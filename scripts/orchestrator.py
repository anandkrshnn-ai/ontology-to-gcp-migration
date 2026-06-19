#!/usr/bin/env python
import argparse
import hashlib
import json
import os
import sys
import yaml
from typing import Dict, Any, List, Tuple
from google.cloud import spanner

class OntologyValidationError(Exception):
    pass

class SchemaDiff:
    def __init__(self, change_type: str, diff_summary: Dict[str, Any]):
        self.change_type = change_type  # ADDITIVE, COMPATIBLE, BREAKING
        self.diff_summary = diff_summary

class OntologyParser:
    """Parses and validates ontology YAML contracts."""
    
    @staticmethod
    def load_yaml(file_path: str) -> Dict[str, Any]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise OntologyValidationError(f"Failed to read or parse YAML file {file_path}: {e}")

    @staticmethod
    def validate_structure(data: Dict[str, Any], file_path: str) -> None:
        required_fields = ["apiVersion", "kind", "metadata", "spec"]
        for field in required_fields:
            if field not in data:
                raise OntologyValidationError(f"Missing required top-level field '{field}' in {file_path}")

        kind = data.get("kind")
        if kind not in ["ObjectType", "RelationshipType", "PropertyGraph"]:
            raise OntologyValidationError(f"Invalid kind '{kind}' in {file_path}. Must be ObjectType, RelationshipType, or PropertyGraph")

        metadata = data.get("metadata", {})
        if "name" not in metadata:
            raise OntologyValidationError(f"Missing metadata.name in {file_path}")

        spec = data.get("spec", {})
        if kind == "ObjectType":
            if "primaryKey" not in spec:
                raise OntologyValidationError(f"ObjectType spec must define 'primaryKey' in {file_path}")
            if "tableName" not in spec:
                raise OntologyValidationError(f"ObjectType spec must define 'tableName' in {file_path}")
            if "properties" not in spec:
                raise OntologyValidationError(f"ObjectType spec must define 'properties' in {file_path}")
        elif kind == "RelationshipType":
            if "tableName" not in spec:
                raise OntologyValidationError(f"RelationshipType spec must define 'tableName' in {file_path}")
            if "sourceType" not in spec:
                raise OntologyValidationError(f"RelationshipType spec must define 'sourceType' in {file_path}")
            if "targetType" not in spec:
                raise OntologyValidationError(f"RelationshipType spec must define 'targetType' in {file_path}")
            if "primaryKey" not in spec:
                raise OntologyValidationError(f"RelationshipType spec must define 'primaryKey' in {file_path}")
        elif kind == "PropertyGraph":
            if "graphName" not in spec:
                raise OntologyValidationError(f"PropertyGraph spec must define 'graphName' in {file_path}")
            if "nodes" not in spec:
                raise OntologyValidationError(f"PropertyGraph spec must define 'nodes' in {file_path}")
            if "edges" not in spec:
                raise OntologyValidationError(f"PropertyGraph spec must define 'edges' in {file_path}")


class DiffEngine:
    """Compares new schema states with historical/canonical schemas to classify compatibility."""
    
    @staticmethod
    def diff_object_type(existing: Dict[str, Any], incoming: Dict[str, Any]) -> SchemaDiff:
        diff_summary = {"added_properties": [], "removed_properties": [], "type_changes": []}
        
        exist_spec = existing.get("spec", {})
        in_spec = incoming.get("spec", {})
        
        exist_props = exist_spec.get("properties", {})
        in_props = in_spec.get("properties", {})
        
        # Check for added and type changes
        for prop_name, prop_def in in_props.items():
            if prop_name not in exist_props:
                diff_summary["added_properties"].append(prop_name)
            else:
                exist_type = exist_props[prop_name].get("type")
                incoming_type = prop_def.get("type")
                if exist_type != incoming_type:
                    diff_summary["type_changes"].append({
                        "property": prop_name,
                        "from": exist_type,
                        "to": incoming_type
                    })
                    
        # Check for removed properties
        for prop_name in exist_props.keys():
            if prop_name not in in_props:
                diff_summary["removed_properties"].append(prop_name)
                
        # Classify compatibility
        if diff_summary["removed_properties"] or diff_summary["type_changes"]:
            change_type = "BREAKING"
        elif diff_summary["added_properties"]:
            change_type = "COMPATIBLE"
        else:
            change_type = "ADDITIVE"  # Identical, or no semantic changes
            
        return SchemaDiff(change_type, diff_summary)


