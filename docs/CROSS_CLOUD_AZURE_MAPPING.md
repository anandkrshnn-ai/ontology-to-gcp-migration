# Cross-Cloud Portability: The Azure Mapping

The V7 Migration Framework is architected around foundational data primitives, not vendor lock-in. While this repository heavily features Google Cloud Platform (GCP) configurations, the exact same execution strategy and pipeline logic apply directly to Microsoft Azure.

This document maps the mechanics of the V7 Framework to the Azure ecosystem, proving to multi-cloud CIOs that this migration strategy is universally defensible.

---

## 1. The Storage Layer (Bronze / Landing)

**The V7 Concept:** Severing the Palantir ingestion pipelines and routing raw data to a cheap, scalable object store before transforming it.

*   **Palantir:** Foundry Files / Cloud Storage
*   **GCP Target:** Google Cloud Storage (GCS)
*   **Azure Target:** **Azure Data Lake Storage (ADLS) Gen2**
*   *Execution Shift:* The Python extraction scripts simply change their output destination from the GCP Storage API to the `azure-storage-file-datalake` SDK. The folder hierarchy (`/bronze/dataset_id/yyyy/mm/dd/`) remains identical.

## 2. The Analytical Engine (Silver / Gold)

**The V7 Concept:** Moving interactive data exploration, complex aggregations, and materialized views from a proprietary backend to a cloud-native columnar OLAP engine.

*   **Palantir:** Spark / Presto
*   **GCP Target:** Google BigQuery
*   **Azure Target:** **Azure Synapse Analytics (Dedicated SQL Pools) or Microsoft Fabric (OneLake + SQL Endpoints)**
*   *Execution Shift:* Schemas translated by the V7 framework into `.sqlx` can be deployed via Synapse Notebooks or Data Factory. The concept of Materialized Views replacing Foundry Object Links applies perfectly to Synapse.

## 3. The Transformation Orchestrator

**The V7 Concept:** Translating proprietary Palantir Contour/Pipeline Builder logic into Git-backed, version-controlled SQL transformation graphs.

*   **Palantir:** Pipeline Builder / Contour
*   **GCP Target:** Dataform (SQLX)
*   **Azure Target:** **Azure Data Factory (Mapping Data Flows) or dbt on Azure**
*   *Execution Shift:* Azure's native Dataform equivalent is ADF Mapping Data Flows. However, for maximum code portability, deploying **dbt (data build tool)** on Azure Synapse is the recommended standard. The V7 Schema Converter can be easily adapted to output dbt `.sql` models instead of Dataform `.sqlx`.

## 4. The Streaming Ingest & DLQ

**The V7 Concept:** Bypassing batch latency for sub-second supply chain apps, and capturing permanent execution errors via Dead-Letter Queues.

*   **Palantir:** Magritte Streaming
*   **GCP Target:** Google Pub/Sub
*   **Azure Target:** **Azure Event Hubs**
*   *Execution Shift:* The `google.cloud.pubsub_v1` library used in the V7 extraction scripts is swapped for `azure-eventhub`. Event Hubs natively supports DLQ routing to ADLS Gen2, maintaining the exact same architectural resilience.

## 5. Security & Governance Mapping

**The V7 Concept:** Scraping Palantir's hierarchical security markings and injecting them into a cloud-native catalog for seamless row/column level access control.

*   **Palantir:** Security Markings / Object Permissions
*   **GCP Target:** Dataplex Policy Tags
*   **Azure Target:** **Microsoft Purview**
*   *Execution Shift:* The `metadata_scraper_to_policy_tags.py` script output is changed. Instead of generating Terraform for `google_data_catalog_policy_tag`, it generates the REST payloads or ARM templates required to define classifications and sensitivity labels in Microsoft Purview.

---

## The Verdict

By relying on standard APIs, exponential backoff (`tenacity`), semantic validation (PySpark), and CQRS proxies (FastAPI), **the V7 Migration Framework is completely cloud-agnostic at the execution layer.** Migrating to Azure requires only swapping the SDK endpoint targets, while the architectural strategy remains untouched.
