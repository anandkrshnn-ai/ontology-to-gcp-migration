#!/usr/bin/env python3
import argparse
import os
import sys
import yaml
import json
from typing import Dict, Any, List, Optional
from google.cloud import spanner


# -----------------------------------------------------------------------
# Type alias helpers
# -----------------------------------------------------------------------

_SPANNER_ALIAS_MAP = {
    "INTEGER": "INT64",
    "LONG":    "INT64",
    "DOUBLE":  "FLOAT64",
    "FLOAT":   "FLOAT64",
    "BOOLEAN": "BOOL",
    "STRING":  "STRING(MAX)",
    "TEXT":    "STRING(MAX)",
}


def _normalise_type(raw_type: str) -> str:
    """
    Normalises a YAML-declared type to its canonical Spanner equivalent.
    Preserves native Spanner types (STRING(N), INT64, TIMESTAMP, etc.) verbatim.
    Maps legacy aliases (INTEGER, BOOLEAN, etc.) to canonical equivalents.
    """
    t = raw_type.strip().upper()
    if t.startswith("STRING("):
        return t
    if t in {"INT64", "FLOAT64", "TIMESTAMP", "DATE", "JSON", "BOOL", "NUMERIC", "BYTES"}:
        return t
    return _SPANNER_ALIAS_MAP.get(t, "STRING(MAX)")


def _is_compatible_widening(from_type: str, to_type: str) -> bool:
    """
    Returns True if the type change is a safe, non-breaking widening.

    Compatible widenings:
      STRING(N)  -> STRING(M)   where M > N
      STRING(N)  -> STRING(MAX)
      STRING(MAX)-> STRING(MAX) (no-op, already equal)

    Everything else is classified as a BREAKING type change.
    """
    def _string_size(t: str) -> Optional[int]:
        """Extracts the numeric size from STRING(N); returns None for STRING(MAX)."""
        if t == "STRING(MAX)":
            return None  # None = infinity
        if t.startswith("STRING(") and t.endswith(")"):
            inner = t[7:-1]
            return int(inner) if inner.isdigit() else None
        return -1  # Not a STRING type at all

    f_size = _string_size(from_type)
    t_size = _string_size(to_type)

    # Both must be STRING types
    if f_size == -1 or t_size == -1:
        return False

    # STRING(MAX) -> STRING(MAX) is a no-op (equal, not a mismatch)
    if f_size is None and t_size is None:
        return False

    # STRING(N) -> STRING(MAX) is always a compatible widening
    if t_size is None:
        return True

    # STRING(N) -> STRING(M): compatible only if M > N
    if f_size is not None and t_size is not None:
        return t_size > f_size

    return False


# -----------------------------------------------------------------------
# Schema loading
# -----------------------------------------------------------------------

def load_ontology_schemas(
    ontology_dir: str,
    changed_files: Optional[List[str]] = None
) -> Dict[str, Dict[str, str]]:
    """
    Incremental mode: if changed_files is provided, only parse those files.
    Full mode: scans every .yaml/.yml file in ontology_dir.

    Returns:
        {table_name: {column_name: normalised_spanner_type}}
    """
    schemas: Dict[str, Dict[str, str]] = {}

    if changed_files is not None:
        files_to_scan = [
            f for f in changed_files
            if f.endswith(".yaml") or f.endswith(".yml")
        ]
        print(f"  ⚡ Incremental mode: scanning {len(files_to_scan)} changed file(s).")
    else:
        if not os.path.exists(ontology_dir):
            print(f"Error: Ontology directory '{ontology_dir}' not found.")
            return schemas
        files_to_scan = [
            os.path.join(ontology_dir, f)
            for f in os.listdir(ontology_dir)
            if f.endswith(".yaml") or f.endswith(".yml")
        ]
        print(f"  🔍 Full mode: scanning {len(files_to_scan)} file(s) in '{ontology_dir}'.")

    for filepath in files_to_scan:
        if not os.path.isfile(filepath):
            print(f"  ⚠️  Skipping (not found): {filepath}")
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    continue
                spec = data.get("spec", {})
                table_name = spec.get("tableName") or spec.get("table")
                if not table_name:
                    continue

                columns: Dict[str, str] = {}
                kind = data.get("kind")

                # Support both attributes (list) and properties (dict) formats
                if "attributes" in spec and "properties" not in spec:
                    for attr in spec.get("attributes", []):
                        columns[attr["name"]] = _normalise_type(
                            attr.get("type", "STRING(MAX)")
                        )
                elif "properties" in spec:
                    for prop_name, prop_def in spec["properties"].items():
                        raw = (
                            prop_def.get("type", "STRING(MAX)")
                            if isinstance(prop_def, dict)
                            else prop_def
                        )
                        columns[prop_name] = _normalise_type(raw)

                # sourceKey/targetKey are graph metadata — NOT physical columns
                if columns:
                    schemas[table_name] = columns
            except Exception as e:
                print(f"  ❌ Error parsing '{filepath}': {e}")

    return schemas


