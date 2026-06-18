# Migrating Palantir Security Markings to BigQuery

Palantir's data-centric security model relies heavily on "Markings" (e.g., `PII`, `ITAR`, `Top Secret`). These markings propagate automatically through the pipeline lineage. Moving this to GCP requires translating these conceptual markings into concrete BigQuery security primitives.

## 1. The Threat: Compliance Breach
**The Problem:** If you migrate healthcare (HIPAA) or defense (ITAR) data without mapping Palantir Markings to GCP, the default BigQuery project-level permissions will expose restricted data to unauthorized analysts.
**The Reality:** You cannot manually apply tags to 10,000+ BigQuery columns. It must be automated.

## 2. The GCP Target State
GCP handles data-centric security via Google Cloud Data Catalog and BigQuery Policy Tags.

### A. Column-Level Security (Policy Tags)
For data classifications (like `PII_Email` or `Financial_Data`):
1.  **Taxonomy Creation:** Create a Data Catalog Taxonomy called `Palantir_Markings`.
2.  **Policy Tags:** Create Policy Tags corresponding to Palantir markings (e.g., `PII`, `PHI`).
3.  **Application:** Apply these Policy Tags to specific columns in BigQuery.
4.  **Enforcement:** BigQuery will automatically deny access to those columns unless the user has the `datacatalog.categoryFineGrainedReader` IAM role for that specific tag.

### B. Row-Level Security
For organizational or geographical restrictions (e.g., `Region_EMEA`):
1.  **Row-Level Access Policies:** Use BigQuery `CREATE ROW ACCESS POLICY`.
2.  **Implementation:** Filter rows based on a mapping table or user identity (`SESSION_USER()`).

### C. The IAM Simplification Mandate (Silent Killer Mitigation)
> [!CAUTION]
> **The Boolean ACL Impedance Mismatch:** Palantir allows incredibly complex Boolean security logic (e.g., `Role A AND (Role B OR Role C)`). GCP IAM and Dataplex are generally additive and flatter. Attempting to replicate Palantir's exact boolean permutations in GCP will result in either a security violation (over-permissioning) or broken applications (under-permissioning).

*   **Mandate Deprecation:** Do not attempt a 1:1 mapping of Boolean ACLs. 
*   **CISO Sign-Off:** Formally require the CISO or Data Governance board to sign off on collapsing complex Palantir Boolean permutations into standard, role-based GCP groups during Phase 1. Accept the deprecation of Boolean nuance in favor of a clean, auditable GCP IAM structure.

## 3. Automation & Continuous Enforcement (CI/CD)
Extracting the Marking matrix from Foundry and running a Python script once is insufficient. To prevent silent security drift:

1.  **CI/CD Integration:** The `scripts/apply_bq_policy_tags.py` utility must be integrated into your Cloud Build or GitHub Actions pipeline. Every time a new BigQuery table is deployed via Terraform or Dataform, the pipeline must enforce the policy tags.
2.  **Lineage Propagation:** Policy Tags do not automatically cascade to derived views by default in BigQuery. 
    *   **Action:** You must use Dataform `pre_operations` and `post_operations` to programmatically query the source table's policy tags and apply them to the new materialized view, replicating Foundry's automatic propagation.
3.  **Audit Logging:** Enable Cloud Audit Logs for Data Catalog and BigQuery. This ensures every read of a protected column and every modification to a policy tag is logged to Cloud Logging, creating a verifiable compliance trail for auditors.
