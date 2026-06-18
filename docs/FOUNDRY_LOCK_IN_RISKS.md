# Risk Assessment: The Foundry Lock-In Factor

Migrating out of Palantir Foundry is notoriously difficult due to extreme vertical integration. This document outlines the brutal realities and technical risks associated with data extraction and logic decoupling, along with mitigation strategies.

## 1. Data Egress & Throttling Risk
**The Threat:** Palantir tightly controls data ingress and egress. Unlike standard cloud platforms, there is no direct S3/GCS bucket access to your raw Parquet files by default. You must extract data via the Foundry REST API or JDBC.
*   **Risk Level:** **CRITICAL**
*   **Impact:** Attempting to egress petabytes of data via REST API will trigger aggressive rate limiting (HTTP 429), resulting in migrations that could take months instead of days.
*   **Mitigation Strategy:** 
    1.  **Do not attempt a "big bang" extraction over the public internet.** Petabyte-scale transfers from Azure ADLS to GCS will trigger massive egress fees.
    2.  **Negotiate Peering:** Establish a high-bandwidth, direct interconnect or negotiated peering agreement between Azure and GCP to minimize standard egress rates.
    3.  **Offline Transfer:** For extremely large, historical datasets, use Google Cloud Transfer Appliance to physically move the data from Azure to GCP data centers.
    4.  Utilize the provided `export_foundry_datasets.py` script for incremental synchronization of delta changes, implementing exponential backoff.
    5.  For massive active tables, investigate deploying a Palantir "External Data Connection" agent inside GCP, pushing data from Foundry to a Cloud SQL staging database rather than pulling via API.

## 2. Data Fidelity & Reconciliation Risk
**The Threat:** Foundry datasets often contain hidden lineage, implicit schema evolution, or undocumented transformations. Pulling raw Parquet may result in semantic loss.
*   **Risk Level:** **HIGH**
*   **Impact:** If the migrated GCS data does not exactly match the ADLS source, analytical models will break, eroding trust in the new GCP environment.
*   **Mitigation Strategy:**
    1.  **Checksum Validation:** Implement mandatory MD5 checksum validation during the transfer process from Azure ADLS to GCS.
    2.  **Row-Count Parity Checks:** Execute automated scripts post-migration to compare row counts and schema definitions between the source Foundry dataset and the target BigQuery table before signing off on the migration phase.

## 3. Proprietary Logic Risk (The `@transform` Trap)
**The Threat:** Foundry encourages users to write PySpark, but requires them to wrap it in proprietary decorators (`@transform`, `@input`).
*   **Risk Level:** **HIGH**
*   **Impact:** Code cannot simply be copy-pasted to Google Cloud Dataproc. Every single pipeline file must be manually refactored to remove Palantir dependencies.
*   **Mitigation Strategy:** 
    1.  Use LLMs (like Gemini) to automate the translation. Feed the Palantir Python code into Gemini with a prompt instructing it to strip `@transform` and replace `transform.get_dataframe()` with standard `spark.read.parquet()`.
    2.  Establish a strict testing framework comparing the output hashes of the Foundry dataset against the new BigQuery dataset.

## 4. The Ontology Rebuild Risk
**The Threat:** The Ontology abstracts away SQL JOINs. Users in Foundry do not know the underlying schema; they just query "Aircraft" and its linked "Flights".
*   **Risk Level:** **HIGH**
*   **Impact:** Rebuilding this on GCP requires reverse-engineering the data model. If relationships are mapped incorrectly in BigQuery, downstream Looker dashboards will show wildly inaccurate metrics.
*   **Mitigation Strategy:** 
    1.  Before shutting down Foundry, mandate that data stewards export the exact schema mapping (Object to Dataset, Link to Join Key) from the Ontology Manager app.
    2.  Recreate the exact graph relationships in BigQuery using `PRIMARY KEY` and `FOREIGN KEY` constraints.

## 5. Total Rebuild of Applications
**The Threat:** Workshop and Slate applications are built via a proprietary GUI. There is no export functionality.
*   **Risk Level:** **MEDIUM** (High cost, but known scope)
*   **Impact:** 100% of the UI layer must be rebuilt from scratch on GCP (Looker, AppSheet, Cloud Run).
*   **Mitigation Strategy:** 
    1.  Use the migration as a pruning exercise. 40% of Workshop apps are likely abandoned. Review Foundry usage logs and only rebuild the apps that have active daily users.
    2.  Default to Google AppSheet for rapid rebuilding of data-entry forms.
