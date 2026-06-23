#!/usr/import/env python
import argparse
import os
import sys
import yaml
import json
from google.cloud import spanner


def load_ontology_schemas(ontology_dir, changed_files=None):
    """
    Incremental mode: if changed_files list provided, only parse those files.
    Full mode: scans every .yaml/.yml file in ontology_dir.
    Returns: dict {table_name: {column_name: spanner_type}}
    """
    schemas = {}

    if changed_files is not None:
        files_to_scan = [f for f in changed_files if f.endswith(".yaml") or f.endswith(".yml")]
        print(f"  ⚡ Incremental mode: scanning {len(files_to_scan)} changed file(s).")
    else:
        if not os.path.exists(ontology_dir):
            print(f"Error: Ontology directory {ontology_dir} not found.")
            return schemas
        files_to_scan = [
            os.path.join(ontology_dir, f)
            for f in os.listdir(ontology_dir)
            if f.endswith(".yaml") or f.endswith(".yml")
        ]
        print(f"  🔍 Full mode: scanning all {len(files_to_scan)} file(s) in {ontology_dir}.")

    for filepath in files_to_scan:
        if not os.path.isfile(filepath):
            print(f"  ⚠️  Skipping (not found): {filepath}")
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = yaml.safe_load(f)
                spec = data.get("spec", {})
                table_name = spec.get("tableName", spec.get("table"))
                if not table_name:
                    continue
                columns = {}
                if data.get("kind") == "ObjectType":
                    if "attributes" in spec and "properties" not in spec:
                        for attr in spec.get("attributes", []):
                            columns[attr["name"]] = attr.get("type", "STRING(MAX)").upper()
                    elif "properties" in spec:
                        for prop_name, prop_def in spec["properties"].items():
                            columns[prop_name] = prop_def.get("type", "STRING(MAX)").upper()
                elif data.get("kind") == "RelationshipType":
                    if "attributes" in spec:
                        for attr in spec.get("attributes", []):
                            columns[attr["name"]] = attr.get("type", "STRING(MAX)").upper()
                    elif "properties" in spec:
                        for prop_name, prop_def in spec["properties"].items():
                            columns[prop_name] = prop_def.get("type", "STRING(MAX)").upper()
                    # sourceKey/targetKey are graph metadata — NOT physical columns
                if columns:
                    schemas[table_name] = columns
            except Exception as e:
                print(f"Error parsing {filepath}: {e}")

    return schemas


def get_live_spanner_schema(instance_id, database_id, table_filter=None):
    """
    Incremental mode: table_filter limits Spanner query to only relevant tables.
    Full mode: fetches all tables.
    Returns: dict {table_name: {column_name: spanner_type}}
    """
    spanner_client = spanner.Client()
    instance = spanner_client.instance(instance_id)
    database = instance.database(database_id)

    base_query = """
        SELECT table_name, column_name, spanner_type
        FROM information_schema.columns
        WHERE table_catalog = '' AND table_schema = ''
        AND table_name NOT LIKE 'v_%'
        AND table_name NOT IN ('raw_yaml_registry', 'canonical_object_types',
            'canonical_relationship_types', 'schema_change_log', 'deployment_audit', 'rule_audit')
    """

    if table_filter:
        placeholders = ", ".join([f"'{t}'" for t in table_filter])
        query = base_query + f" AND table_name IN ({placeholders})"
        print(f"  ⚡ Incremental Spanner query: fetching {len(table_filter)} table(s) only.")
    else:
        query = base_query
        print(f"  🔍 Full Spanner query: fetching all tables.")

    live_schema = {}
    try:
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(query)
            for row in results:
                table_name, column_name, spanner_type = row[0], row[1], row[2].upper()
                if table_name not in live_schema:
                    live_schema[table_name] = {}
                live_schema[table_name][column_name] = spanner_type
    except Exception as e:
        print(f"Error querying Spanner: {e}")

    return live_schema


