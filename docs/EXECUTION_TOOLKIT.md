# The V7 Execution Toolkit

This toolkit operationalizes the V7 Migration Framework. It contains the engineering runbooks and automation scripts required to extract metadata, convert schemas, and intercept API calls. 

Using these tools ensures the migration is automated, auditable, and prevents the "Federated Lock-in" trap.

---

## 1. Metadata Scraper & Security Egress
**Script:** `scripts/metadata_scraper_to_policy_tags.py`

**Purpose:** 
Palantir's security markings (row/column access control) are proprietary. This tool connects to the Palantir API, extracts hierarchical markings (e.g., `Confidential > Finance`), and flattens them into GCP Dataplex Taxonomies via auto-generated Terraform.

**Usage:**
```bash
# Run the scraper against a specific Palantir Dataset RID
python scripts/metadata_scraper_to_policy_tags.py \
  --dataset_id ri.foundry.main.dataset.1234abcd \
  --project_id prj-data-governance \
  --output generated_policy_tags.tf
```

**Expected Output (`generated_policy_tags.tf`):**
The script generates native Terraform mapping the hierarchy:
```hcl
resource "google_data_catalog_policy_tag" "finance" {
  taxonomy     = google_data_catalog_taxonomy.finance_taxonomy.id
  display_name = "Finance"
  parent_policy_tag = google_data_catalog_policy_tag.confidential.id
}
```

---

## 2. Schema & Incremental Logic Converter
**Script:** `scripts/schema_to_dataform_converter.py`

**Purpose:** 
Translating schema is easy; translating logic is hard. This tool converts Palantir dataset schemas into native GCP Dataform `.sqlx` definitions. Crucially, it parses Palantir's `APPEND` build types and translates them into Dataform `incremental()` block logic and BigQuery partition keys.

**Usage:**
```bash
# Provide the exported Palantir JSON schema
python scripts/schema_to_dataform_converter.py \
  --input exports/palantir_schema_flight_telemetry.json \
  --output_dir dataform/definitions/
```

**Expected Output (`flight_telemetry.sqlx`):**
```sql
config {
  type: "incremental",
  bigquery: {
    partitionBy: "DATE(event_timestamp)"
  }
}
-- Automatically generated incremental block
${when(incremental(), `
  WHERE event_timestamp > (SELECT MAX(event_timestamp) FROM ${self()})
`)}
```

---

## 3. The Ontology API Proxy (The "Severed Bridge")
**Script:** `scripts/ontology_api_proxy.py`

**Purpose:** 
When we sever the BigQuery/PubSub connectors at Phase 5, any custom React/Workshop apps hitting the Palantir Ontology API will break. This FastAPI middleware proxy intercepts those calls and routes them to BigQuery.
*CRITICAL:* To prevent BigQuery nested `JSON/STRUCT` unnesting costs from exploding, this proxy maps complex link traversals directly to pre-built **Materialized Views**.

**Deployment (Cloud Run):**
```bash
# Containerize and deploy the proxy to Cloud Run
gcloud run deploy ontology-api-proxy \
  --source ./scripts/ \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="BQ_PROJECT=prj-data-gold"
```

**Example Routing:**
Frontend calls: `POST /api/v1/ontology/traverse` (Source: Package -> Target: Flights).
Proxy intercepts and executes optimized SQL:
```sql
SELECT target_flight_id, flight_status 
FROM `prj-data-gold.ontology.mv_package_flight_links` 
WHERE source_package_id = 'PKG-123'
```

---

## 4. Cost Governance (BigQuery Safeguards)
> [!WARNING]
> Do NOT allow analysts to query BigQuery as if it were Palantir's object explorer. Palantir optimizes graph traversals under the hood. BigQuery is a columnar database; unchecked nested `JSON/STRUCT` unnesting will result in massive compute bills.

To mitigate this, enforce the following rules when landing data:

1. **Clustering & Partitioning:** All converted Dataform models must implement partitioning (usually by time) and clustering (usually by Primary Keys / Link IDs).
2. **Materialized Views for Traversals:** Never perform multi-hop `JOIN` or `UNNEST` operations at runtime for interactive applications. Use the `ontology_api_proxy` to map traversals to predefined BigQuery Materialized Views (e.g., `mv_package_flight_customer_multihop`).
3. **Slot Reservations:** Configure BigQuery Slot commitments for the analytical workload to cap maximum spend. Do not use on-demand pricing for the raw Ontology layer.

---

## 5. Engineer Playbooks (Troubleshooting & Rollbacks)

### Playbook A: Metadata Scraper Fails on Security Markings
**Symptom:** The `metadata_scraper_to_policy_tags.py` script throws an API 403 or fails to map a hierarchy.
**Root Cause:** The Palantir service account token expired, or a new hierarchical level was created in Foundry that doesn't map to the Dataplex taxonomy structure.
**Resolution:**
1. Refresh the Foundry API token in the GCP Secret Manager.
2. If it's a structural failure, manually map the new Palantir tag to the `parent_policy_tag` in the generated `.tf` file before running `terraform apply`.

### Playbook A1: Auditor Mandate - Secret Manager Key Rotation
**Symptom:** Auditors require evidence of service account key rotation.
**Root Cause:** Long-lived static tokens for the Foundry API violate zero-trust compliance standards.
**Resolution:**
1. Store the `FOUNDRY_TOKEN` strictly in **Google Secret Manager**.
2. Configure a Cloud Function triggered by Cloud Scheduler every 30 days to automatically generate a new Palantir Service Account token and update the Secret Manager payload.
3. Provide auditors with the Secret Manager Audit Logs (via Cloud Logging) proving systematic 30-day rotation.

### Playbook B: Ontology Proxy Returns 400 (Traversal Not Supported)
**Symptom:** Frontend application breaks with a `400 Bad Request: Traversal not supported`.
**Root Cause:** The frontend attempted a multi-hop traversal (e.g., Package to Customer) that was not defined in the `mv_mapping` dictionary of the proxy.
**Resolution:**
1. Identify the missing traversal link in the logs.
2. Build a new BigQuery Materialized View representing that joined relationship.
3. Update `scripts/ontology_api_proxy.py` to map the traversal key to the new Materialized View and redeploy to Cloud Run.

### Playbook C: Rollback (Un-severing the Connectors)
**Symptom:** Critical business logic fails after severing the BigQuery/PubSub connectors at Phase 5.
**Rollback Procedure:**
1. Reprovision the Palantir Cloud Storage connector pointing back to the Bronze landing buckets.
2. Switch the frontend DNS endpoint from the Cloud Run `ontology_api_proxy` back to the native Foundry API endpoint.
3. Treat the BigQuery target tables as read-only until the semantic mapping issue is resolved.
