# GCP Landing Zone for Palantir Migration

This Terraform module provisions the necessary Google Cloud infrastructure to act as the target landing zone for a complete Palantir Foundry extraction.

## Architecture Deployed
*   **Google Cloud Storage (GCS):** `data-lake` bucket with 90-day Coldline lifecycle policies (replacing ADLS/Foundry Files).
*   **BigQuery:** `palantir_ontology` dataset (replacing the Foundry Ontology and structured datasets).
*   **Data Catalog:** `Palantir Security Markings` taxonomy for Policy Tag migration (replacing Foundry Markings).
*   **Cloud Composer:** Apache Airflow environment (replacing Foundry Build app orchestration).
*   **Pub/Sub:** Streaming topics (replacing Palantir Magritte).

## Universal Enterprise Standard (V7)
For Fortune 500 deployments, this IaC foundation must be wrapped in rigorous strategic guardrails:
1.  **VPC Service Controls (VPC-SC):** You must deploy this infrastructure within a VPC Service Perimeter to prevent data exfiltration. 
2.  **Global Resilience & Institutional Sponsorship:** Multi-region scaling (`primary_region` and `secondary_region`) is not enough. You must mandate **Quarterly Disaster Recovery Failover Drills**. To prevent execution fatigue, these drills MUST be backed by **Institutional Executive Sponsorship** (e.g., written into the corporate governance charter), not just driven by individual engineering leads.
3.  **Automated Catalog Lifecycle:** While Anthos Config Management prevents manual drift, the policies themselves can become unmanageable. You MUST implement a **Centralized Policy Catalog** for Config Sync/Policy Controller. To prevent governance fatigue, implement **Automated Catalog Pruning** (via GitOps CI/CD) to actively deprecate and archive stale or conflicting policies.

## Quick Start

1.  **Authenticate with GCP:**
    ```bash
    gcloud auth application-default login
    ```

2.  **Initialize Terraform:**
    ```bash
    terraform init
    ```

3.  **Review the Deployment Plan:**
    ```bash
    terraform plan -var="project_id=YOUR_PROJECT_ID"
    ```

4.  **Deploy the Landing Zone:**
    ```bash
    terraform apply -var="project_id=YOUR_PROJECT_ID"
    ```
