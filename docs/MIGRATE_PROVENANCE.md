# Preserving Historical Provenance (Time Travel)

Palantir Foundry maintains an immutable history of all dataset transactions (provenance). You can "rewind" to see what a dataset looked like at any point in the past. Highly regulated industries (Healthcare, Finance, Defense) rely on this for SOX, HIPAA, and ITAR compliance audits.

## 1. The Threat: Audit Failure
**The Problem:** BigQuery Time Travel only goes back 7 days by default.
**The Reality:** If auditors ask to see the state of a financial dataset as it was 6 months ago, and you moved off Foundry without implementing a long-term provenance architecture, you will fail the audit.

## 2. GCP Provenance Architecture

To replicate Foundry's immutable history, we must implement a multi-tiered approach in GCP.

### Tier 1: Short-Term Rewind (BigQuery Time Travel)
*   **Action:** BigQuery natively supports 7-day Time Travel. This covers immediate operational errors (e.g., someone accidentally `DROP`s a table or runs a bad `UPDATE`).
*   **Usage:** Use the `FOR SYSTEM_TIME AS OF` clause in Standard SQL to query the state of the data from 3 days ago.

### Tier 2: Medium-Term Audit (BigQuery Table Snapshots)
*   **Action:** For compliance checkpoints (e.g., end-of-month financial closing), use BigQuery Table Snapshots.
*   **Implementation:** Schedule a Cloud Composer DAG or BigQuery Scheduled Query to execute a `CREATE SNAPSHOT TABLE` command on critical datasets every 30 days. Snapshots are stored efficiently as delta changes.
*   **Curated Audit Views (V4 Upgrade):** Snapshots are raw and immutable. To make them legally queryable for auditors without exposing raw tables, build "Curated Audit Views." These are parameterized BigQuery views (`SELECT * FROM my_snapshot_YYYYMMDD`) accompanied by a Data Studio/Looker dashboard that allows auditors to self-serve historical queries by date without touching the underlying snapshot infrastructure.

### Tier 3: Long-Term Immutable Storage (GCS Coldline)
*   **Action:** For multi-year regulatory retention (e.g., 7-year HIPAA compliance), BigQuery storage becomes too expensive and snapshots become unwieldy.
*   **Implementation:** Schedule automated exports of BigQuery tables to Google Cloud Storage (GCS) in Parquet format.
*   **Regulatory Lifecycle & Cost Tiering (V7 Upgrade)**
You cannot simply dump all historical data into GCS Coldline. At petabyte scale, this is financially ruinous.
*   **Action:** Implement strict GCS Object Lifecycle Management tiering policies.
*   **Centralized Policy Management & Exception Governance (V7):** Do not leave tiering up to individual bucket configurations where they can drift or be overridden. You MUST use **Google Cloud Organization Policies** or centralized Terraform templates to enforce these lifecycle rules across all provenance buckets globally. To prevent exception creep, establish strict **Exception Governance**: any deviation from the global archival policy must require documented CISO sign-off and an automated expiration date.
*   **Example Tiering Policy:**
    *   **0-30 Days:** Standard Storage (High frequency query/recovery).
    *   **31-365 Days:** Nearline Storage (Infrequent access, e.g., year-end reporting).
    *   **1-3 Years:** Coldline Storage (Rare access, e.g., active legal hold).
    *   **3-7 Years:** Archive Storage (SOX/HIPAA deep freeze).
    *   **7+ Years:** Auto-Delete (GDPR right-to-be-forgotten / liability reduction).

### Curated Audit Views & Auditor Dashboards (V7 Upgrade)
Auditors (internal compliance or external regulators) do not write SQL.
*   **Action:** Do not expose raw BigQuery Snapshot tables. Create specific `Audit_Views` that mask PII (using Policy Tags) and present the historical data in a denormalized, easy-to-read format.
*   **Self-Service Dashboards:** Build templated **Looker or Data Studio (Looker Studio) Dashboards** connected directly to these `Audit_Views`. Ensure auditors can filter by date range, user ID, and action type without needing engineering support.
*   **Multi-Regulator UX Validation (V7):** Do not assume these dashboards are universally usable. You MUST conduct explicit **Beta Testing** sessions with *multiple external regulators* (e.g., FDA vs SEC vs internal legal), as formats vary globally. If an auditor cannot self-serve a compliance request within 5 minutes, the dashboard has failed. This is the only way to validate the "hours spent on audit" KPI globally.

## 3. Real-Time Provenance (Event Sourcing)
If your application requires querying the exact sequence of changes to a row over time (CDC):
*   **Action:** Do not update BigQuery rows in place (`UPDATE`). Instead, implement an Event Sourcing pattern.
*   **Implementation:** Stream all changes (Inserts, Updates, Deletes) via Pub/Sub and Dataflow into an append-only BigQuery "Ledger" table. Use BigQuery Views to calculate the "current state" on demand, while preserving the entire immutable ledger of changes underneath.
