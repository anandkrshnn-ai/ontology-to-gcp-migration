import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import yaml
from scripts.dvt_validator import DVTValidator, DVTValidationError

class TestDVTValidator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.ontology_dir = os.path.join(self.test_dir, "ontology")
        os.makedirs(self.ontology_dir, exist_ok=True)
        
        # Write a sample ObjectType YAML file for testing
        self.sample_entity = {
            "apiVersion": "logistics.ontology/v1",
            "kind": "ObjectType",
            "metadata": {
                "name": "Hub"
            },
            "spec": {
                "table": "hub",
                "primaryKey": ["hub_id"],
                "attributes": [
                    {"name": "hub_id", "type": "STRING(64)", "required": True},
                    {"name": "hub_name", "type": "STRING(256)", "required": True},
                    {"name": "max_throughput_tons", "type": "INT64", "required": False}
                ]
            }
        }
        self.yaml_path = os.path.join(self.ontology_dir, "hub.yaml")
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.sample_entity, f)

        self.validator = DVTValidator(
            ontology_dir=self.ontology_dir,
            project_id="test-project",
            spanner_instance="test-instance",
            spanner_database="test-database",
            bq_dataset="test_bq_dataset",
            dry_run=True
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_discover_entities(self):
        """Test parsing of ontology folder and entity discovery."""
        entities = self.validator.discover_entities()
        self.assertEqual(len(entities), 1)
        entity = entities[0]
        self.assertEqual(entity["metadata"]["name"], "Hub")
        self.assertEqual(entity["spec"]["tableName"], "hub")
        self.assertEqual(entity["spec"]["primaryKey"], "hub_id")
        self.assertIn("hub_id", entity["spec"]["properties"])
        self.assertIn("max_throughput_tons", entity["spec"]["properties"])

    def test_get_connection_commands(self):
        """Test correct generation of DVT connection commands."""
        commands = self.validator.get_connection_commands()
        self.assertEqual(len(commands), 3)
        
        # Verify filesystem connection
        fs_name, fs_cmd = commands[0]
        self.assertEqual(fs_name, "FileSystem Connection")
        self.assertIn("FileSystem", fs_cmd)
        self.assertIn("palantir_csv_source", fs_cmd)

        # Verify Spanner connection
        spanner_name, spanner_cmd = commands[1]
        self.assertEqual(spanner_name, "Spanner Connection")
        self.assertIn("Spanner", spanner_cmd)
        self.assertIn("test-project", spanner_cmd)
        self.assertIn("test-instance", spanner_cmd)
        self.assertIn("test-database", spanner_cmd)

        # Verify BigQuery connection
        bq_name, bq_cmd = commands[2]
        self.assertEqual(bq_name, "BigQuery Connection")
        self.assertIn("BigQuery", bq_cmd)
        self.assertIn("test-project", bq_cmd)

    def test_generate_validation_yaml_structure(self):
        """Test structure of programmatically generated validation YAML configs."""
        entities = self.validator.discover_entities()
        self.assertEqual(len(entities), 1)
        entity = entities[0]

        # 1. Test Table row-count validation YAML structure
        table_yaml = self.validator.generate_validation_yaml("fs-to-spanner", entity, "table_count")
        self.assertEqual(table_yaml["source_conn"], "palantir_csv_source")
        self.assertEqual(table_yaml["target_conn"], "gcp_spanner_target")
        self.assertEqual(table_yaml["type"], "Table")
        self.assertEqual(table_yaml["table_name"], "hub")
        self.assertEqual(table_yaml["target_table_name"], "hub")

        # 2. Test Column validation YAML structure (including numeric aggregates)
        column_yaml = self.validator.generate_validation_yaml("fs-to-spanner", entity, "column_agg")
        self.assertEqual(column_yaml["source_conn"], "palantir_csv_source")
        self.assertEqual(column_yaml["target_conn"], "gcp_spanner_target")
        self.assertEqual(column_yaml["type"], "Column")
        self.assertEqual(column_yaml["table_name"], "hub")
        self.assertEqual(column_yaml["target_table_name"], "hub")
        
        aggregates = column_yaml["aggregates"]
        # Basic count aggregate
        self.assertTrue(any(a["type"] == "count" and a["source_column"] is None for a in aggregates))
        # Column count aggregates
        self.assertTrue(any(a["type"] == "count" and a["source_column"] == "hub_name" for a in aggregates))
        # Column numeric sum/min/max aggregates for max_throughput_tons (INT64)
        self.assertTrue(any(a["type"] == "sum" and a["source_column"] == "max_throughput_tons" for a in aggregates))
        self.assertTrue(any(a["type"] == "min" and a["source_column"] == "max_throughput_tons" for a in aggregates))
        self.assertTrue(any(a["type"] == "max" and a["source_column"] == "max_throughput_tons" for a in aggregates))

    @patch('subprocess.run')
    def test_dry_run_subprocess_interception(self, mock_run):
        """Test that dry-run mode prevents subprocess call and yields correct results."""
        self.validator.dry_run = True
        
        # Test connection setup in dry-run
        conn_success = self.validator.setup_connections()
        self.assertTrue(conn_success)
        mock_run.assert_not_called()

        # Test validation execution in dry-run
        results = self.validator.run_validation("fs-to-spanner")
        self.assertEqual(results["status"], "SUCCESS")
        self.assertEqual(len(results["results"]), 1)
        self.assertEqual(results["results"][0]["entity"], "Hub")
        self.assertEqual(results["results"][0]["table_count_validation"], "SUCCESS")
        self.assertEqual(results["results"][0]["column_validation"], "SUCCESS")
        
        # Subprocess should not be invoked during validation run either
        mock_run.assert_not_called()

        # Confirm the generated YAML configs were written in the workspace
        dvt_configs_dir = os.path.abspath(os.path.join(self.ontology_dir, '../dvt_configs'))
        self.assertTrue(os.path.exists(dvt_configs_dir))
        self.assertTrue(os.path.exists(os.path.join(dvt_configs_dir, "hub_table_count.yaml")))
        self.assertTrue(os.path.exists(os.path.join(dvt_configs_dir, "hub_column_agg.yaml")))

if __name__ == '__main__':
    unittest.main()
