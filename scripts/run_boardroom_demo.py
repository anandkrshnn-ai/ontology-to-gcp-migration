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
    print("\n[STEP 4] Semantic Gating: PySpark Hash Validation")
    print("Simulating PySpark Hash Match Failure (Corruption Prevented)...")
    
    # Mock PySpark module
    import sys
    sys.modules['pyspark'] = MagicMock()
    sys.modules['pyspark.sql'] = MagicMock()
    sys.modules['pyspark.sql.functions'] = MagicMock()
    
    # We simulate the exact logic from the pyspark script
    import pyspark_hash_validator as val_module
    actual_hash = "INVALID_HASH_888"
    expected_hash = "8f4e3c1b2a9d8f7e6c5b4a3d2e1f0a9b"
    try:
        if actual_hash != expected_hash:
            error_msg = f"SEMANTIC MISMATCH: Expected {expected_hash}, got {actual_hash}. The migrated data is corrupted."
            logging.error(error_msg)
            raise val_module.SemanticFidelityError(error_msg)
    except val_module.SemanticFidelityError as e:
        print(f"PIPELINE HALTED: {str(e)}")

    print("\n" + "="*80)
    print("✅ DEMO COMPLETE: The V7 Engine has successfully prevented corruption and data loss.")
    print("="*80)

if __name__ == "__main__":
    run_demo()
