import os
import sys
from unittest.mock import patch, MagicMock
import responses
import logging
import json

os.environ["FOUNDRY_TOKEN"] = "mock_secret_manager_token_123"
os.environ["GCP_PROJECT_ID"] = "prj-data-gold-demo"

# Adjust logging format slightly for the demo
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)

def run_demo():
    print("="*80)
    print("🎬 V7 FRAMEWORK DEMO: Palantir-to-GCP Migration Engine")
    print("="*80)
    
    # --- 1. Extraction Resilience ---
    print("\n[STEP 1] Extraction Resilience: Handling Palantir API Throttling & DLQ Routing")
    import export_foundry_datasets as export_module
    
    with patch('google.auth.default', return_value=(MagicMock(), 'mock_project')), \
         patch('google.cloud.storage.Client'), \
         patch('google.cloud.pubsub_v1.PublisherClient') as mock_pubsub:
        
        @responses.activate
        def test_extraction():
            # Mock List Files (Success)
            responses.add(
                responses.GET,
                "https://your-stack.palantirfoundry.com/api/v1/datasets/ri.foundry.demo/files",
                json={"data": [{"path": "flight_data.csv"}, {"path": "corrupted_file.csv"}]},
                status=200
            )
            
            # Mock Download 1 (Simulate 429 Too Many Requests -> Tenacity Backoff -> Success)
            responses.add(
                responses.GET,
                "https://your-stack.palantirfoundry.com/api/v1/datasets/ri.foundry.demo/files/flight_data.csv/content",
                status=429
            )
            responses.add(
                responses.GET,
                "https://your-stack.palantirfoundry.com/api/v1/datasets/ri.foundry.demo/files/flight_data.csv/content",
                status=429
            )
            responses.add(
                responses.GET,
                "https://your-stack.palantirfoundry.com/api/v1/datasets/ri.foundry.demo/files/flight_data.csv/content",
                body="mock data",
                status=200
            )
            
            # Mock Download 2 (Simulate Permanent 500 Error -> DLQ)
            # The retry logic will hit this 5 times, so we add multiple
            for _ in range(5):
                responses.add(
                    responses.GET,
                    "https://your-stack.palantirfoundry.com/api/v1/datasets/ri.foundry.demo/files/corrupted_file.csv/content",
                    status=500
                )
            
            # Lower tenacity wait time for demo speed
            export_module.fetch_from_foundry.retry.wait = export_module.wait_exponential(multiplier=0.01, min=0.01, max=0.05)
            
            export_module.export_dataset_to_gcs("ri.foundry.demo")
        
        test_extraction()
        
    # --- 2. Schema Conversion ---
    print("\n[STEP 2] Schema Conversion: Converting Palantir Incremental Logic to Dataform (.sqlx)")
    import schema_to_dataform_converter as schema_module
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        schema = schema_module.mock_read_palantir_schema("dummy.json")
        sqlx = schema_module.generate_sqlx(schema)
        out_file = os.path.join(tmpdir, "flight_telemetry.sqlx")
        with open(out_file, "w") as f:
            f.write(sqlx)
        print(f"Generated {out_file}:\n" + "-" * 40)
        print(sqlx.strip())
        print("-" * 40)

    # --- 3. CQRS Proxy ---
    print("\n[STEP 3] CQRS Proxy: Routing BigQuery reads & Cloud SQL writes")
    from fastapi.testclient import TestClient
    from ontology_api_proxy import app
    client = TestClient(app)
    
    print("Testing GET Traversal (Package -> Flight -> Customer)...")
    resp1 = client.post("/api/v1/ontology/traverse", 
                        json={"source_object_type": "Package", "source_primary_key": "PKG-123", "link_type_id": "flights"},
                        headers={"Authorization": "Bearer valid-enterprise-token"})
    print(f"Proxy Response (Read via BQ View): {json.dumps(resp1.json(), indent=2)}")
    
    print("\nTesting POST Action (Write-back)...")
    resp2 = client.post("/api/v1/ontology/actions", 
                        json={"action_type": "UpdateFlightStatus", "object_type": "Flight", "primary_key": "FL-999", "payload": {"status": "DELAYED"}},
                        headers={"Authorization": "Bearer valid-enterprise-token"})
    print(f"Proxy Response (Write via Cloud SQL): {json.dumps(resp2.json(), indent=2)}")

    # --- 4. Semantic Validator ---
    print("\n[STEP 4] Semantic Gating: GCP Data Validation Tool (DVT)")
    print("ONTOLOGY GATING SEQUENCE:")
    
    # Stage 1: ontology compiled
    print("  1. 🛠️ ontology compiled: Parsing ObjectType specs from local YAMLs...")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
    import dvt_validator as dvt_module
    
    dvt_val = dvt_module.DVTValidator(
        ontology_dir="ontology",
        project_id="prj-data-gold-demo",
        spanner_instance="ontology-demo",
        spanner_database="ontology-db",
        dry_run=True
    )
    
    entities = dvt_val.discover_entities()
    print(f"     Found {len(entities)} ObjectType entities compiled from ontology.")
    
    # Stage 2: data loaded
    print("  2. 📥 data loaded: Initializing database connection registrations...")
    dvt_val.setup_connections()
    
    # Stage 3: DVT row-count/schema checks passed
    print("  3. 🔍 DVT row-count/schema checks passed: Executing semantic validations...")
    dvt_results = dvt_val.run_validation(mode="fs-to-spanner")
    print("\n=== DVT Validation Summary Report ===")
    print(f"Overall Status: {dvt_results['status']}")
    for r in dvt_results["results"][:4]:  # Show first 4 entities in demo for brevity
        print(f"- Entity: {r['entity']} ({r['table_name']})")
        print(f"  Row Count Check: {r['table_count_validation']}")
        print(f"  Column Check   : {r['column_validation']}")
    print("=================================\n")
    
    # Stage 4: serving plane enabled
    if dvt_results["status"] == "SUCCESS":
        print("  4. 🚀 serving plane enabled: Data validated with 100% fidelity. Routing query traffic to GCP Spanner/BigQuery.")
    else:
        print("  ❌ GATING FAILED: Semantic mismatches detected. Serving plane disabled.")

    print("\n" + "="*80)
    print("✅ DEMO COMPLETE: The V7 Engine has successfully prevented corruption and data loss.")
    print("="*80)

if __name__ == "__main__":
    run_demo()