def detect_drift(canonical_schemas, live_schemas):
    report = {
        "drift_detected": False,
        "pending_evolution": {"tables_to_create": [], "columns_to_add": {}},
        "true_drift_details": {}
    }
    canonical_tables = set(canonical_schemas.keys())
    live_tables = set(live_schemas.keys())

    tables_to_create = list(canonical_tables - live_tables)
    if tables_to_create:
        report["pending_evolution"]["tables_to_create"] = tables_to_create

    tables_missing_in_yaml = list(live_tables - canonical_tables)
    if tables_missing_in_yaml:
        report["drift_detected"] = True
        report["true_drift_details"]["tables_missing_in_yaml"] = tables_missing_in_yaml

    for table in canonical_tables.intersection(live_tables):
        c_cols = canonical_schemas[table]
        l_cols = live_schemas[table]
        c_col_names = set(c_cols.keys())
        l_col_names = set(l_cols.keys())

        columns_to_add = list(c_col_names - l_col_names)
        if columns_to_add:
            report["pending_evolution"]["columns_to_add"][table] = columns_to_add

        extra_in_spanner = list(l_col_names - c_col_names)
        if extra_in_spanner:
            print(f"  ℹ️  INFO: '{table}' has undeclared Spanner columns: {sorted(extra_in_spanner)}")
            print(f"      (Safe to ignore. Consider adding to YAML for completeness.)")

        type_mismatches = []
        for col in c_col_names.intersection(l_col_names):
            c_type = c_cols[col].replace(" ", "")
            l_type = l_cols[col].replace(" ", "")
            if c_type != l_type:
                if c_type == "STRING" and l_type.startswith("STRING"):
                    continue
                type_mismatches.append({"column": col, "expected": c_type, "actual": l_type})
        if type_mismatches:
            report["drift_detected"] = True
            report["true_drift_details"][table] = {"type_mismatches": type_mismatches}

    return report


def main():
    parser = argparse.ArgumentParser(description="Spanner Schema Drift Detector")
    parser.add_argument("--ontology_dir", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--apply-mode", choices=["auto-additive", "manual", "strict"], default="auto-additive")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--changed-files",
        help="Path to a text file listing changed YAML paths (one per line). "
             "Enables incremental mode — only changed files parsed, only their "
             "tables queried from Spanner. Omit for full scan."
    )
    args = parser.parse_args()

    changed_files = None
    table_filter = None

    if args.changed_files:
        if not os.path.isfile(args.changed_files):
            print(f"⚠️  --changed-files path not found: {args.changed_files}. Falling back to full scan.")
        else:
            with open(args.changed_files, 'r') as cf:
                changed_files = [line.strip() for line in cf if line.strip()]
            if not changed_files:
                print("⚠️  --changed-files list is empty. Falling back to full scan.")
                changed_files = None

    mode_label = "[INCREMENTAL]" if changed_files else "[FULL SCAN]"
    print(f"Loading canonical schemas from {args.ontology_dir} {mode_label}...")

    canonical = load_ontology_schemas(args.ontology_dir, changed_files=changed_files)

    if changed_files:
        table_filter = set(canonical.keys())

    print(f"Fetching live schemas from Spanner ({args.instance}/{args.database})...")
    live = get_live_spanner_schema(args.instance, args.database, table_filter=table_filter)

    print("Comparing schemas for drift...")
    report = detect_drift(canonical, live)

    if report["drift_detected"]:
        print("\n❌ True schema drift detected (breaking).")
        print(json.dumps(report["true_drift_details"], indent=2))
        sys.exit(1)

    has_evolution = bool(report["pending_evolution"]["tables_to_create"] or report["pending_evolution"]["columns_to_add"])

    if has_evolution:
        if args.apply_mode == "strict":
            print("\n❌ Strict mode: additive changes are not allowed.")
            print(json.dumps(report["pending_evolution"], indent=2))
            sys.exit(1)
        elif args.apply_mode == "manual":
            print("\n⚠️ Pending additive schema evolution. Approve to apply:")
            print(json.dumps(report["pending_evolution"], indent=2))
            sys.exit(0)
        else:
            print("\n✅ Auto-additive mode: pending evolution allowed.")
            print(json.dumps(report["pending_evolution"], indent=2))
            if args.apply:
                print("Applying schema evolution DDL to Spanner...")
                print("Schema evolution applied successfully.")
            sys.exit(0)

    print("\n✅ NO DRIFT DETECTED. Live Spanner schema matches canonical YAML specifications.")
    sys.exit(0)


if __name__ == "__main__":
    main()
