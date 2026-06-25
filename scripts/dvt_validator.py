#!/usr/bin/env python3
"""
GCP Professional Services Data Validator (DVT) Wrapper
------------------------------------------------------
This script acts as a pipeline orchestration helper for the Google Cloud
Professional Services Data Validator (DVT). It parses the local Palantir
Ontology definition files, maps them to database schemas, registers DVT
connections (FileSystem, Spanner, BigQuery), and executes data validation checks.
"""

import os
import sys
import argparse
import logging
import subprocess
import yaml
from typing import Dict, Any, List, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Ensure we can import from orchestrator
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from scripts.orchestrator import OntologyParser, OntologyValidationError
except ImportError:
    # Fallback to local import if run differently
    from orchestrator import OntologyParser, OntologyValidationError

class DVTValidationError(Exception):
    """Exception raised when validation checks fail or have mismatches."""
    pass

class DVTValidator:
    def __init__(self, 
                 ontology_dir: str = "ontology", 
                 project_id: str = "tzwkexo-re-ai-lab",
                 spanner_instance: str = "fedex-free-poc-instance",
                 spanner_database: str = "fedex_poc_sandbox",
                 bq_dataset: str = "palantir_ontology_dev_unique",
                 dry_run: bool = False):
        self.ontology_dir = ontology_dir
        self.project_id = project_id
        self.spanner_instance = spanner_instance
        self.spanner_database = spanner_database
        self.bq_dataset = bq_dataset
        self.dry_run = dry_run
        self.test_data_dir = os.path.join(ontology_dir, "test_data")

    def discover_entities(self) -> List[Dict[str, Any]]:
        """Parses ontology folder and returns ObjectType specs."""
        entities = []
        if not os.path.exists(self.ontology_dir):
            logging.error(f"Ontology directory not found: {self.ontology_dir}")
            return entities

        for file_name in os.listdir(self.ontology_dir):
            if file_name.endswith('.yaml') or file_name.endswith('.yml'):
                path = os.path.join(self.ontology_dir, file_name)
                try:
                    data = OntologyParser.load_yaml(path)
                    OntologyParser.validate_structure(data, path)
                    data = OntologyParser.normalise(data)
                    if data.get("kind") == "ObjectType":
                        entities.append(data)
                except Exception as e:
                    logging.warning(f"Skipping {file_name} due to parsing error: {e}")
        return entities

    def get_connection_commands(self) -> List[Tuple[str, List[str]]]:
        """Generates DVT connection registration commands."""
        commands = []
        
        # 1. FileSystem (Local CSVs / GCS Landing Zone)
        fs_cmd = [
            "data-validation", "connections", "add",
            "--connection-name", "palantir_csv_source",
            "FileSystem",
            "--path", os.path.abspath(self.test_data_dir)
        ]
        commands.append(("FileSystem Connection", fs_cmd))

        # 2. Spanner Connection
        spanner_cmd = [
            "data-validation", "connections", "add",
            "--connection-name", "gcp_spanner_target",
            "Spanner",
            "--project-id", self.project_id,
            "--instance-id", self.spanner_instance,
            "--database-id", self.spanner_database
        ]
        commands.append(("Spanner Connection", spanner_cmd))

        # 3. BigQuery Connection
        bq_cmd = [
            "data-validation", "connections", "add",
            "--connection-name", "gcp_bq_target",
            "BigQuery",
            "--project-id", self.project_id
        ]
        commands.append(("BigQuery Connection", bq_cmd))

        return commands

    def setup_connections(self) -> bool:
        """Configures all DVT connections by executing commands."""
        logging.info("--- Registering DVT Connections ---")
        commands = self.get_connection_commands()
        
        success = True
        for name, cmd in commands:
            logging.info(f"Setting up: {name}")
            if self.dry_run:
                logging.info(f"[Dry-Run] Executing: {' '.join(cmd)}")
            else:
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    logging.info(f"Success registering {name}: {res.stdout.strip()}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"Failed to register {name}: {e.stderr.strip()}")
                    # Sometimes connection already exists, which is fine
                    if "already exists" in e.stderr.lower() or "already registered" in e.stderr.lower():
                        logging.info(f"Connection {name} is already registered. Proceeding.")
                    else:
                        success = False
        return success

    def generate_validation_yaml(self, mode: str, entity: Dict[str, Any], val_type: str) -> Dict[str, Any]:
        """Generates the dictionary representing DVT validation YAML."""
        spec = entity["spec"]
        table_name = spec["tableName"]
        properties = spec.get("properties", {})

        # Resolve source and target table identities
        if mode == "fs-to-spanner":
            source_conn = "palantir_csv_source"
            target_conn = "gcp_spanner_target"
            source_table = table_name
            target_table = table_name
        elif mode == "spanner-to-bq":
            source_conn = "gcp_spanner_target"
            target_conn = "gcp_bq_target"
            source_table = table_name
            target_table = f"{self.bq_dataset}.{table_name}"
        elif mode == "fs-to-bq":
            source_conn = "palantir_csv_source"
            target_conn = "gcp_bq_target"
            source_table = table_name
            target_table = f"{self.bq_dataset}.{table_name}"
        else:
            raise ValueError(f"Unknown validation mode: {mode}")

        if val_type == "table_count":
            return {
                "source_conn": source_conn,
                "target_conn": target_conn,
                "type": "Table",
                "schema_name": None,
                "table_name": source_table,
                "target_schema_name": None,
                "target_table_name": target_table,
                "threshold": 0.0,
                "filters": [],
                "labels": []
            }
        elif val_type == "column_agg":
            aggregates = []
            # Default table count aggregate
            aggregates.append({
                "field_alias": "count",
                "source_column": None,
                "target_column": None,
                "type": "count"
            })
            for col_name, col_info in properties.items():
                col_type = col_info.get("type", "STRING")
                # Count check is valid for all columns
                aggregates.append({
                    "field_alias": f"count__{col_name}",
                    "source_column": col_name,
                    "target_column": col_name,
                    "type": "count"
                })
                # If numeric, add sum, min, max
                col_type_upper = col_type.upper()
                if any(x in col_type_upper for x in ["INT", "NUMERIC", "FLOAT", "DOUBLE", "DECIMAL", "REAL"]):
                    aggregates.append({
                        "field_alias": f"sum__{col_name}",
                        "source_column": col_name,
                        "target_column": col_name,
                        "type": "sum"
                    })
                    aggregates.append({
                        "field_alias": f"min__{col_name}",
                        "source_column": col_name,
                        "target_column": col_name,
                        "type": "min"
                    })
                    aggregates.append({
                        "field_alias": f"max__{col_name}",
                        "source_column": col_name,
                        "target_column": col_name,
                        "type": "max"
                    })
            return {
                "source_conn": source_conn,
                "target_conn": target_conn,
                "type": "Column",
                "schema_name": None,
                "table_name": source_table,
                "target_schema_name": None,
                "target_table_name": target_table,
                "aggregates": aggregates,
                "threshold": 0.0,
                "filters": [],
                "labels": []
            }
        else:
            raise ValueError(f"Unknown validation type: {val_type}")

    def run_validation(self, mode: str = "fs-to-spanner") -> Dict[str, Any]:
        """
        Runs validations for discovered entities.
        Modes:
          - 'fs-to-spanner': Compare local CSVs vs Spanner
          - 'spanner-to-bq': Compare Spanner vs BigQuery
          - 'fs-to-bq': Compare local CSVs vs BigQuery
        """
        entities = self.discover_entities()
        if not entities:
            logging.error("No valid ObjectType entities found to validate.")
            return {"status": "NO_ENTITIES", "results": []}

        logging.info(f"--- Running DVT Validations (Mode: {mode}) ---")
        validation_results = []
        overall_success = True

        # Ensure dvt_configs/ directory exists in the workspace
        dvt_configs_dir = os.path.abspath(os.path.join(self.ontology_dir, '..', 'dvt_configs'))
        os.makedirs(dvt_configs_dir, exist_ok=True)

        for entity in entities:
            name = entity["metadata"]["name"]
            spec = entity["spec"]
            table_name = spec["tableName"]

            # Generate validation configurations
            table_yaml = self.generate_validation_yaml(mode, entity, "table_count")
            column_yaml = self.generate_validation_yaml(mode, entity, "column_agg")

            table_yaml_path = os.path.join(dvt_configs_dir, f"{table_name}_table_count.yaml")
            column_yaml_path = os.path.join(dvt_configs_dir, f"{table_name}_column_agg.yaml")

            # Write configurations to local files (allowing inspection/reuse)
            with open(table_yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(table_yaml, f, default_flow_style=False)
            with open(column_yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(column_yaml, f, default_flow_style=False)

            # Build command using DVT run-config CLI
            table_cmd = ["data-validation", "run-config", "-c", table_yaml_path]
            column_cmd = ["data-validation", "run-config", "-c", column_yaml_path]

            # Run count validation
            logging.info(f"Running table row count validation for {name} ({table_name}) via generated config {os.path.basename(table_yaml_path)}...")
            count_ok, count_output = self._execute_dvt_command(table_cmd, "table_count", table_name)
            
            # Run column validation
            logging.info(f"Running column aggregation validation for {name} ({table_name}) via generated config {os.path.basename(column_yaml_path)}...")
            col_ok, col_output = self._execute_dvt_command(column_cmd, "column_agg", table_name)

            entity_success = count_ok and col_ok
            if not entity_success:
                overall_success = False

            validation_results.append({
                "entity": name,
                "table_name": table_name,
                "table_count_validation": "SUCCESS" if count_ok else "FAILED",
                "column_validation": "SUCCESS" if col_ok else "FAILED",
                "count_output": count_output,
                "column_output": col_output
            })

        status = "SUCCESS" if overall_success else "FAILED"
        return {"status": status, "results": validation_results}

    def _execute_dvt_command(self, cmd: List[str], val_type: str, table: str) -> Tuple[bool, str]:
        """Executes a DVT CLI command and returns success flag and stdout snippet."""
        if self.dry_run:
            logging.info(f"[Dry-Run] CLI Command: {' '.join(cmd)}")
            # Generate deterministic mock output for dry-run
            if val_type == "table_count":
                mock_out = f"Validation Success! {table} row counts match.\nSource count: 5, Target count: 5."
            else:
                mock_out = f"Validation Success! Columns for {table} successfully validated."
            return True, mock_out
        
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            # DVT prints a tabular validation report. We search for fail/mismatch markers
            output = res.stdout
            lower_out = output.lower()
            
            # Look for mismatch or failure indicators in DVT output tabular format
            is_valid = True
            if "fail" in lower_out or "mismatch" in lower_out or "difference" in lower_out:
                is_valid = False
                
            return is_valid, output
        except subprocess.CalledProcessError as e:
            # Process failed due to configuration or network issue
            logging.error(f"DVT Process execution failed for {table}: {e.stderr}")
            return False, f"CLI Error: {e.stderr}"
        except FileNotFoundError:
            logging.error("data-validation CLI utility not found in PATH. Make sure google-pso-data-validator is installed.")
            return False, "data-validation utility not installed."

def main():
    parser = argparse.ArgumentParser(description="Ontology to GCP Data Validation Tool pipeline manager")
    parser.add_argument("--action", choices=["connections", "validate", "all"], default="all",
                        help="Action to perform: register connections, run validation, or both")
    parser.add_argument("--ontology-dir", default="ontology", help="Path to ontology YAML files")
    parser.add_argument("--mode", choices=["fs-to-spanner", "spanner-to-bq", "fs-to-bq"], default="fs-to-spanner",
                        help="Validation mapping mode")
    parser.add_argument("--project", default="tzwkexo-re-ai-lab", help="GCP Project ID")
    parser.add_argument("--spanner-instance", default="fedex-free-poc-instance", help="Spanner Instance ID")
    parser.add_argument("--spanner-database", default="fedex_poc_sandbox", help="Spanner Database ID")
    parser.add_argument("--bq-dataset", default="palantir_ontology_dev_unique", help="Target BigQuery dataset name")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Print commands instead of executing them")

    args = parser.parse_args()

    validator = DVTValidator(
        ontology_dir=args.ontology_dir,
        project_id=args.project,
        spanner_instance=args.spanner_instance,
        spanner_database=args.spanner_database,
        bq_dataset=args.bq_dataset,
        dry_run=args.dry_run
    )

    success = True
    if args.action in ["connections", "all"]:
        conn_success = validator.setup_connections()
        if not conn_success:
            success = False

    if args.action in ["validate", "all"]:
        results = validator.run_validation(mode=args.mode)
        print("\n=== Validation Summary Report ===")
        print(f"Overall Status: {results['status']}")
        for r in results["results"]:
            print(f"- Entity: {r['entity']} ({r['table_name']})")
            print(f"  Row Count Check: {r['table_count_validation']}")
            print(f"  Column Check   : {r['column_validation']}")
            if r['table_count_validation'] == "FAILED" or r['column_validation'] == "FAILED":
                print(f"  Details: {r['count_output'] or r['column_output']}")
                success = False
        print("=================================\n")

    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
