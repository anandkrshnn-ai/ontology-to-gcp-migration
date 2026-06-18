# Disaster Recovery (DR) and Rollback Playbook

While the V7 Framework guarantees architectural robustness via exponential backoff and DLQs, catastrophic failures during the production cutover phase (Phase 5) require a well-documented rollback path. This document defines the tabletop exercises and runbooks needed to "un-sever" the connectors and fail back to Palantir safely.

## Rollback Principles
1. **Zero Data Loss:** BigQuery remains immutable.
2. **Re-attach the Bridge:** The goal of rollback is to restore the Palantir Cloud Storage data sink and point the front-end DNS back to the native Palantir API.
3. **No-Fault Abort:** Rollbacks are expected and practiced.

---

## 🚨 Tabletop Scenario: The "Traverse Explode"

**The Scenario:** 
During Phase 5 cutover, a legacy React frontend application executes an unexpected, multi-hop link traverse (e.g., Package -> Flights -> Aircraft -> Maintenance Logs). Because the `ontology_api_proxy` lacks a pre-calculated Materialized View for this exact 4-hop chain, BigQuery performs a massive cross-join UNNEST, triggering an OOM (Out of Memory) error or spiking the slot quota, crashing the proxy.

### Step 1: Detect and Declare
*   **Trigger:** The Cloud Monitoring Dashboard fires an alert on `Ontology Proxy Latency > 2000ms` and `BigQuery Slot Usage > 100% Allocation`.
*   **Action:** The Migration Lead declares a "Traverse Explode" failure and initiates the Rollback Playbook.

### Step 2: Un-Sever the DNS Routing (Frontend Reversion)
Currently, `api.enterprise.com/ontology` routes to the Cloud Run `ontology_api_proxy`. 
*   **Action:** Run the pre-staged Terraform reversal script to immediately swap the DNS routing back to the native Palantir API endpoint.
```bash
terraform apply -var="proxy_target=palantir" -auto-approve
```
*   *Time to resolution:* < 2 minutes. The frontend immediately resumes querying Palantir.

### Step 3: Un-Sever the Sync Connectors (Data Reversion)
During cutover, the upstream data pipelines were repointed to stream directly to BigQuery/PubSub.
*   **Action:** Enable the dormant Palantir Cloud Storage data connectors. 
*   **Action:** Flush the PubSub DLQ to ensure any stuck messages during the crash are routed back to the Palantir ingest queue.
*   *Time to resolution:* < 10 minutes.

### Step 4: Root Cause & Fix
*   Once stable on Palantir, analyze the proxy logs to identify the unsupported multi-hop query.
*   **Fix:** Build the missing BigQuery Materialized View in `dataform/`, redeploy the proxy with the new routing map, and schedule another cutover window.

---

## 🚨 Tabletop Scenario: Silent Semantic Corruption

**The Scenario:**
A complex, custom pipeline logic built in Palantir Contour was poorly translated to Dataform `.sqlx`. The CI/CD `pyspark_hash_validator.py` catches the semantic discrepancy (the BigQuery dataset hash does not match the Palantir dataset hash), but due to an unauthorized manual override, the pipeline is pushed to production. 

### Step 1: Detect and Declare
*   **Trigger:** Analysts report downstream dashboard KPIs (e.g., Revenue per Flight) are off by 5%. 
*   **Action:** Check the Semantic Gating Logs in the Observability Dashboard. Identify the manual override.

### Step 2: Freeze BigQuery
*   **Action:** Immediately revoke write access to the corrupted BigQuery dataset.

### Step 3: Rollback Dataform State
*   **Action:** Use Git to revert the `.sqlx` logic to the last known good commit.
*   **Action:** Re-run the Dataform pipeline with full table replacement (`--full-refresh`) to purge the corrupted data and rebuild from raw Bronze.

### Step 4: Auditor Notification
*   **Action:** Provide the IAM logs showing the unauthorized CI/CD bypass to the governance team.

---

> [!CAUTION]
> These runbooks must be executed in a Staging/Sandbox environment quarterly. Auditors will require proof of tabletop completion before certifying the Phase 5 cutover.
