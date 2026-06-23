#!/usr/import/env python
import argparse
import os
import sys
import yaml
import json
from google.cloud import spanner


def load_ontology_schemas(ontology_dir):
    """
    Loads YAML files and extracts canonical table schemas.
    Returns: dict {table_name: {column_name: spanner_type}}
    """
    schemas = {}
    if not os.path.exists(ontology_dir):
        print(f"Error: Ontology directory {ontology_dir} not found.")
        return schemas

    for filename in os.listdir(ontology_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(ontology_dir, filename), 'r', encoding='utf-8') as f:
                try:
                    data = yaml.safe_load(f)
                    spec = data.get("spec", {})
                    table_name = spec.get("tableName", spec.get("table"))
                    
                    if not table_name:
                        continue
                        
                    columns = {}
                    
                    # Handle ObjectType attributes/properties
                    if data.get("kind") == "ObjectType":
                        # Support real ontology format: attributes as list
                        if "attributes" in spec and "properties" not in spec:
                            for attr in spec.get("attributes", []):
                                columns[attr["name"]] = attr.get("type", "STRING(MAX)").upper()
                        # Support properties dict
                        elif "properties" in spec:
                            for prop_name, prop_def in spec["properties"].items():
                                columns[prop_name] = prop_def.get("type", "STRING(MAX)").upper()
                                
                    # Handle RelationshipType
                    elif data.get("kind") == "RelationshipType":
                        # Usually relationship edges have predictable columns or defined ones
                        columns["source_id"] = "STRING(MAX)"
                        columns["target_id"] = "STRING(MAX)"
                        # If properties are defined
                        if "properties" in spec:
                            for prop_name, prop_def in spec["properties"].items():
                                columns[prop_name] = prop_def.get("type", "STRING(MAX)").upper()

                    if columns:
                        schemas[table_name] = columns
                        
                except Exception as e:
                    print(f"Error parsing {filename}: {e}")
                    
    return schemas


def get_live_spanner_schema(instance_id, database_id):
    """
    Queries Spanner INFORMATION_SCHEMA to get live table schemas.
    Returns: dict {table_name: {column_name: spanner_type}}
    """
    spanner_client = spanner.Client()
    instance = spanner_client.instance(instance_id)
    database = instance.database(database_id)
    
    query = """
        SELECT table_name, column_name, spanner_type 
        FROM information_schema.columns 
        WHERE table_catalog = '' AND table_schema = '' 
        AND table_name NOT LIKE 'v_%' 
        AND table_name NOT IN ('raw_yaml_registry', 'canonical_object_types', 'canonical_relationship_types', 'schema_change_log', 'deployment_audit', 'rule_audit')
    """
    
    live_schema = {}
    try:
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(query)
            for row in results:
                table_name = row[0]
                column_name = row[1]
                spanner_type = row[2].upper()
                
                if table_name not in live_schema:
                    live_schema[table_name] = {}
                live_schema[table_name][column_name] = spanner_type
    except Exception as e:
        print(f"Error querying Spanner: {e}")
        
    return live_schema


def detect_drift(canonical_schemas, live_schemas):
    """
    Compares canonical YAML schemas vs live Spanner schemas.
    """
    report = {
        "drift_detected": False,
        "pending_evolution": {
            "tables_to_create": [],
            "columns_to_add": {}
        },
        "true_drift_details": {}
    }
    
    canonical_tables = set(canonical_schemas.keys())
    live_tables = set(live_schemas.keys())
    
    # 1. New tables (present in YAML, absent in Spanner)
    tables_to_create = list(canonical_tables - live_tables)
    if tables_to_create:
        report["pending_evolution"]["tables_to_create"] = tables_to_create
        
    # Extra tables in Spanner (missing in YAML) - True Drift
    tables_missing_in_yaml = list(live_tables - canonical_tables)
    if tables_missing_in_yaml:
        report["drift_detected"] = True
        report["true_drift_details"]["tables_missing_in_yaml"] = tables_missing_in_yaml
        
    # Check tables that exist in both
    for table in canonical_tables.intersection(live_tables):
        c_cols = canonical_schemas[table]
        l_cols = live_schemas[table]
        
        c_col_names = set(c_cols.keys())
        l_col_names = set(l_cols.keys())
        
        # 2. New columns (present in YAML, absent in Spanner)
        columns_to_add = list(c_col_names - l_col_names)
        if columns_to_add:
            report["pending_evolution"]["columns_to_add"][table] = columns_to_add
            
        # 3. True drift (type change, column dropped from YAML)
        extra_in_spanner = list(l_col_names - c_col_names)
        type_mismatches = []
        
        for col in c_col_names.intersection(l_col_names):
            # Normalise types for basic comparison (e.g., STRING(MAX) vs STRING(256))
            c_type = c_cols[col].replace(" ", "")
            l_type = l_cols[col].replace(" ", "")
            if c_type != l_type:
                # Sometimes user defines STRING, spanner says STRING(MAX)
                if c_type == "STRING" and l_type.startswith("STRING"):
                    continue
                type_mismatches.append({"column": col, "expected": c_type, "actual": l_type})
                
        if extra_in_spanner or type_mismatches:
            report["drift_detected"] = True
            report["true_drift_details"][table] = {
                "extra_in_spanner_out_of_band": extra_in_spanner,
                "type_mismatches": type_mismatches
            }
            
    return report


def main():
    parser = argparse.ArgumentParser(description="Spanner Schema Drift Detector")
    parser.add_argument("--ontology_dir", required=True, help="Directory containing ontology YAML specifications")
    parser.add_argument("--instance", required=True, help="Spanner Instance ID")
    parser.add_argument("--database", required=True, help="Spanner Database ID")
    parser.add_argument("--apply-mode", choices=["auto-additive", "manual", "strict"], default="auto-additive", help="How to handle pending evolution")
    
    args = parser.parse_args()
    
    print(f"Loading canonical schemas from {args.ontology_dir}...")
    canonical = load_ontology_schemas(args.ontology_dir)
    
    print(f"Fetching live schemas from Spanner ({args.instance}/{args.database})...")
    live = get_live_spanner_schema(args.instance, args.database)
    
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
            sys.exit(0)
            
    print("\n✅ NO DRIFT DETECTED. Live Spanner schema matches canonical YAML specifications.")
    sys.exit(0)


if __name__ == "__main__":
    main()
