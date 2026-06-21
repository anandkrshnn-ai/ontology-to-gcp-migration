# Presentation Guide: Ontology-to-GCP Migration Demo

This guide outlines the step-by-step narrative and commands to present the three demo tracks showcasing the Palantir-to-GCP ontology migration pipeline.

---

## Pre-Flight Setup Checklist
Before starting the demo, configure your Google Cloud Environment:

1. **Verify Spanner Instance**:
   Ensure the instance `ontology-demo` and database `ontology-db` are created in region `us-central1` with processing units set to `100`.
2. **Cloud Build Triggers**:
   * Create a **Plan Trigger** pointing to `cloudbuild-plan.yaml` on pushes/PRs to `master`.
   * Create an **Apply Trigger** pointing to `cloudbuild-apply.yaml` on merges to `master` with **Manual Approval Required** enabled.
3. **Application Default Credentials**:
   If running the dashboard in Cloud Shell, run the authentication command:
   ```bash
   gcloud auth application-default login
   ```

---

## Act 1: The GitOps Schema-as-Code Pipeline (GCP Console)
**Goal**: Demonstrate how ontology modifications are verified automatically in CI and released after manual approval.

### Step 1: Show the Current State
1. Show the [ontology/network_routing.yaml](file:///ontology/network_routing.yaml) file on GitHub.
2. Point out the `attributes`, `relationships`, and validation `rules` enforcing the schema boundaries.

### Step 2: Trigger CI Validation (PLAN)
1. Edit `ontology/network_routing.yaml` to add a new neutral attribute:
   ```yaml
     - name: region
       type: STRING(50)
   ```
2. Commit and push the change to `master`.
3. Open the **Cloud Build History** console and watch the Plan trigger execute.
4. Open the build logs and point out:
   * Unit tests passing successfully.
   * `scripts.orchestrator` validating the specifications.
   * The DDL diff showing the planned column addition: `ADD COLUMN region`.

### Step 3: Manual Gate & Deploy (APPLY)
1. Switch to the gated Apply trigger. Point out that the build is paused waiting for an authorized approver.
2. Approve the deployment.
3. Once completed, navigate to the **Spanner Studio** console and show the `network_routing` table now has the `region` column live.

---

## Act 2: Interactive Graph RAG Dashboard (Streamlit)
**Goal**: Show the serving plane resolving natural language queries by merging unstructured logs with Spanner Graph relationships.

### Step 1: Start the Dashboard
1. Open Cloud Shell and run:
   ```bash
   pip install -r requirements.txt
   streamlit run scripts/rag_dashboard.py --server.port 8080
   ```
2. Open the Web Preview (port 8080).

### Step 2: Select Connection Mode
* In the sidebar, select **Simulated Mode** for offline presentation, or **Live Google Cloud Spanner** to query your live database instance.
* (Optional) Enter your Gemini API key in the sidebar for live LLM synthesis.

### Step 3: Run the Graph RAG Query
1. Select the query:
   *"Why are segments originating from OAK experiencing delays, and what transport mode satisfies SEG-002?"*
2. Click **Run GraphRAG Retriever**.
3. Point out the three execution steps in the UI:
   * **Step 1: Semantic Document Retrieval**: Finds unstructured log reports indicating power fluctuations at the `OAK-STN` station.
   * **Step 2: Spanner Graph Path Expansion**: Traverses the `air_routing_graph` GQL query to resolve segment configurations (`SEG-002` connecting OAK-RAMP to MEM-HUB via `AIR`).
   * **Step 3: Answer Synthesis**: Generates a unified response showing that although OAK is suffering power delays, the downstream air corridors remain active.

---

## Act 3: Automated Boardroom Demo (Resilience Script)
**Goal**: Demonstrate how the migration proxy handles API throttling, incremental loading, and blocks corrupt migrations.

### Step 1: Execute the Demo Script
Run the automated resilience script:
```bash
python scripts/run_boardroom_demo.py
```

### Step 2: Point Out Key Highlights
As the script outputs logs, explain these four resilience capabilities:
1. **Extraction Throttling (Tenacity backoff)**: Shows the script receiving HTTP `429` (too many requests) errors and backing off exponentially until successful.
2. **Incremental Conversion**: Shows incoming tables compiling to Dataform `.sqlx` incremental models.
3. **CQRS Proxy**: Shows queries being routed to BigQuery view representations (for high-volume reads) and actions routed to transactional databases.
4. **Fidelity Gating**: Shows the pipeline automatically halting execution and logging a critical alert when a hash validation failure is encountered, preventing corruption.
