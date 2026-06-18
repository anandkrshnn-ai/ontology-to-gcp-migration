# Landing Zone Architecture: Replicating Palantir's Perimeter on GCP

Palantir operates as an implicit, air-gapped security perimeter. Migrating Palantir workloads (BigQuery, Cloud Run, Dataproc) into a flat GCP project without a foundational Landing Zone violates enterprise security standards and guarantees an audit failure.

This document defines the strict **GCP Enterprise Landing Zone** required to safely host the migrated Palantir workloads, utilizing a Shared VPC and VPC Service Controls (VPC-SC).

---

## 1. Resource Hierarchy

Palantir uses "Spaces" to logically separate lines of business. In GCP, we map this to the formal Folder and Project hierarchy to ensure isolation and billing attribution.

| Palantir Concept | GCP Implementation | Description |
| :--- | :--- | :--- |
| **Organization** | GCP Organization Node | The root of the enterprise tree (e.g., `enterpriseco.com`). |
| **Spaces** | GCP Folders | Logical grouping (e.g., `Folder: Logistics`, `Folder: Finance`). |
| **Projects / Use Cases** | GCP Projects | We enforce a strict **Hub-and-Spoke** model. One `Host Project` for networking, and multiple `Service Projects` (Data, Apps, Analytics) for workloads. |

## 2. Identity & Access Management (IAM)

Palantir utilizes proprietary roles (Owner, Editor, Viewer) deeply tied to their ontology.

| Palantir Role | GCP IAM & Data Controls | Description |
| :--- | :--- | :--- |
| **Platform Administrator** | `roles/owner` (Restricted) | Limited to emergency break-glass accounts. |
| **Data Steward** | `roles/datacatalog.admin` + `roles/bigquery.admin` | Governs the taxonomy and policy tags. |
| **Ontology Editor** | `roles/bigquery.dataEditor` | Can mutate tables; often restricted to the Cloud Run CQRS Service Accounts. |
| **Analyst (Viewer)** | `roles/bigquery.dataViewer` | Read-only access, heavily filtered by Dataplex column/row-level security. |

## 3. Data Landing Zone (Medallion Architecture)

Palantir utilizes the "Foundry Filesystem" to store raw ingested data before it's transformed into the Ontology. In our GCP framework, the **Data Landing Zone** is governed by Dataplex and follows the Medallion architecture.

- **Raw Zone (Bronze):** Google Cloud Storage (GCS). This is the initial landing point for raw exports from Palantir (`google_storage_bucket.data_lake` in `main.tf`). Data here is immutable.
- **Clean Zone (Silver):** BigQuery. Data is parsed, schematized, and validated against the Semantic Hash (`pyspark_hash_validator.py`).
- **Curated Zone (Gold):** BigQuery / Cloud SQL. This is the new "Ontology" where business logic is applied (via the Contour-to-SQL translator) and Workshop Actions can perform mutations.

## 4. Networking: The Shared VPC

A standalone VPC does not scale for an enterprise migration. We utilize a **Shared VPC (Hub-and-Spoke)** model.

- **Host Project (`prj-net-hub`):** Owns the Shared VPC, subnets, firewall rules, and Cloud NAT.
- **Service Projects (`prj-data-logistics`, `prj-apps-actions`):** Consume subnets from the Host Project.
- **Egress Control:** Cloud NAT is configured in the Host Project. All egress traffic routes through a centralized inspection point.
- **B2B Extensibility:** Private Service Connect (PSC) is used to securely expose Cloud Run APIs (the migrated Workshop Actions) to external partners without exposing the internal VPC.

## 4. Security Perimeters: VPC Service Controls (VPC-SC)

Palantir's "walled garden" prevents data exfiltration by default. In GCP, we enforce this contractually using **VPC Service Controls**.

- **The Perimeter:** A VPC-SC perimeter is drawn around all data-hosting Service Projects.
- **Protected APIs:** `bigquery.googleapis.com`, `storage.googleapis.com`, `pubsub.googleapis.com`, `dataproc.googleapis.com`.
- **Exfiltration Prevention:** Even if an analyst holds `roles/bigquery.dataViewer`, they cannot run a `bq extract` command to a GCS bucket outside the perimeter.
- **Perimeter Bridging:** For CI/CD pipelines (GitHub Actions/Cloud Build) to deploy code, explicit ingress/egress rules are configured on the perimeter to allow strictly defined deployment traffic.

> [!WARNING]
> VPC-SC misconfigurations are the #1 cause of pipeline failures during migration. The Landing Zone infrastructure-as-code must be validated in a sandbox environment before applying to production.
