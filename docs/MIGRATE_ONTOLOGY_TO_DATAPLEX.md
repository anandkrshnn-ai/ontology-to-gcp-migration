# Deconstructing the Ontology: Migrating to BigQuery & Dataplex

The Palantir Ontology is the core semantic layer that maps physical data to real-world business concepts (Objects, Links, Actions). Migrating out of Foundry requires recreating this semantic layer using open, scalable GCP equivalents.

## 1. Object Types -> BigQuery Materialized Views
In Foundry, an "Object Type" (e.g., `Aircraft`, `Customer`) is a view over a backing dataset, indexed in Phonograph (Palantir's transactional database) for fast retrieval.

### The GCP Equivalent
*   **BigQuery Materialized Views:** For read-heavy object types, create BigQuery Materialized Views on top of your raw data lakes. This provides the fast, pre-computed read performance that Phonograph provides.
*   **Cloud SQL (AlloyDB):** If your Object Types require heavy, low-latency transactional updates (e.g., updating a `Flight_Status` every second), migrate that specific backing data to AlloyDB rather than BigQuery.

## 2. Link Types -> BigQuery Relationships
Foundry "Link Types" define relationships between Object Types (e.g., an `Airline` *has many* `Aircraft`).

### The GCP Equivalent
*   **Primary/Foreign Keys in BigQuery:** BigQuery now supports `PRIMARY KEY` and `FOREIGN KEY` constraints. While these are unenforced, they act as critical metadata for the query optimizer and downstream BI tools.
*   **Advanced Semantic Modeling (Time-Bounded & Hierarchical):** Foundry Ontology encodes complex business logic (e.g., an employee's role *between* two dates). Simple PK/FK constraints cannot capture this.
    *   **Action:** For time-bounded relationships, implement BigQuery **Temporal Tables** or materialized views with strict `BETWEEN` date logic.
    *   **Action:** For hierarchical relationships (e.g., a massive organization chart), utilize BigQuery's support for `STRUCT` and `ARRAY` (nested and repeated fields) to pre-calculate the hierarchy natively, preventing recursive query latency.

## 3. Advanced Semantic Modeling & Visualization (V6 Upgrade)
Palantir Link Types are often more complex than standard RDBMS foreign keys; they can be hierarchical (parent-child), temporal (time-bounded relationships), or many-to-many.
*   **The Problem:** Flat BigQuery Materialized Views lose this semantic richness, and JSON/STRUCTs can become an opaque "black box" to business users.
*   **The Target:** **BigQuery JSON/STRUCTs** + **Semantic Visualization Tools**.
*   **Action:** For hierarchical or temporal Link Types, model the BigQuery views using `ARRAY<STRUCT>` to embed child entities directly within the parent row. 
*   **Semantic Visualization & Workflow Embedding (V7):** Do not expect business users to write `UNNEST` SQL queries. You MUST deploy a **Data Lineage or Graph Visualization UI** (e.g., Dataplex Lineage graphs, Looker block visualizations, or a custom Neo4j UI). Crucially, these tools must be **natively embedded** within the analyst's primary workflow (e.g., Looker embedded iframes or Vertex AI Notebook extensions), rather than functioning as disjointed portal tools.
*   **Catalog Sync Monitoring (V7):** If using an external Enterprise Data Catalog (Collibra, Alation) for stewardship, you must automate metadata synchronization with Dataplex. To prevent integration fragility, implement strict **Sync Monitoring and Reconciliation Alerts** to detect and fix catalog divergence immediately.

## 4. Metadata & Lineage -> Google Cloud Dataplex
Foundry provides excellent data lineage, data health checks, and business glossaries out of the box.

### The GCP Equivalent
*   **Dataplex Business Glossary:** Recreate the "Ontology Manager" descriptions and metadata tags using Dataplex glossaries.
*   **Dataplex Lineage:** GCP automatically captures Data Lineage for BigQuery, Dataform, and Dataproc. You can view the visual lineage graph (equivalent to Foundry's Data Lineage app) directly in Dataplex.
*   **Data Quality:** Replace Foundry's "Data Health" checks with Dataplex Auto Data Quality rules.
*   **Governance & Stewardship (RBAC):** Foundry users rely heavily on Ontology-level permissions. You must replace this with Dataplex **Data Stewards**. Configure Role-Based Access Control (RBAC) within Dataplex Zones to grant specific business domains (e.g., HR, Finance) stewardship over their respective metadata, ensuring trust and ownership is not lost in translation.
*   **Stewardship UX (V6 Upgrade):** Enforcing PR workflows for data changes is correct, but Git is hostile to business users. You MUST deploy an Enterprise Data Catalog with a rich UI (e.g., **Collibra, Alation, or a customized Dataplex UI**) where "Ontology Managers" can visually review, approve, and submit Lineage Correction requests. Without a usable UX, ontology governance will fail.

## 4. Replacing "Actions"
Foundry "Actions" are transactional mutations applied to Objects (e.g., clicking a button to change a status).
*   **The GCP Equivalent:** If you are building custom applications on Cloud Run (replacing Workshop), your "Actions" are simply REST API calls (POST/PUT) that execute SQL `UPDATE` statements against BigQuery or AlloyDB. 
*   **Caution:** BigQuery is not designed for massive volumes of single-row updates. If your Foundry Actions generate thousands of single-row mutations per minute, that data MUST be moved to a transactional database (Cloud SQL/AlloyDB/Spanner) before being federated back into BigQuery.
