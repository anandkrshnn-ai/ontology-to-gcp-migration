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
        "tables_missing_in_spanner": [],
        "tables_missing_in_yaml": [],
        "column_drift": {}
    }
    
    canonical_tables = set(canonical_schemas.keys())
    live_tables = set(live_schemas.keys())
    
    report["tables_missing_in_spanner"] = list(canonical_tables - live_tables)
    report["tables_missing_in_yaml"] = list(live_tables - canonical_tables)
    
    if report["tables_missing_in_spanner"] or report["tables_missing_in_yaml"]:
        report["drift_detected"] = True
        
    # Check tables that exist in both
    for table in canonical_tables.intersection(live_tables):
        c_cols = canonical_schemas[table]
        l_cols = live_schemas[table]
        
        c_col_names = set(c_cols.keys())
        l_col_names = set(l_cols.keys())
        
        missing_in_spanner = list(c_col_names - l_col_names)
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
                
        if missing_in_spanner or extra_in_spanner or type_mismatches:
            report["drift_detected"] = True
            report["column_drift"][table] = {
                "missing_in_spanner": missing_in_spanner,
                "extra_in_spanner_out_of_band": extra_in_spanner,
                "type_mismatches": type_mismatches
            }
            
    return report


def main():
    parser = argparse.ArgumentParser(description="Spanner Schema Drift Detector")
    parser.add_argument("--ontology_dir", required=True, help="Directory containing ontology YAML specifications")
    parser.add_argument("--instance", required=True, help="Spanner Instance ID")
    parser.add_argument("--database", required=True, help="Spanner Database ID")
    
    args = parser.parse_args()
    
    print(f"Loading canonical schemas from {args.ontology_dir}...")
    canonical = load_ontology_schemas(args.ontology_dir)
    
    print(f"Fetching live schemas from Spanner ({args.instance}/{args.database})...")
    live = get_live_spanner_schema(args.instance, args.database)
    
    print("Comparing schemas for drift...")
    report = detect_drift(canonical, live)
    
    if report["drift_detected"]:
        print("\n❌ SCHEMA DRIFT DETECTED!")
        print(json.dumps(report, indent=2))
        sys.exit(1)
    else:
        print("\n✅ NO DRIFT DETECTED. Live Spanner schema matches canonical YAML specifications.")
        sys.exit(0)


if __name__ == "__main__":
    main()
