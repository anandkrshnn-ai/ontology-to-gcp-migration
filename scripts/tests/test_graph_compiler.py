import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import unittest
from scripts.graph_compiler import GraphCompiler

class TestGraphCompiler(unittest.TestCase):
    def setUp(self):
        self.node_yaml = {
            "apiVersion": "v1",
            "kind": "ObjectType",
            "metadata": {"name": "routing_node"},
            "spec": {
                "primaryKey": "node_id",
                "tableName": "routing_node",
                "storage": {"mode": "managed_by_platform"},
                "properties": {
                    "node_id": {"type": "string", "required": True},
                    "capacity": {"type": "integer"}
                }
            }
        }
        self.graph_yaml = {
            "apiVersion": "v1",
            "kind": "PropertyGraph",
            "metadata": {"name": "logistics_graph"},
            "spec": {
                "graphName": "LogisticsGraph",
                "nodes": [
                    {
                        "objectType": "routing_node",
                        "tableName": "routing_node",
                        "key": "node_id",
                        "label": "RoutingNode"
                    }
                ],
                "edges": []
            }
        }

    def test_table_and_view_generation(self):
        compiler = GraphCompiler(compatibility_status="ADDITIVE", schema_diffs={})
        table_ddl = compiler.generate_table_ddl(self.node_yaml)
        self.assertIn("CREATE TABLE routing_node", table_ddl)
        self.assertIn("node_id STRING(MAX) NOT NULL", table_ddl)
        self.assertIn("capacity INT64", table_ddl)

        view_ddl = compiler.generate_view_ddl(self.node_yaml)
        self.assertIn("CREATE OR REPLACE VIEW v_routing_node", view_ddl)
        self.assertIn("SELECT node_id, capacity", view_ddl)

    def test_property_graph_ddl_uses_views(self):
        compiler = GraphCompiler(compatibility_status="ADDITIVE", schema_diffs={})
        graph_ddl = compiler.generate_property_graph_ddl(self.graph_yaml)
        self.assertIn("CREATE OR REPLACE PROPERTY GRAPH LogisticsGraph", graph_ddl)
        # Verify it references views
        self.assertIn("v_routing_node KEY (node_id) AS RoutingNode", graph_ddl)

    def test_breaking_change_gates_and_emits_recipe(self):
        diffs = {
            "routing_node": {
                "change_type": "BREAKING",
                "diff": {"removed_properties": ["capacity"]}
            }
        }
        compiler = GraphCompiler(compatibility_status="BREAKING", schema_diffs=diffs)
        self.assertTrue(compiler.should_gate_build())
        
        plan = compiler.compile_plan([self.node_yaml], self.graph_yaml)
        self.assertEqual(plan["status"], "BLOCKED_BREAKING")
        self.assertEqual(plan["actions"], [])
        self.assertIn("migration_recipe", plan)
        self.assertIn("manual_steps", plan["migration_recipe"])
        self.assertEqual(plan["migration_recipe"]["entity"], "routing_node")