class SpannerRegistryManager:
    """Manages raw registry and canonical schema metadata in Google Cloud Spanner."""
    
    def __init__(self, instance_id: str = None, database_id: str = None, mock: bool = True):
        self.mock = mock
        self.instance_id = instance_id
        self.database_id = database_id
        self.mock_db: Dict[str, Dict[str, Any]] = {
            "raw_yaml_registry": {},
            "canonical_object_types": {},
            "canonical_relationship_types": {},
            "schema_change_log": {},
            "deployment_audit": {}
        }
        if not mock:
            self.client = spanner.Client()
            self.instance = self.client.instance(instance_id)
            self.database = self.instance.database(database_id)

    def get_existing_canonical_object(self, name: str) -> Dict[str, Any]:
        if self.mock:
            record = self.mock_db["canonical_object_types"].get(name)
            if record:
                return json.loads(record.get("full_yaml", "{}"))
            return {}
        
        # Fetch from Google Spanner
        try:
            with self.database.snapshot() as snapshot:
                results = snapshot.execute_sql(
                    "SELECT yaml_hash FROM canonical_object_types WHERE object_type_id = @name",
                    params={"name": name},
                    param_types={"name": spanner.param_types.STRING}
                )
                rows = list(results)
                if rows:
                    yaml_hash = rows[0][0]
                    # Fetch raw yaml
                    yaml_results = snapshot.execute_sql(
                        "SELECT yaml_content FROM raw_yaml_registry WHERE yaml_hash = @hash",
                        params={"hash": yaml_hash},
                        param_types={"hash": spanner.param_types.STRING}
                    )
                    yaml_rows = list(yaml_results)
                    if yaml_rows:
                        return yaml.safe_load(yaml_rows[0][0])
        except Exception as e:
            print(f"[Warning] Failed to query Spanner database: {e}. Falling back to dry-run logic.")
        return {}

    def insert_raw_registry(self, yaml_hash: str, yaml_content: str, source_system: str) -> None:
        if self.mock:
            self.mock_db["raw_yaml_registry"][yaml_hash] = {
                "yaml_hash": yaml_hash,
                "yaml_content": yaml_content,
                "source_system": source_system,
                "status": "PENDING"
            }
            return
            
        def _write(transaction):
            transaction.insert_or_update(
                table="raw_yaml_registry",
                columns=["yaml_hash", "yaml_content", "ingestion_timestamp", "source_system", "status"],
                values=[[yaml_hash, yaml_content, spanner.COMMIT_TIMESTAMP, source_system, "PROCESSED"]]
            )
        self.database.run_in_transaction(_write)

    def write_canonical_object(self, object_type_id: str, yaml_hash: str, name: str, table_name: str, primary_key: str, properties: Dict[str, Any]) -> None:
        if self.mock:
            self.mock_db["canonical_object_types"][object_type_id] = {
                "object_type_id": object_type_id,
                "yaml_hash": yaml_hash,
                "name": name,
                "table_name": table_name,
                "primary_key_field": primary_key,
                "attributes": json.dumps(properties),
                "status": "ACTIVE"
            }
            return

        def _write(transaction):
            transaction.insert_or_update(
                table="canonical_object_types",
                columns=["object_type_id", "yaml_hash", "api_version", "kind", "name", "schema_version", "table_name", "primary_key_field", "attributes", "status", "last_updated"],
                values=[[object_type_id, yaml_hash, "v1", "ObjectType", name, "1.0", table_name, primary_key, json.dumps(properties), "ACTIVE", spanner.COMMIT_TIMESTAMP]]
            )
        self.database.run_in_transaction(_write)

    def log_schema_change(self, entity_id: str, entity_type: str, change_type: str, diff_summary: Dict[str, Any]) -> None:
        change_id = hashlib.md5(f"{entity_id}-{change_type}-{json.dumps(diff_summary)}".encode('utf-8')).hexdigest()
        if self.mock:
            self.mock_db["schema_change_log"][change_id] = {
                "change_id": change_id,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "change_type": change_type,
                "diff_summary": json.dumps(diff_summary)
            }
            return

        def _write(transaction):
            transaction.insert_or_update(
                table="schema_change_log",
                columns=["change_id", "entity_id", "entity_type", "change_type", "diff_summary", "created_at"],
                values=[[change_id, entity_id, entity_type, change_type, json.dumps(diff_summary), spanner.COMMIT_TIMESTAMP]]
            )
        self.database.run_in_transaction(_write)


