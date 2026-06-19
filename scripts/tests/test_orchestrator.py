import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import shutil
import tempfile
import unittest
import yaml
from scripts.orchestrator import OntologyParser, DiffEngine, SpannerRegistryManager, Orchestrator, OntologyValidationError

class TestOntologyParser(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_validate_structure_valid(self):
        yaml_content = """
apiVersion: v1
kind: ObjectType
metadata:
  name: test_object
spec:
  primaryKey: id
  tableName: test_table
  properties:
    id:
      type: string
    name:
      type: string
"""
        file_path = os.path.join(self.test_dir, "valid.yaml")
        with open(file_path, "w") as f:
            f.write(yaml_content)
        
        data = OntologyParser.load_yaml(file_path)
        # Should not raise exception
        OntologyParser.validate_structure(data, file_path)

    def test_validate_structure_invalid_kind(self):
        yaml_content = """
apiVersion: v1
kind: InvalidKind
metadata:
  name: test_object
spec:
  primaryKey: id
"""
        file_path = os.path.join(self.test_dir, "invalid.yaml")
        with open(file_path, "w") as f:
            f.write(yaml_content)
            
        data = OntologyParser.load_yaml(file_path)
        with self.assertRaises(OntologyValidationError):
            OntologyParser.validate_structure(data, file_path)


class TestDiffEngine(unittest.TestCase):
    def test_diff_additive_identical(self):
        existing = {
            "spec": {
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"}
                }
            }
        }
        incoming = {
            "spec": {
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"}
                }
            }
        }
        diff = DiffEngine.diff_object_type(existing, incoming)
        self.assertEqual(diff.change_type, "ADDITIVE")
        self.assertEqual(diff.diff_summary["added_properties"], [])

    def test_diff_compatible_add_property(self):
        existing = {
            "spec": {
                "properties": {
                    "id": {"type": "string"}
                }
            }
        }
        incoming = {
            "spec": {
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"}
                }
            }
        }
        diff = DiffEngine.diff_object_type(existing, incoming)
        self.assertEqual(diff.change_type, "COMPATIBLE")
        self.assertIn("description", diff.diff_summary["added_properties"])

    def test_diff_breaking_remove_property(self):
        existing = {
            "spec": {
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"}
                }
            }
        }
        incoming = {
            "spec": {
                "properties": {
                    "id": {"type": "string"}
                }
            }
        }
        diff = DiffEngine.diff_object_type(existing, incoming)
        self.assertEqual(diff.change_type, "BREAKING")
        self.assertIn("name", diff.diff_summary["removed_properties"])


class TestOrchestratorFlows(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Write valid object YAML
        self.obj_yaml = """
apiVersion: v1
kind: ObjectType
metadata:
  name: hub_location
spec:
  primaryKey: hub_id
  tableName: hub_location
  properties:
    hub_id:
      type: string
    name:
      type: string
"""
        with open(os.path.join(self.test_dir, "hub.yaml"), "w") as f:
            f.write(self.obj_yaml)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_orchestrator_validate_and_apply(self):
        registry = SpannerRegistryManager(mock=True)
        orchestrator = Orchestrator(registry)
        
        # Test validate
        files = orchestrator.validate_source_dir(self.test_dir)
        self.assertEqual(len(files), 1)
        
        # Test apply (write to mock Spanner)
        orchestrator.run_apply(self.test_dir)
        
        # Assert object was recorded in raw registry
        self.assertTrue(len(registry.mock_db["raw_yaml_registry"]) > 0)
        # Assert object was recorded in canonical object types
        self.assertIn("hub_location", registry.mock_db["canonical_object_types"])
