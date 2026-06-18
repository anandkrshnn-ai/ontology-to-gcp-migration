# Cross-Cloud Portability: Azure to GCP Mapping

A major barrier to enterprise cloud migrations is the fear of moving from one vendor lock-in (Palantir) directly into another (Google Cloud). 

This document serves as boardroom assurance. It explicitly proves that the V7 Migration Framework is built on **Sovereign Enterprise Standards** (Standard SQL, containerized APIs, decoupled storage) and can be fully ported to Microsoft Azure if strategic or regulatory requirements ever mandate an exit strategy.

---

## 1. The Sovereign Framework Matrix

The following table maps the core components of our GCP architecture to their exact Azure equivalents. This proves operational continuity and hybrid-cloud readiness.

| Migration Domain | Palantir Source | Target (GCP) | Sovereign Equivalent (Azure) | Migration / Portability Note |
| :--- | :--- | :--- | :--- | :--- |
| **Data Lake (Raw Data)** | Foundry Filesystem | **Cloud Storage (GCS)** | **ADLS Gen2** | Parquet files are universally portable. Object lifecycle and IAM mapped 1:1. |
| **Data Warehouse** | Foundry Ontology | **BigQuery** | **Azure Synapse Analytics** | Uses Standard SQL dialect; schema and views port with minimal syntax changes. |
| **Streaming & Telemetry** | Magritte Streaming | **Pub/Sub** | **Azure Event Hubs** | Event-driven architecture decoupled from storage. |
| **ETL / Heavy Compute** | PySpark Code Repos | **Dataproc Serverless** | **Azure Databricks** | PySpark is 100% cloud-agnostic. Code ports directly with 1-to-1 compute portability. |
| **Visual Pipelines** | Contour / Pipeline Builder| **Dataform (.sqlx)** | **dbt (Data Build Tool)** | Dataform's SQLX translates naturally to dbt models for Synapse/Databricks. |
| **Data Governance** | Foundry Markings | **Dataplex** | **Microsoft Purview** | Policy tags, data lineage, and column-level security map structurally between the two. |
| **Mutations / APIs** | Workshop Actions | **Cloud Run (FastAPI)** | **Azure Container Apps** | Dockerized REST APIs are universally portable. Zero vendor lock-in. |
| **Identity & Access** | Palantir Multipass | **Cloud Identity / IAM** | **Microsoft Entra ID (Azure AD)** | OIDC/SAML mapping allows centralized identity governance. |
| **Observability** | Foundry Data Health | **Cloud Monitoring** | **Azure Monitor** | Log sinks and SLA dashboards map to KQL queries. |

---

## 2. Portability Principles

To ensure this framework remains a "Sovereign Standard" and doesn't devolve into proprietary lock-in, the engineering teams strictly adhere to the following principles:

### A. Compute is Ephemeral and Containerized
All migrated Palantir "Workshop Actions" (mutations) are written in FastAPI or Go and packaged as standard Docker containers. By deploying to **Cloud Run**, we guarantee they can be redeployed tomorrow on **Azure Container Apps** or an on-premise Kubernetes cluster without rewriting a single line of business logic.

### B. Logic is Standardized (No Proprietary Dialects)
We strictly forbid proprietary BigQuery extensions where standard SQL suffices. Palantir Contour logic is compiled into standard SQL CTEs. If the enterprise pivots to Azure, those same SQL scripts will execute in Synapse Analytics.

### C. Data is Open Format
All raw data egressed from Palantir is stored in standard Parquet format within Cloud Storage. Parquet natively retains schema definitions, allowing ADLS Gen2 and Azure Databricks to mount and read the data instantly if a cross-cloud migration is initiated.

---

## 3. Audit Readiness Statement

By adhering to this Azure portability matrix, the organization guarantees to regulators and the Board of Directors that:
1. **Data Sovereignty is maintained.**
2. **Business Continuity is secured against GCP service disruptions.**
3. **The IT estate is hybrid-ready and capable of multi-cloud acquisitions (M&A).**