# -----------------------------------------------------------------------
# Live Spanner schema
# -----------------------------------------------------------------------

def get_live_spanner_schema(
    project_id: Optional[str],
    instance_id: str,
    database_id: str,
    table_filter: Optional[set] = None
) -> Dict[str, Dict[str, str]]:
    """
    Incremental mode: table_filter limits the Spanner query to specific tables.
    Full mode: fetches all user-managed tables.

    Returns:
        {table_name: {column_name: spanner_type (uppercased)}}
    """
    if project_id:
        spanner_client = spanner.Client(project=project_id)
    else:
        spanner_client = spanner.Client()

    instance = spanner_client.instance(instance_id)
    database = instance.database(database_id)

    base_query = """
SELECT table_name, column_name, spanner_type
FROM information_schema.columns
WHERE table_catalog = '' AND table_schema = ''
AND table_name NOT LIKE 'v_%'
AND table_name NOT IN (
    'raw_yaml_registry', 'canonical_object_types',
    'canonical_relationship_types', 'schema_change_log',
    'deployment_audit', 'rule_audit'
)
"""
    if table_filter:
        placeholders = ", ".join(f"'{t}'" for t in table_filter)
        query = base_query + f" AND table_name IN ({placeholders})"
        print(f"  ⚡ Incremental Spanner query: fetching {len(table_filter)} table(s) only.")
    else:
        query = base_query
        print("  🔍 Full Spanner query: fetching all tables.")

    live_schema: Dict[str, Dict[str, str]] = {}
    try:
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(query)
            for row in results:
                table_name = row[0]
                column_name = row[1]
                spanner_type = row[2].upper().strip()
                if table_name not in live_schema:
                    live_schema[table_name] = {}
                live_schema[table_name][column_name] = spanner_type
    except Exception as e:
        print(f"  ❌ Error querying Spanner: {e}")
        raise

    return live_schema


# -----------------------------------------------------------------------
# Core drift detection
# -----------------------------------------------------------------------