class Orchestrator:
    """High-level deployment and validation coordinator for the ontology pipeline."""
    
    def __init__(self, registry_manager: SpannerRegistryManager):
        self.registry = registry_manager

    def validate_source_dir(self, source_dir: str) -> List[Tuple[str, Dict[str, Any]]]:
        if not os.path.exists(source_dir):
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
            
        validated_files = []
        for file_name in os.listdir(source_dir):
            if file_name.endswith('.yaml') or file_name.endswith('.yml'):
                path = os.path.join(source_dir, file_name)
                data = OntologyParser.load_yaml(path)
                OntologyParser.validate_structure(data, path)
                validated_files.append((path, data))
        return validated_files

    def run_plan(self, source_dir: str) -> Dict[str, Any]:
        """Runs the validation, diffing, and plans the DDL generation / migrations."""
        validated_files = self.validate_source_dir(source_dir)
        plan_summary = {
            "validated_entities": [],
            "schema_diffs": {},
            "status": "VALID",
            "spanner_ddl_changes_needed": False
        }

        for path, data in validated_files:
            kind = data.get("kind")
            name = data["metadata"]["name"]
            plan_summary["validated_entities"].append(f"{kind}:{name}")
            
            if kind == "ObjectType":
                existing = self.registry.get_existing_canonical_object(name)
                if existing:
                    diff = DiffEngine.diff_object_type(existing, data)
                    plan_summary["schema_diffs"][name] = {
                        "change_type": diff.change_type,
                        "diff": diff.diff_summary
                    }
                    if diff.change_type != "ADDITIVE":
                        plan_summary["spanner_ddl_changes_needed"] = True
                else:
                    plan_summary["schema_diffs"][name] = {
                        "change_type": "ADDITIVE",
                        "diff": {"info": "New entity type added"}
                    }
                    plan_summary["spanner_ddl_changes_needed"] = True

        return plan_summary

    def run_apply(self, source_dir: str) -> None:
        """Processes files, logs raw state, calculates diffs, writes updates to registry."""
        validated_files = self.validate_source_dir(source_dir)
        
        for path, data in validated_files:
            # Hash calculation
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            yaml_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            name = data["metadata"]["name"]
            kind = data["metadata"].get("kind", data.get("kind"))

            # Log to Raw Registry
            self.registry.insert_raw_registry(yaml_hash, content, source_system="git-pipeline")
            
            if kind == "ObjectType":
                existing = self.registry.get_existing_canonical_object(name)
                change_type = "ADDITIVE"
                diff_sum = {"info": "New entity type added"}
                
                if existing:
                    diff = DiffEngine.diff_object_type(existing, data)
                    change_type = diff.change_type;
                    diff_sum = diff.diff_summary

                # Register canonical state
                self.registry.write_canonical_object(
                    object_type_id=name,
                    yaml_hash=yaml_hash,
                    name=name,
                    table_name=data["spec"]["tableName"],
                    primary_key=data["spec"]["primaryKey"],
                    properties=data["spec"]["properties"]
                )
                
                # Log diff history
                self.registry.log_schema_change(name, "OBJECT", change_type, diff_sum)


def main():
    parser = argparse.ArgumentParser(description="Ontology to Graph Orchestrator and Compiler")
    parser.add_argument("--action", choices=["validate", "plan", "apply"], required=True, help="Orchestration stage to run")
    parser.add_argument("--source", required=True, help="Directory containing ontology YAML configurations")
    parser.add_argument("--instance", help="GCP Spanner Instance ID")
    parser.add_argument("--database", help="GCP Spanner Database ID")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform run locally without GCP Spanner connection")

    args = parser.parse_args()

    # Determine if we should mock Spanner based on parameters/flags
    mock_mode = args.dry_run or not (args.instance and args.database)
    if mock_mode:
        print("[Info] Running in DRY-RUN / MOCK mode. Spanner operations will be simulated.")
        
    registry_manager = SpannerRegistryManager(args.instance, args.database, mock=mock_mode)
    orchestrator = Orchestrator(registry_manager)

    try:
        if args.action == "validate":
            print(f"Validating ontology specifications in: {args.source}")
            orchestrator.validate_source_dir(args.source)
            print("Success: All YAML definitions are structurally valid.")
            
        elif args.action == "plan":
            print(f"Generating transition plan for: {args.source}")
            plan = orchestrator.run_plan(args.source)
            print(json.dumps(plan, indent=2))
            
        elif args.action == "apply":
            print(f"Applying schema and metadata changes from: {args.source}")
            orchestrator.run_apply(args.source)
            print("Apply completed successfully.")

    except Exception as e:
        print(f"Error during orchestrator execution: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
