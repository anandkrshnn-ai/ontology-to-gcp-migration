#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from typing import Dict

import yaml
from google.cloud import spanner


# ============================================================
# ONTOLOGY LOADER
# ============================================================

def normalize_type(spanner_type: str) -> str:
    if not spanner_type:
        return "STRING(MAX)"
    return str(spanner_type).upper().replace(" ", "")


def load_ontology_schemas(
        ontology_dir: str,
        changed_files=None
) -> Dict[str, Dict[str, str]]:

    schemas = {}

    if changed_files:
        files_to_scan = [
            f for f in changed_files
            if f.endswith(".yaml") or f.endswith(".yml")
        ]
        print(
            f"⚡ Incremental mode: "
            f"scanning {len(files_to_scan)} ontology file(s)"
        )
    else:

        if not os.path.exists(ontology_dir):
            raise FileNotFoundError(
                f"Ontology directory not found: {ontology_dir}"
            )

        files_to_scan = [
            os.path.join(ontology_dir, f)
            for f in os.listdir(ontology_dir)
            if f.endswith(".yaml") or f.endswith(".yml")
        ]

        print(
            f"🔍 Full mode: scanning "
            f"{len(files_to_scan)} ontology file(s)"
        )

    for filepath in files_to_scan:

        if not os.path.isfile(filepath):
            print(f"Skipping missing file: {filepath}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:

            data = yaml.safe_load(f)

            if not isinstance(data, dict):
                continue

            spec = data.get("spec", {})

            table_name = (
                    spec.get("tableName")
                    or spec.get("table")
            )

            if not table_name:
                continue

            columns = {}

            #
            # ATTRIBUTES FORMAT
            #
            if "attributes" in spec:

                for attr in spec.get("attributes", []):

                    name = attr.get("name")

                    if not name:
                        continue

                    columns[name] = normalize_type(
                        attr.get("type", "STRING(MAX)")
                    )

            #
            # PROPERTIES FORMAT
            #
            if "properties" in spec:

                props = spec.get("properties", {})

                if isinstance(props, dict):

                    for prop_name, prop_def in props.items():

                        columns[prop_name] = normalize_type(
                            prop_def.get("type", "STRING(MAX)")
                        )

            if columns:
                schemas[table_name] = columns

    return schemas


# ============================================================
# SPANNER DISCOVERY
# ============================================================

SYSTEM_TABLES = {
    "raw_yaml_registry",
    "canonical_object_types",
    "canonical_relationship_types",
    "schema_change_log",
    "deployment_audit",
    "rule_audit",
    "ontology_object_registry",
    "file_processing_status",
    "rule_definitions",
    "transactions",
    "ontology_change_log"
}


def get_live_spanner_schema(
        project_id,
        instance_id,
        database_id,
        table_filter=None
):
    if project_id:
        client = spanner.Client(project=project_id)
    else:
        client = spanner.Client()

    instance = client.instance(instance_id)
    database = instance.database(database_id)

    query = """
    SELECT
        table_name,
        column_name,
        spanner_type
    FROM information_schema.columns
    WHERE table_catalog = ''
      AND table_schema = ''
      AND table_name NOT LIKE 'v_%'
    """

    live_schema = {}

    with database.snapshot() as snapshot:

        rows = snapshot.execute_sql(query)

        for row in rows:

            table_name = row[0]

            if table_name in SYSTEM_TABLES:
                continue

            if table_filter and table_name not in table_filter:
                continue

            column_name = row[1]
            spanner_type = normalize_type(row[2])

            live_schema.setdefault(
                table_name,
                {}
            )[column_name] = spanner_type

    return live_schema


# ============================================================
# TYPE COMPATIBILITY
# ============================================================

def string_length(spanner_type):

    m = re.match(r"STRING\((.+)\)", spanner_type)

    if not m:
        return None

    value = m.group(1)

    if value == "MAX":
        return 999999999

    return int(value)


def is_compatible_type_change(
        live_type,
        yaml_type
):

    live_type = normalize_type(live_type)
    yaml_type = normalize_type(yaml_type)

    if live_type == yaml_type:
        return True

    #
    # STRING EXPANSION
    #
    if (
            live_type.startswith("STRING(")
            and yaml_type.startswith("STRING(")
    ):
        return (
                string_length(yaml_type)
                >=
                string_length(live_type)
        )

    return False


# ============================================================
# DRIFT DETECTOR
# ============================================================

def detect_drift(
        canonical_schemas,
        live_schemas
):

    report = {
        "drift_detected": False,

        "pending_evolution": {
            "tables_to_create": [],
            "columns_to_add": {},
            "compatible_type_changes": {}
        },

        "true_drift_details": {}
    }

    canonical_tables = set(
        canonical_schemas.keys()
    )

    live_tables = set(
        live_schemas.keys()
    )

    #
    # NEW TABLES
    #
    report["pending_evolution"]["tables_to_create"] = sorted(
        list(
            canonical_tables - live_tables
        )
    )

    #
    # TABLES EXIST IN SPANNER
    # BUT NOT IN CANONICAL YAML
    #
    extra_tables = sorted(
        list(
            live_tables - canonical_tables
        )
    )

    if extra_tables:

        report["drift_detected"] = True

        report["true_drift_details"][
            "tables_missing_in_yaml"
        ] = extra_tables

    #
    # TABLE COMPARISON
    #
    for table in canonical_tables.intersection(
            live_tables
    ):

        ccols = canonical_schemas[table]
        lcols = live_schemas[table]

        cset = set(ccols.keys())
        lset = set(lcols.keys())

        #
        # NEW COLUMNS
        #
        new_columns = sorted(
            list(cset - lset)
        )

        if new_columns:

            report["pending_evolution"][
                "columns_to_add"
            ][table] = new_columns

        #
        # EXTRA COLUMNS
        #
        extra_columns = sorted(
            list(lset - cset)
        )

        if extra_columns:

            print(
                f"INFO: "
                f"{table} has undeclared columns "
                f"{extra_columns}"
            )

        #
        # TYPE CHECK
        #
        for col in cset.intersection(lset):

            yaml_type = normalize_type(
                ccols[col]
            )

            live_type = normalize_type(
                lcols[col]
            )

            if yaml_type == live_type:
                continue

            #
            # COMPATIBLE EVOLUTION
            #
            if is_compatible_type_change(
                    live_type,
                    yaml_type
            ):

                report[
                    "pending_evolution"
                ][
                    "compatible_type_changes"
                ].setdefault(
                    table,
                    []
                ).append(
                    {
                        "column": col,
                        "from": live_type,
                        "to": yaml_type
                    }
                )

                continue

            #
            # BREAKING DRIFT
            #
            report["drift_detected"] = True

            report[
                "true_drift_details"
            ].setdefault(
                table,
                {
                    "type_mismatches": []
                }
            )

            report[
                "true_drift_details"
            ][
                table
            ][
                "type_mismatches"
            ].append(
                {
                    "column": col,
                    "expected": yaml_type,
                    "actual": live_type
                }
            )

    return report


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Ontology Drift Detector"
    )

    parser.add_argument(
        "--ontology_dir",
        required=True
    )

    parser.add_argument(
        "--instance",
        required=True
    )

    parser.add_argument(
        "--database",
        required=True
    )

    parser.add_argument(
        "--project"
    )

    parser.add_argument(
        "--apply-mode",
        default="auto-additive",
        choices=[
            "auto-additive",
            "manual",
            "strict"
        ]
    )

    parser.add_argument(
        "--changed-files"
    )

    args = parser.parse_args()

    changed_files = None
    table_filter = None

    if args.changed_files:

        if os.path.isfile(
                args.changed_files
        ):

            with open(
                    args.changed_files,
                    "r"
            ) as f:

                changed_files = [
                    x.strip()
                    for x in f
                    if x.strip()
                ]

        if not changed_files:

            print(
                "⚠ Empty changed-files list. "
                "Using full scan."
            )

            changed_files = None

    canonical = load_ontology_schemas(
        args.ontology_dir,
        changed_files
    )

    if changed_files:
        table_filter = set(
            canonical.keys()
        )

    live = get_live_spanner_schema(
        args.project,
        args.instance,
        args.database,
        table_filter
    )

    report = detect_drift(
        canonical,
        live
    )

    #
    # BREAKING DRIFT
    #
    if report["drift_detected"]:

        print(
            "\n❌ BREAKING DRIFT DETECTED"
        )

        print(
            json.dumps(
                report["true_drift_details"],
                indent=2
            )
        )

        sys.exit(1)

    #
    # COMPATIBLE EVOLUTION
    #
    has_evolution = any([
        report["pending_evolution"]["tables_to_create"],
        report["pending_evolution"]["columns_to_add"],
        report["pending_evolution"]["compatible_type_changes"]
    ])

    if has_evolution:

        print(
            "\n✅ COMPATIBLE SCHEMA EVOLUTION"
        )

        print(
            json.dumps(
                report["pending_evolution"],
                indent=2
            )
        )

        if args.apply_mode == "strict":
            sys.exit(1)

        sys.exit(0)

    print(
        "\n✅ NO DRIFT DETECTED"
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