def detect_drift(
    canonical_schemas: Dict[str, Dict[str, str]],
    live_schemas: Dict[str, Dict[str, str]]
) -> Dict[str, Any]:
    """
    Compares canonical YAML schemas against live Spanner schemas.

    Returns a drift report with shape:
    {
        "drift_detected": bool,           # True = BREAKING change, blocks pipeline
        "compatibility_status": str,      # "NONE" | "ADDITIVE" | "COMPATIBLE" | "BREAKING"
        "pending_evolution": {
            "tables_to_create": [],       # New tables in YAML not yet in Spanner
            "columns_to_add": {},         # New columns in YAML not yet in Spanner
            "compatible_type_changes": {} # STRING widening changes (safe ALTER COLUMN)
        },
        "true_drift_details": {}          # BREAKING changes that must be resolved manually
    }
    """
    report: Dict[str, Any] = {
        "drift_detected": False,
        "compatibility_status": "NONE",
        "pending_evolution": {
            "tables_to_create": [],
            "columns_to_add": {},
            "compatible_type_changes": {}
        },
        "true_drift_details": {}
    }

    canonical_tables = set(canonical_schemas.keys())
    live_tables = set(live_schemas.keys())

    # ------------------------------------------------------------------
    # 1. New tables in YAML → CREATE TABLE (ADDITIVE)
    # ------------------------------------------------------------------
    tables_to_create = sorted(canonical_tables - live_tables)
    if tables_to_create:
        report["pending_evolution"]["tables_to_create"] = tables_to_create

    # ------------------------------------------------------------------
    # 2. Tables in Spanner but missing from YAML → BREAKING
    #    (Could be orphaned tables — flag for DBA review)
    # ------------------------------------------------------------------
    tables_missing_in_yaml = sorted(live_tables - canonical_tables)
    if tables_missing_in_yaml:
        report["drift_detected"] = True
        report["true_drift_details"]["tables_missing_in_yaml"] = tables_missing_in_yaml

    # ------------------------------------------------------------------
    # 3. Per-column analysis for tables that exist in both
    # ------------------------------------------------------------------
    for table in sorted(canonical_tables.intersection(live_tables)):
        c_cols = canonical_schemas[table]
        l_cols = live_schemas[table]
        c_col_names = set(c_cols.keys())
        l_col_names = set(l_cols.keys())

        # 3a. New columns in YAML → ALTER TABLE ADD COLUMN (ADDITIVE)
        new_cols = sorted(c_col_names - l_col_names)
        if new_cols:
            report["pending_evolution"]["columns_to_add"][table] = new_cols

        # 3b. Columns in Spanner but not in YAML → informational only (safe to ignore)
        undeclared = sorted(l_col_names - c_col_names)
        if undeclared:
            print(
                f"  ℹ️  INFO: '{table}' has undeclared Spanner columns: {undeclared}\n"
                f"      (Safe to ignore. Consider adding to YAML for completeness.)"
            )

        # 3c. Type mismatches on shared columns
        for col in sorted(c_col_names.intersection(l_col_names)):
            c_type = c_cols[col].replace(" ", "")
            l_type = l_cols[col].replace(" ", "")

            if c_type == l_type:
                continue  # Perfect match — no change needed

            # STRING alias shorthand: treat bare "STRING" as compatible with any STRING(N)
            if c_type == "STRING" and l_type.startswith("STRING"):
                continue

            if _is_compatible_widening(from_type=l_type, to_type=c_type):
                # Safe ALTER COLUMN — STRING(100) -> STRING(200) etc.
                if table not in report["pending_evolution"]["compatible_type_changes"]:
                    report["pending_evolution"]["compatible_type_changes"][table] = []
                report["pending_evolution"]["compatible_type_changes"][table].append({
                    "column": col,
                    "from":   l_type,
                    "to":     c_type
                })
            else:
                # BREAKING — narrowing, type swap, or non-STRING change
                report["drift_detected"] = True
                if table not in report["true_drift_details"]:
                    report["true_drift_details"][table] = {"type_mismatches": []}
                report["true_drift_details"][table]["type_mismatches"].append({
                    "column":   col,
                    "expected": c_type,
                    "actual":   l_type
                })

    # ------------------------------------------------------------------
    # 4. Determine overall compatibility_status
    # ------------------------------------------------------------------
    pending = report["pending_evolution"]
    has_additive = bool(
        pending["tables_to_create"] or pending["columns_to_add"]
    )
    has_compatible = bool(pending["compatible_type_changes"])

    if report["drift_detected"]:
        report["compatibility_status"] = "BREAKING"
    elif has_additive and has_compatible:
        report["compatibility_status"] = "COMPATIBLE"
    elif has_additive:
        report["compatibility_status"] = "ADDITIVE"
    elif has_compatible:
        report["compatibility_status"] = "COMPATIBLE"
    else:
        report["compatibility_status"] = "NONE"

    return report


