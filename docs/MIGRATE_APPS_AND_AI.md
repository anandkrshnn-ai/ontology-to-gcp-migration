# Rebuilding the User Interface and AI: Apps & AIP

Palantir's "Workshop" and "Artificial Intelligence Platform" (AIP) are the primary ways users interact with the Ontology. These interfaces are 100% proprietary and cannot be exported as code. 

**The Brutal Reality:** You cannot migrate a Workshop app. You must rebuild the functionality.

## 1. Replacing Workshop & Slate (The UI Layer)

Before writing any code, execute a rigorous **Feature Parity Analysis**. Workshop allows deep proprietary customization; not every app can be perfectly mapped to a low-code GCP tool. Audit all existing Workshop and Slate applications and categorize them into three buckets:

### Bucket A: Reporting & Ad-Hoc Data Exploration
Foundry users rely heavily on Contour for visual data exploration without code.
*   **The GCP Target:** A hybrid of **BigQuery Studio** (for ad-hoc SQL/Python exploration) and **Looker** (for semantic visualization and governed BI).
*   **Action:** Do not try to force Looker as a 1:1 Contour replacement. Looker requires centralized LookML engineering, breaking the self-service model. Train business users to use BigQuery Studio's visual data exploration features for ad-hoc pivots, and transition mature dashboards to Looker.

### B. Code-Driven Analysis (Replacing Code Workbooks)
*   **The Target:** **Vertex AI Workbench** or **Colab Enterprise**.
*   **Action:** Provide Python/R users with managed notebook environments that have pre-authenticated, IAM-governed access to the BigQuery datasets.
*   **Collaboration Parity (V5 Upgrade):** Foundry Code Workbooks natively support multi-user real-time collaboration. Default Vertex notebooks do not. 
    *   **Action:** You must enforce **Git-backed Colab Enterprise environments**. 
    *   Do not allow analysts to work in isolated, unversioned notebooks. Configure Colab Enterprise to sync directly with a GitHub/GitLab repository. 
    *   Implement strict Pull Request (PR) workflows for any notebook code that is intended to run in production or be shared across teams. This bridges the concurrency gap and enforces enterprise governance.
    *   **Real-Time Alternative:** If Git PR workflows introduce too much friction for your data science teams, investigate integrating **Deepnote** or upcoming GCP native real-time co-editing features to achieve true multi-user concurrency parity with Palantir.

### C. Adoption Metrics & Remediation (V6 Upgrade)
Change management is not just retraining; it is quantifiable adoption.
*   **Action:** Do not rely on anecdotal feedback. Implement strict adoption telemetry.
*   **Metrics to Track:**
    *   **CSAT:** Weekly Customer Satisfaction scores from analysts transitioning from Contour to BQ Studio.
    *   **Usage Parity:** Track the number of BigQuery queries run via the new tools versus the historical query volume in Palantir. A drop in volume indicates users are frustrated and abandoning the platform (Shadow IT risk).
*   **Adoption Remediation Playbook (V7):** Tracking metrics is useless without an action plan. If CSAT drops below acceptable thresholds or Usage Parity falls behind:
    1.  **Flexible KPI Thresholds:** CSAT targets must be context-aware. A 15% rebound KPI might be viable for a modern data team, but impossible in a risk-averse compliance unit. Adjust remediation thresholds based on the specific business unit's baseline.
    2.  **Cultural Tailoring:** Avoid one-size-fits-all fixes. While gamification ("bounty boards") works for software engineers, conservative enterprises may require formal, audited **Certification Tracks** instead.
    3.  **Mandatory Office Hours:** Deploy Data Engineers to sit (virtually) with the struggling business unit twice a week.
    4.  **Hybrid Bridging Views:** If the new SQL model is too complex, temporarily deploy simplified "Bridging Views" in BigQuery that mimic the exact column structure of the legacy Palantir datasets, giving analysts a familiar stepping stone.

### Bucket B: Low-Code Data Entry (CRUD)
If the Workshop app allows users to update statuses, submit forms, or manage simple lists (e.g., updating the status of an `Aircraft`).
*   **The GCP Target:** **AppSheet**.
*   **Action:** AppSheet is Google's no-code platform. You can point AppSheet directly at BigQuery or Cloud SQL tables. It will auto-generate mobile and web interfaces for CRUD (Create, Read, Update, Delete) operations, mimicking Workshop's "Actions" without writing custom code.

### Bucket C: Complex Workflows & Micro-Frontends
If the Workshop app involves complex, multi-step approvals, deep API integrations with external systems (like SAP), or custom visual widgets.
*   **The GCP Target:** Custom UI (React/Angular) on **Cloud Run**.
*   **Action:** This requires software engineering. Build a modern web application, host it on Cloud Run, and use Identity-Aware Proxy (IAP) to enforce zero-trust access exactly like Foundry does. Use Cloud Endpoints or API Gateway to manage the backend APIs querying BigQuery/AlloyDB.

### Change Management & User Retraining
**The Threat:** Business users are trained heavily on Palantir's interface. If you rip it out without warning, adoption of the GCP replacements will fail, regardless of technical success.
*   **Action:** Develop a comprehensive Change Management plan. Implement parallel runs where users can compare Looker dashboards to their old Slate dashboards. Establish mandatory "GCP Data Literacy" training weeks before the Foundry shutdown to familiarize them with AppSheet and Looker UIs.

## 2. Replacing AIP (The AI Layer)

Palantir's AIP allows users to chain LLM prompts and execute Actions on the Ontology.

### The GCP Target: Vertex AI (Gemini & Agent Builder)
Google Cloud has a much deeper native AI ecosystem than Palantir, powered by the Gemini models.

*   **AIP Logic -> Vertex AI Agent Builder:** Instead of using AIP Logic to build prompt chains, use Vertex AI Agent Builder. You can create Agents that have "Tools" (API access to BigQuery) and "Data Stores" (Enterprise Search over your PDFs/documents).
*   **AIP Assist -> Gemini in Looker/BigQuery:** GCP injects Gemini directly into the console. Analysts can use Gemini in BigQuery to write SQL, or Gemini in Looker to generate reports from natural language, replacing the need for AIP Assist.
*   **Foundry ML -> Vertex AI Model Registry:** If you trained custom scikit-learn or PyTorch models in Foundry, export the model artifacts (`.pkl` or `.pt` files) via the script in Phase 1, and upload them to Vertex AI Model Registry for managed serving.
*   **AI Guardrails & Safety Filters:** Palantir AIP heavily markets its rigid safety perimeters and access controls for LLMs. When migrating to Vertex AI, you must explicitly recreate this security posture. Implement **Vertex AI Safety Settings** to block hate speech, dangerous content, and bias. Utilize **IAM per-user context** when querying Agent Builder to ensure the LLM cannot hallucinate or retrieve data the user is not authorized to see.
