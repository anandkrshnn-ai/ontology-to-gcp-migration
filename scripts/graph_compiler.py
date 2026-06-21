#!/usr/bin/env python
from typing import Dict, Any, List

class GraphCompilerError(Exception):
    pass

class MigrationRecipe:
    """Represents a DBA-owned manual migration recipe for breaking changes."""
    def __init__(self, entity_name: str, change_type: str, steps: List[str]):
        self.entity_name = entity_name
        self.change_type = change_type
        self.steps = steps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity": self.entity_name,
            "change_type": self.change_type,
            "manual_steps": self.steps
        }


class GraphCompiler:
    """
    Compiles normalized canonical ObjectTypes and RelationshipTypes 
    into Spanner relational DDL (Tables, Views) and Spanner Graph DDL 
    (CREATE OR REPLACE PROPERTY GRAPH).
    """

    def __init__(self, compatibility_status: str, schema_diffs: Dict[str, Any]):
        self.compatibility_status = compatibility_status  # ADDITIVE, COMPATIBLE, BREAKING
        self.schema_diffs = schema_diffs

    def _normalise_spec(self, entity_yaml: Dict[str, Any]) -> Dict[str, Any]:
        """Normalises both old (properties dict) and new (attributes list) YAML formats."""
        spec = entity_yaml.get("spec", {})
        
        # Support real ontology format: attributes as list
        if "attributes" in spec and "properties" not in spec:
            props = {}
            for attr in spec.get("attributes", []):
                props[attr["name"]] = {
                    "type": attr.get("type", "STRING(MAX)"),
                    "required": attr.get("required", False)
                }
            spec = dict(spec)
            spec["properties"] = props
        
        # Support real ontology: "table" -> "tableName"
        if "table" in spec and "tableName" not in spec:
            spec = dict(spec)
            spec["tableName"] = spec["table"]
        
        # Support real ontology: primaryKey as list -> string
        pk = spec.get("primaryKey")
        if isinstance(pk, list) and len(pk) > 0:
            spec = dict(spec)
            spec["primaryKey"] = pk[0]
        
        # Force storage mode to managed_by_platform for real ontology
        if "storage" not in spec:
            spec = dict(spec)
            spec["storage"] = {"mode": "managed_by_platform"}
        
        entity_yaml = dict(entity_yaml)
        entity_yaml["spec"] = spec
        return entity_yaml

    def should_gate_build(self) -> bool:
        """
        Returns True if the build must be halted due to breaking schema evolution policies.
        Auto-blocks breaking changes from applying via automated pipelines.
        """
        return self.compatibility_status == "BREAKING"

    def generate_table_ddl(self, entity_yaml: Dict[str, Any]) -> str:
        """
        Generates Spanner physical CREATE TABLE DDL if storage mode is 'managed_by_platform'.
        Otherwise, returns empty string assuming external table creation ownership.
        """
        entity_yaml = self._normalise_spec(entity_yaml)
        spec = entity_yaml.get("spec", {})
        name = entity_yaml["metadata"]["name"]
        table_name = spec.get("tableName")
        primary_key = spec.get("primaryKey")
        properties = spec.get("properties", {})
        
        # Check if platform owns storage
        storage = spec.get("storage", {})
        mode = storage.get("mode", "view")
        
        if mode != "managed_by_platform":
            return ""

        columns = []
        for prop_name, prop_def in properties.items():
            prop_type = prop_def.get("type", "string").upper()
            # Map typical types to Spanner types
            spanner_type = "STRING(MAX)"
            if prop_type in ["DOUBLE", "FLOAT"]:
                spanner_type = "FLOAT64"
            elif prop_type in ["INTEGER", "LONG"]:
                spanner_type = "INT64"
            elif prop_type == "BOOLEAN":
                spanner_type = "BOOL"
            elif prop_type == "JSON":
                spanner_type = "JSON"
            elif prop_type in ["DATE", "NUMERIC", "INT64", "TIMESTAMP", "BOOL", "FLOAT64"]:
                spanner_type = prop_type
            elif prop_type.startswith("STRING("):
                spanner_type = prop_type

            required = " NOT NULL" if prop_def.get("required", False) else ""
            columns.append(f"    {prop_name} {spanner_type}{required}")

        ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(columns) + f"\n) PRIMARY KEY ({primary_key});"
        return ddl

    def generate_view_ddl(self, entity_yaml: Dict[str, Any]) -> str:
        """
        Generates the standard Spanner VIEW DDL for the object or relationship node surface.
        All Spanner Graph nodes/edges traverse through these views by default to isolate 
        internal schemas, perform cast-normalizations, and avoid query disruption.
        """
        entity_yaml = self._normalise_spec(entity_yaml)
        spec = entity_yaml.get("spec", {})
        name = entity_yaml["metadata"]["name"]
        table_name = spec.get("tableName")
        properties = spec.get("properties", {})
        
        # Qualify columns with table alias to satisfy strict name resolution
        selected_cols = ", ".join(f"t.{col}" for col in properties.keys())
        view_name = f"v_{table_name}"
        
        # Thin view layer abstraction over physical storage
        ddl = f"CREATE OR REPLACE VIEW {view_name} SQL SECURITY INVOKER AS \nSELECT {selected_cols} \nFROM {table_name} AS t;"
        return ddl

    def generate_property_graph_ddl(self, graph_yaml: Dict[str, Any]) -> str:
        """
        Generates the CREATE OR REPLACE PROPERTY GRAPH statement using views as primary sources.
        """
        spec = graph_yaml.get("spec", {})
        graph_name = spec.get("graphName", "LogisticsGraph")
        
        nodes_list = []
        for node in spec.get("nodes", []):
            obj_type = node["objectType"]
            table_name = node["tableName"]
            label = node["label"]
            # Graph binds directly to the view surface v_<table>
            view_name = f"v_{table_name}"
            nodes_list.append(f"    {view_name}\n      LABEL {label}")
            
        edges_list = []
        for edge in spec.get("edges", []):
            rel_type = edge["relationshipType"]
            table_name = edge["tableName"]
            label = edge["label"]
            view_name = f"v_{table_name}"
            
            source_node = edge["source"]["nodeType"]
            source_key = edge["source"]["key"]
            source_fk = edge["source"]["foreignKey"]
            
            target_node = edge["target"]["nodeType"]
            target_key = edge["target"]["key"]
            target_fk = edge["target"]["foreignKey"]
            
            # Edge connects nodes through view keys and foreign keys with unique alias
            edges_list.append(
                f"    {view_name} AS {label}\n"
                f"      SOURCE KEY ({source_fk}) REFERENCES v_{source_node} ({source_key})\n"
                f"      DESTINATION KEY ({target_fk}) REFERENCES v_{target_node} ({target_key})"
            )
            
        nodes_ddl = ",\n".join(nodes_list)
        edges_ddl = ",\n".join(edges_list)
        
        ddl = (
            f"CREATE OR REPLACE PROPERTY GRAPH {graph_name}\n"
            f"  NODE TABLES (\n{nodes_ddl}\n  )\n"
            f"  EDGE TABLES (\n{edges_ddl}\n  );"
        )
        return ddl

    def generate_migration_recipe(self) -> MigrationRecipe:
        """
        Emits a manual DBA migration recipe when a BREAKING change blocks the pipeline.
        """
        steps = [
            "1. Coordinate with downstream product owners about incoming breaking changes.",
            "2. Execute manual SQL statements to add compatability backfills or clone the Spanner tables.",
            "3. Deploy a new parallel version of the Property Graph (e.g. GraphName_v2) to allow canary cutover.",
            "4. Deprecate and safely drop the old Graph version after verify phase completion."
        ]
        broken_entities = []
        for name, details in self.schema_diffs.items():
            if details.get("change_type") == "BREAKING":
                broken_entities.append(name)
                
        return MigrationRecipe(
            entity_name=", ".join(broken_entities),
            change_type="BREAKING",
            steps=steps
        )

    def compile_plan(self, validated_yamls: List[Dict[str, Any]], graph_yaml: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compiles the entire schema set into an ordered, executable JSON plan.
        If compatibility is BREAKING, sets the status to BLOCKED_BREAKING and outputs a recipe.
        """
        if self.should_gate_build():
            recipe = self.generate_migration_recipe()
            return {
                "status": "BLOCKED_BREAKING",
                "compatibility": self.compatibility_status,
                "actions": [],
                "migration_recipe": recipe.to_dict()
            }
            
        actions = []
        
        # 1. Generate Table DDLs (only for platform managed ones)
        for y in validated_yamls:
            if y.get("kind") == "ObjectType":
                table_ddl = self.generate_table_ddl(y)
                if table_ddl:
                    actions.append(table_ddl)
                    
        # 2. Generate View DDLs (for both Objects and Relationships)
        for y in validated_yamls:
            if y.get("kind") in ["ObjectType", "RelationshipType"]:
                view_ddl = self.generate_view_ddl(y)
                if view_ddl:
                    actions.append(view_ddl)
                    
        # 3. Generate Property Graph DDL
        if graph_yaml:
            graph_ddl = self.generate_property_graph_ddl(graph_yaml)
            actions.append(graph_ddl)
            
        return {
            "status": "APPROVED",
            "compatibility": self.compatibility_status,
            "actions": actions
        }