# -----------------------------------------------------------------------
# CLI entry point
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Spanner Schema Drift Detector")
    parser.add_argument("--ontology_dir", required=True, help="Path to ontology YAML directory")
    parser.add_argument("--instance",     required=True, help="Spanner instance ID")
    parser.add_argument("--database",     required=True, help="Spanner database ID")
    parser.add_argument("--project",      required=False, help="GCP project ID")
    parser.add_argument(
        "--apply-mode",
        choices=["auto-additive", "manual", "strict"],
        default="auto-additive",
        help="How to handle pending additive evolution"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply pending DDL to Spanner (auto-additive mode only)"
    )
    parser.add_argument(
        "--changed-files",
        help=(
            "Path to a text file listing changed YAML paths (one per line). "
            "Enables incremental mode — only changed files are parsed and only "
            "their tables are queried from Spanner. Omit for full scan."
        )
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Resolve incremental vs full-scan mode
    # ------------------------------------------------------------------
    changed_files = None
    table_filter = None

    if args.changed_files:
        if not os.path.isfile(args.changed_files):
            print(
                f"⚠️  --changed-files path not found: '{args.changed_files}'. "
                f"Falling back to full scan."
            )
        else:
            with open(args.changed_files, "r") as cf:
                changed_files = [line.strip() for line in cf if line.strip()]
            if not changed_files:
                print("⚠️  --changed-files list is empty. Falling back to full scan.")
                changed_files = None

    mode_label = "[INCREMENTAL]" if changed_files else "[FULL SCAN]"
    print(f"\nLoading canonical schemas from '{args.ontology_dir}' {mode_label}...")
    canonical = load_ontology_schemas(args.ontology_dir, changed_files=changed_files)

    if changed_files:
        table_filter = set(canonical.keys())

    print(f"Fetching live schemas from Spanner ({args.instance}/{args.database})...")
    live = get_live_spanner_schema(
        args.project, args.instance, args.database, table_filter=table_filter
    )

    print("Comparing schemas for drift...\n")
    report = detect_drift(canonical, live)

    # ------------------------------------------------------------------
    # BREAKING — hard stop
    # ------------------------------------------------------------------
    if report["drift_detected"]:
        print("❌ BREAKING schema drift detected. Pipeline blocked.")
        print(json.dumps(report["true_drift_details"], indent=2))
        sys.exit(1)

    # ------------------------------------------------------------------
    # Summarise pending evolution
    # ------------------------------------------------------------------
    pending = report["pending_evolution"]
    has_evolution = bool(
        pending["tables_to_create"]
        or pending["columns_to_add"]
        or pending["compatible_type_changes"]
    )

    if not has_evolution:
        print("✅ NO DRIFT DETECTED. Live Spanner schema matches canonical YAML.")
        sys.exit(0)

    print(f"📋 Pending evolution ({report['compatibility_status']}):")
    print(json.dumps(pending, indent=2))

    # ------------------------------------------------------------------
    # apply-mode gate
    # ------------------------------------------------------------------
    if args.apply_mode == "strict":
        print("\n❌ Strict mode: no schema changes allowed in this pipeline.")
        sys.exit(1)

    if args.apply_mode == "manual":
        print("\n⚠️  Manual mode: review the pending evolution above and apply manually.")
        sys.exit(0)

    # auto-additive — proceed
    print("\n✅ Auto-additive mode: pending evolution approved.")

    if not args.apply:
        print("   (Re-run with --apply to execute DDL against Spanner.)")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Apply DDL to Spanner
    # ------------------------------------------------------------------
    print("\nApplying schema evolution DDL to Spanner...")

    if args.project:
        spanner_client = spanner.Client(project=args.project)
    else:
        spanner_client = spanner.Client()
    instance = spanner_client.instance(args.instance)
    database = instance.database(args.database)

    statements: List[str] = []

    # 1. CREATE TABLE for new tables (uses GraphCompiler to generate DDL)
    if pending["tables_to_create"]:
        from scripts.graph_compiler import GraphCompiler
        compiler = GraphCompiler("ADDITIVE", {})
        for fname in os.listdir(args.ontology_dir):
            if not (fname.endswith(".yaml") or fname.endswith(".yml")):
                continue
            fpath = os.path.join(args.ontology_dir, fname)
            with open(fpath, "r", encoding="utf-8") as fh:
                try:
                    data = yaml.safe_load(fh)
                    spec = data.get("spec", {})
                    tname = spec.get("tableName") or spec.get("table")
                    if tname in pending["tables_to_create"]:
                        ddl = compiler.generate_table_ddl(data)
                        if ddl:
                            statements.append(ddl)
                except Exception as e:
                    print(f"  ❌ Error generating DDL for '{fname}': {e}")

    # 2. ALTER TABLE ADD COLUMN for new columns
    for table, cols in pending["columns_to_add"].items():
        for col in cols:
            col_type = canonical[table].get(col, "STRING(MAX)")
            statements.append(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    # 3. ALTER TABLE ALTER COLUMN for compatible type widenings
    for table, changes in pending["compatible_type_changes"].items():
        for change in changes:
            statements.append(
                f"ALTER TABLE {table} ALTER COLUMN {change['column']} {change['to']}"
            )

    if not statements:
        print("  No DDL statements generated.")
        sys.exit(0)

    print(f"  Executing {len(statements)} DDL statement(s):")
    for stmt in statements:
        print(f"    → {stmt}")

    clean_statements = [s.rstrip().rstrip(";") for s in statements if s.strip()]
    operation = database.update_ddl(clean_statements)
    operation.result()  # Blocks until Spanner confirms completion
    print("\n✅ Schema evolution applied successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
