# Migrating Palantir Data & Pipelines to GCP

Migrating out of Foundry requires liberating your data from Palantir's proprietary file systems and rewriting logic to run on open-source or GCP-native engines.

## 1. Data Egress (Escaping Foundry)

Foundry stores data internally (often in Parquet format) but restricts access via the Foundry API. Egress is the highest-risk phase of migration due to API throttling and potential egress costs.

### Strategy A: The Foundry API (Bulk Export)
Use the `export_foundry_datasets.py` script provided in this framework. This script utilizes the Foundry REST API to page through datasets and download the raw Parquet files, which are then uploaded directly to Google Cloud Storage (GCS).
*   **Pros:** Works for any dataset, regardless of scale.
*   **Cons:** Subject to Foundry's API rate limits. High latency for massive datasets.

### Strategy B: External Data Connections (JDBC Push)
If the data is tabular, you can configure an External Data Connection in Foundry that points to a Cloud SQL instance (PostgreSQL). You then write a Foundry Pipeline Builder job to `INSERT` the data directly into GCP.
*   **Pros:** Bypasses REST API limits.
*   **Cons:** Not suitable for unstructured data or massive analytical workloads (BigQuery does not support direct JDBC inserts from Foundry; you must land in Cloud SQL first, then sync to BigQuery using Datastream).

## 2. Pipeline Modernization (Logic Translation)

Palantir Code Repositories allow users to write Python, Java, or SQL. However, Foundry injects proprietary decorators (e.g., `@transform`) and uses a custom build scheduler.

### Python (PySpark) Pipelines -> Cloud Dataproc
1.  **Remove Decorators:** Strip out `@transform`, `@input`, and `@output`.
2.  **Refactor I/O:** Replace Foundry's internal `transform.get_dataframe()` methods with standard PySpark `spark.read.parquet("gs://...")` commands targeting your new GCS data lake.
3.  **Deploy:** Run the refactored `.py` files on Google Cloud Dataproc Serverless.

### SQL Pipelines (Pipeline Builder) -> Google Cloud Dataform
Foundry's Pipeline Builder generates Spark SQL under the hood.
1.  **Extract SQL:** Export the raw SQL from the Pipeline Builder nodes.
2.  **Translate Dialect:** Convert Spark SQL syntax to BigQuery Standard SQL (e.g., handling array aggregations or specific date functions).
3.  **Implement Dataform:** Wrap the translated SQL in `.sqlx` files using Google Cloud Dataform to manage dependencies, assertions, and execution graphs within BigQuery.

## 3. Orchestration & DAG Management
Foundry uses its internal Build application to schedule pipelines based on data freshness. This must be replaced with robust enterprise orchestration.
*   **GCP Equivalent (PySpark):** Use **Cloud Composer (Apache Airflow)** to orchestrate Dataproc Spark jobs. Airflow handles the complex DAG dependencies that the Foundry Build app previously managed.
*   **GCP Equivalent (SQL):** Use **Google Cloud Workflows** or native Dataform Workflow Invocations scheduled via Cloud Scheduler to run BigQuery transformations.

## 4. Streaming & Real-Time Data (Replacing Magritte)
Palantir's Magritte streaming pipelines are often used for IoT and supply chain control towers. Batch BigQuery will not suffice for these workloads.
*   **The GCP Target:** **Cloud Pub/Sub** + **Cloud Dataflow**.
*   **Action:** Re-route external streaming sources (e.g., Kafka clusters, IoT gateways) to publish directly to Google Cloud Pub/Sub topics instead of Palantir REST endpoints.
*   **Processing:** Replace the streaming `@transform` logic with Apache Beam pipelines running on Cloud Dataflow, streaming the processed events into BigQuery.
*   **CDC (Change Data Capture):** If Magritte was used to ingest database changes, replace it with **Google Cloud Datastream** to replicate Oracle/PostgreSQL transactions directly into BigQuery in real-time.

### The Streaming Fork Architecture (Silent Killer Mitigation)
> [!CAUTION]
> **The Streaming SLA Trap:** BigQuery Dataform conversions assume batch or micro-batch processing. Palantir natively handles real-time windowing. If you map a 500ms supply chain pipeline to a 2-minute BigQuery materialized view, the business will claim the migration "broke the supply chain."

*   **Fork the Architecture:** Formally identify "Ultra-Low Latency" pipelines during Discovery. 
*   **Route Away from BigQuery:** Do not route these pipelines through BigQuery for operational serving. Fork them into **Apache Beam (Dataflow)** and land them directly in **Bigtable or Redis**. Reserve BigQuery strictly for analytical workloads.

### Enterprise Streaming Resilience & Legal SLAs (V7 Upgrade)
To guarantee Fortune 500 operational stability:
1.  **Schema Evolution:** CDC pipelines will break violently if upstream schemas drift. You must implement the **Pub/Sub Schema Registry** (using Avro or Protobuf). This enforces schema validation at the ingestion layer, preventing bad data from taking down the Dataflow pipeline.
2.  **Contractual SLA Linkage:** Technical latency SLAs ("sub-second lag") are insufficient. 
    *   **Action:** You must tie latency to **customer outcomes** and formal **legal contracts** (e.g., "A package scan must trigger a customer notification within 2 seconds, or penalties apply"). 
    *   **Legal Risk Management:** If binding SLAs increase liability exposure, your architecture must include explicit **penalty mitigation strategies** (e.g., multi-region fallback streaming clusters). Monitor these via strict Cloud Monitoring Dashboards tied to PagerDuty.

## 5. Regression Testing & Validation
Stripping decorators is not enough; Foundry often injects implicit joins or timezone handling. You must validate the output.
1.  **Dataform Assertions:** For SQL pipelines, implement Dataform `assertions` to check for uniqueness, null values, and row-count parity against the legacy Palantir datasets.
2.  **PySpark Hash Comparisons:** For complex Python transforms, implement a regression suite that hashes the output dataframe from the new GCP pipeline and compares it to the hash of the corresponding Foundry dataset output to guarantee semantic fidelity before cutting over.

### Continuous Pipeline Validation & Error Regressions (V7 Upgrade)
*   **Semantic CI/CD Integration:** Automated regression suites must be integrated directly into your CI/CD pipeline. 
*   **Performance & Error Regressions:** Semantic correctness is meaningless if the pipeline processes fewer events or fails silently. 
    *   **Action:** Configure the CI/CD pipeline to block PRs that break semantic fidelity **OR** fail throughput baselines **OR** exhibit unhandled exceptions. Explicitly test **Dead-Letter Queue (DLQ) behavior** and retry logic.
*   **CI/CD Efficiency Safeguards (V7):** Heavy regression suites can paralyze developer velocity. You MUST implement **incremental testing strategies** (e.g., only running full data-volume regressions on main-branch merges, utilizing sampled datasets for feature branches) to prevent pipeline slowdowns while maintaining safety.
