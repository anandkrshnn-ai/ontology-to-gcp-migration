# Phase 0: Data Discovery (Pre-Migration Baseline)

Data Discovery is the most critical phase of migrating off Palantir. Because Foundry is a vertical "black box," the data, transformation logic, and user interface are heavily intertwined. Migrating blindly without a complete map ensures failure.

This phase provides a **contractually defensible baseline** for the migration.

## 🔄 The Discovery Sequence

### 1. The Foundry Compass Audit (Lineage Mapping)
Palantir's greatest strength is its Data Lineage tool. We use it to trace pipelines from the visualization layer back to the raw ingestion source.
*   **Identify the Layers:** Explicitly tag every dataset into three tiers:
    *   **Raw / Ingest (Bronze):** Raw JSON/CSV landing via Magritte.
    *   **Transformed / Clean (Silver):** Intermediate datasets cleaned by Spark logic.
    *   **Ontology Backing Datasets (Gold):** Highly structured datasets powering Object Explorer and Contour dashboards.

### 2. Isolate the Transformation Logic
Palantir runs on Apache Spark managed by "Build" and "Code Repositories."
*   **Locate Code:** For every dataset, locate the exact Code Repository.
*   **Extract Logic:** Export PySpark, Java, or SQL code.
*   **Document Decorators:** Identify proprietary wrappers (e.g., `@transform`, `@incremental`) that dictate implicit logic requiring native rewrites in Google Cloud Dataflow or Dataproc.

### 3. Deconstruct the Semantic Layer (The Ontology)
You cannot just migrate the tables; you must migrate the relationships.
*   **Extract Objects:** Document every Object Type (e.g., `Package`, `Flight`).
*   **Extract Link Types:** Document relationship cardinalities (1:1, 1:Many, time-bounded) to dictate BigQuery `JSON/STRUCT` array schemas.
*   **Extract Security (Markings):** Document row-level and column-level security markings for BigQuery Policy Tag mapping.

### 4. Consumption Mapping & "Zombie" Hunting
Do not migrate data that no one uses. Eliminate "zombie" pipelines burning compute costs.
*   **Usage Telemetry:** Audit Palantir Contour, Quiver, and Workshop logs.
*   **The Purge:** If a dataset hasn't been queried in 90 days, do not migrate it. This typically reduces total migration scope and GCP costs by 20% to 30%.

### 5. The Logic Burn-Down Chart (Silent Killer Mitigation)
> [!CAUTION]
> **The Slate/Contour Logic Black Hole:** We can automate schema extraction, but proprietary business logic locked in Contour (visual data prep) or Slate cannot be exported via API. Severing connectors without rewriting this logic leaves analysts with raw tables and zero KPIs.

*   **Identify Critical Paths:** Identify the top 20% of Contour paths and Slate queries that drive 80% of business value.
*   **Mandate Manual Rewrite:** Formally assign Data Engineers to rewrite this visual logic into Dataform SQL *before* Phase 5. The "Logic Burn-Down Chart" tracks this manual engineering effort.

---

## 📊 Deliverables

At the end of this phase, no GCP architecture is built. Instead, you produce the definitive scope:
*   **Data Inventory Report** → All datasets + metadata 
*   **Pipeline Catalog** → Jobs, schedules, transforms  
*   **Ontology Export** → JSON/graph of semantic models  
*   **Classification Matrix** → Sensitivity labels applied  
*   **Lineage Graphs** → Migration sequencing map  

---

## 🚨 Brutal Truth

Skipping Phase 0 means migrating blind:  
- Sensitive datasets may be exposed.  
- Critical pipelines may break.  
- Dependencies may collapse.  

Phase 0 gives you a **contractually defensible baseline**: auditors can sign off, executives can trust the scope, and engineers can migrate with confidence.
