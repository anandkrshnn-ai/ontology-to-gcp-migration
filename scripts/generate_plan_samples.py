#!/usr/bin/env python
import os
import json
from scripts.orchestrator import SpannerRegistryManager, Orchestrator
from scripts.graph_compiler import GraphCompiler

def main():
    print("[Info] Generating compilation plan artifacts...")

    # Setup directories
    ontology_dir = "ontology"
    artifacts_dir = "artifacts"
    os.makedirs(artifacts_dir, exist_ok=True)

    # 1. Success Case: Compile the current ontology (Additive Ingestion)
    registry_success = SpannerRegistryManager(mock=True)
    orchestrator_success = Orchestrator(registry_success)
    
    # Run plan workflow on current ontology
    plan_info = orchestrator_success.run_plan(ontology_dir)
    validated_files = orchestrator_success.validate_source_dir(ontology_dir)
    
    # Segregate ObjectTypes and PropertyGraph
    yamls = [data for _, data in validated_files]
    graph_yaml = next((y for y in yamls if y.get("kind") == "PropertyGraph"), None)
    
    compiler_success = GraphCompiler(
        compatibility_status=plan_info["status"], 
        schema_diffs=plan_info["schema_diffs"]
    )
    
    success_plan = compiler_success.compile_plan(yamls, graph_yaml)
    
    success_path = os.path.join(artifacts_dir, "plan_success.json")
    with open(success_path, "w", encoding="utf-8") as f:
        json.dump(success_plan, f, indent=2)
    print(f"Success Plan written to: {success_path}")

    # 2. Blocked Case: Simulate a breaking schema evolution
    # Setup mock database pre-populated with an existing schema definition
    registry_blocked = SpannerRegistryManager(mock=True)
    
    # Pre-register 'network_routing' with a property 'capacity'
    registry_blocked.mock_db["canonical_object_types"]["network_routing"] = {
        "object_type_id": "network_routing",
        "yaml_hash": "dummy_hash",
        "full_yaml": json.dumps({
            "apiVersion": "v1",
            "kind": "ObjectType",
            "metadata": {"name": "network_routing"},
            "spec": {
                "primaryKey": "node_id",
                "tableName": "network_routing",
                "properties": {
                    "node_id": {"type": "string"},
                    "name": {"type": "string"},
                    "location_type": {"type": "string"},
                    "latitude": {"type": "double"},
                    "longitude": {"type": "double"},
                    "capacity": {"type": "integer"}, # Existing property
                    "legacy_column": {"type": "string"} # To be deleted (breaking change)
                }
            }
        })
    }
    
    # In the incoming ontology/network_routing.yaml, 'legacy_column' is deleted
    orchestrator_blocked = Orchestrator(registry_blocked)
    plan_info_blocked = orchestrator_blocked.run_plan(ontology_dir)
    
    compiler_blocked = GraphCompiler(
        compatibility_status="BREAKING", # Set breaking compatibility status
        schema_diffs=plan_info_blocked["schema_diffs"]
    )
    
    blocked_plan = compiler_blocked.compile_plan(yamls, graph_yaml)
    
    blocked_path = os.path.join(artifacts_dir, "plan_blocked.json")
    with open(blocked_path, "w", encoding="utf-8") as f:
        json.dump(blocked_plan, f, indent=2)
    print(f"Blocked Plan written to: {blocked_path}")


if __name__ == "__main__":
    main()
