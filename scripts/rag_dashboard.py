import streamlit as st
import json
import os
import sys
import yaml
import numpy as np

# Adjust sys.path to resolve local packages in the workspace root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.orchestrator import SpannerRegistryManager, Orchestrator
from scripts.graph_compiler import GraphCompiler
from scripts.run_ontology_to_graph_rag_demo import MockVectorStore, SpannerGraphSimulator

# Theme Configuration
st.set_page_config(
    page_title="Palantir-to-GCP Migration Engine",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Styling (Dark Mode, Glassmorphism, Rounded Cards)
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
        color: #e0e0e0;
    }
    .stApp {
        background-color: #0d0f14;
    }
    div.stButton > button {
        background-color: #1a73e8;
        color: white;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.6em 2em;
        border: none;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {
        background-color: #1557b0;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(26,115,232,0.3);
    }
    .card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 1.5em;
        margin-bottom: 1em;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }
    .step-header {
        font-weight: 700;
        font-size: 1.1em;
        color: #1a73e8;
        margin-bottom: 0.5em;
    }
    code {
        color: #ff7b72 !important;
    }
</style>
""", unsafe_allow_html=True)

# Title Header
st.markdown("""
<div style="text-align: center; padding: 1.5em 0;">
    <h1 style="color: #ffffff; font-weight: 800; font-size: 2.8em; margin-bottom: 0.2em;">🚀 Palantir-to-GCP Migration Engine</h1>
    <p style="color: #8a99ad; font-size: 1.2em;">Ontology-to-GraphRAG Modernization Control Plane</p>
</div>
""", unsafe_allow_html=True)

# Load Ontology files
ontology_dir = "ontology"
yamls = {}
if os.path.exists(ontology_dir):
    for f_name in os.listdir(ontology_dir):
        if f_name.endswith(('.yaml', '.yml')):
            with open(os.path.join(ontology_dir, f_name), 'r', encoding='utf-8') as f:
                yamls[f_name] = f.read()

# Sidebar Setup
st.sidebar.title("🛠️ Mode & Connection")
conn_mode = st.sidebar.radio(
    "Select Backend Connection Mode:",
    ["Simulated (Mocked)", "Live Google Cloud Spanner"]
)

spanner_project = ""
spanner_instance = ""
spanner_database = ""

if conn_mode == "Live Google Cloud Spanner":
    st.sidebar.markdown("---")
    st.sidebar.subheader("Spanner Configuration")
    spanner_project = st.sidebar.text_input("GCP Project ID:", value=os.environ.get("GOOGLE_CLOUD_PROJECT", "migration-demo"))
    spanner_instance = st.sidebar.text_input("Spanner Instance ID:", value="ontology-instance")
    spanner_database = st.sidebar.text_input("Spanner Database ID:", value="ontology-db")
    
    st.sidebar.info("💡 Make sure you run 'terraform apply' or create the Spanner Instance & Database in your GCP Console first.")

# Initialize Backend Client
@st.cache_resource
def get_spanner_client(project, instance, database, mock):
    try:
        from google.cloud import spanner
        if mock:
            return SpannerRegistryManager(mock=True), None
        
        # Test Spanner client connection
        client = spanner.Client(project=project)
        inst = client.instance(instance)
        db = inst.database(database)
        
        # Instantiate real registry manager
        manager = SpannerRegistryManager(instance_id=instance, database_id=database, mock=False)
        # Inject clients for custom querying
        manager.spanner_client = client
        manager.spanner_db = db
        return manager, None
    except Exception as e:
        return None, str(e)

if conn_mode == "Live Google Cloud Spanner":
    registry_manager, conn_err = get_spanner_client(spanner_project, spanner_instance, spanner_database, mock=False)
    if conn_err:
        st.error(f"❌ Failed to connect to GCP Spanner client: {conn_err}")
        st.warning("Falling back to Simulated Mode.")
        registry_manager = SpannerRegistryManager(mock=True)
        is_live = False
    else:
        st.success(f"⚡ Connected to Live Spanner: `{spanner_instance}/{spanner_database}`")
        is_live = True
else:
    registry_manager = SpannerRegistryManager(mock=True)
    is_live = False

# Tabs
tab1, tab2, tab3 = st.tabs(["🎛️ Control Plane (Compiler)", "📥 Ingestion Zone (Telemetry)", "🔍 Serving Plane (GraphRAG)"])

# TAB 1: Control Plane
with tab1:
    st.markdown("### Structural Ontology Registry & Compilation")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Ontology Specs")
        selected_file = st.selectbox("Select raw contract to view:", list(yamls.keys()))
        if selected_file:
            st.code(yamls[selected_file], language="yaml")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Compiler Transition Plan")
        
        if not is_live:
            sim_mode = st.radio(
                "Simulate Schema Evolution Mode:",
                ["ADDITIVE (No conflicts - Auto Apply)", "BREAKING (Schema mismatch - Hard Gate)"]
            )
            
            if st.button("Generate Migration Plan"):
                if "ADDITIVE" in sim_mode:
                    plan_path = "artifacts/plan_success.json"
                    if os.path.exists(plan_path):
                        with open(plan_path, "r", encoding="utf-8") as f:
                            plan_data = json.load(f)
                        st.success("✔️ Transition plan compiled successfully (Status: APPROVED)")
                        st.json(plan_data)
                    else:
                        st.warning("plan_success.json not found in artifacts.")
                else:
                    plan_path = "artifacts/plan_blocked.json"
                    if os.path.exists(plan_path):
                        with open(plan_path, "r", encoding="utf-8") as f:
                            plan_data = json.load(f)
                        st.error("❌ MIGRATION BLOCKED (Status: BLOCKED_BREAKING)")
                        st.info("⚠️ Pipeline halted: Incompatible schema modification detected. Manual DBA intervention required.")
                        st.json(plan_data)
                    else:
                        st.warning("plan_blocked.json not found in artifacts.")
        else:
            # LIVE MODE: Run actual validation and plan generation
            st.markdown("##### Live GCP Schema Operations")
            
            col_actions = st.columns(2)
            with col_actions[0]:
                if st.button("Initialize Registry Metadata Tables"):
                    with st.spinner("Deploying base schema registry tables..."):
                        try:
                            ddl_path = "terraform/modules/spanner/schema.ddl"
                            with open(ddl_path, "r", encoding="utf-8") as f:
                                ddl_text = f.read()
                            
                            # Split statements on semicolon
                            statements = [stmt.strip() for stmt in ddl_text.split(";") if stmt.strip()]
                            operation = registry_manager.spanner_db.update_ddl(statements)
                            operation.result()
                            st.success("✔️ Metadata registry tables successfully created in Spanner!")
                        except Exception as e:
                            st.error(f"Failed to apply schema.ddl: {e}")
                            
            with col_actions[1]:
                if st.button("Deploy Current Ontology to Spanner"):
                    with st.spinner("Compiling and applying ontology configuration..."):
                        try:
                            # 1. Run local orchestrator validation
                            orchestrator = Orchestrator(registry_manager)
                            plan_info = orchestrator.run_plan(ontology_dir)
                            
                            # 2. Compile DDLs
                            validated_files = orchestrator.validate_source_dir(ontology_dir)
                            yamls_list = [data for _, data in validated_files]
                            graph_yaml = next((y for y in yamls_list if y.get("kind") == "PropertyGraph"), None)
                            
                            compiler = GraphCompiler(compatibility_status=plan_info["status"], schema_diffs=plan_info["schema_diffs"])
                            compilation_plan = compiler.compile_plan(yamls_list, graph_yaml)
                            
                            if compilation_plan["status"] == "BLOCKED_BREAKING":
                                st.error("❌ Compilation Blocked: Breaking change detected.")
                                st.json(compilation_plan["migration_recipe"])
                            else:
                                # Apply compiled DDLs
                                ddl_statements = compilation_plan["actions"]
                                if ddl_statements:
                                    st.info(f"Deploying {len(ddl_statements)} DDL statements to Spanner...")
                                    operation = registry_manager.spanner_db.update_ddl(ddl_statements)
                                    operation.result()
                                    
                                    # Log the changes
                                    orchestrator.run_apply(ontology_dir)
                                    st.success("✔️ Property Graph successfully compiled and deployed to Spanner database!")
                                    st.json(compilation_plan)
                                else:
                                    st.warning("No new DDL actions compiled.")
                        except Exception as e:
                            st.error(f"Error executing schema apply: {e}")
                            
            st.markdown("---")
            # Query Registry Tables
            if st.button("Query Active Registry Metadata"):
                try:
                    with registry_manager.spanner_db.snapshot() as snapshot:
                        results = snapshot.execute_sql("SELECT object_type_id, table_name, status, last_updated FROM canonical_object_types")
                        rows = list(results)
                        if rows:
                            st.markdown("**Canonical Object Types Registered:**")
                            st.write(rows)
                        else:
                            st.info("No objects registered in `canonical_object_types` table yet. Deploy the ontology first.")
                except Exception as e:
                    st.error(f"Error querying registry tables: {e}")

        st.markdown("</div>", unsafe_allow_html=True)

# TAB 2: Ingestion Zone
with tab2:
    st.markdown("### Telemetry Data Library & Extraction Zone")
    
    col_ing1, col_ing2 = st.columns(2)
    
    # Store dynamic text in session state
    if "vector_store" not in st.session_state:
        st.session_state.vector_store = MockVectorStore()
        
    with col_ing1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Current Unstructured Documents")
        for doc in st.session_state.vector_store.documents:
            st.markdown(f"**{doc['id']}** ({doc['entities'].get('node_id') or doc['entities'].get('segment_id') or list(doc['entities'].keys())[0]} target)")
            st.info(doc['text'])
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_ing2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Add New Telemetry / Maintenance Logs")
        new_id = st.text_input("Document ID:", value="doc_chunk_4")
        new_text = st.text_area("Log Content:", value="Operational Note: Emergency fuel transfers completed at Dallas Segment.")
        target_entity = st.selectbox("Link to Entity:", ["network_routing", "network_routing_segment"])
        
        if st.button("Index Document"):
            st.session_state.vector_store.documents.append({
                "id": new_id,
                "text": new_text,
                "entities": {target_entity: target_entity}
            })
            # Generate mock embedding
            st.session_state.vector_store.embeddings[new_id] = np.random.rand(128)
            st.success(f"Successfully chunked and indexed {new_id} to Vector Search.")
        st.markdown("</div>", unsafe_allow_html=True)

# TAB 3: GraphRAG Serving
with tab3:
    st.markdown("### Interactive Graph-Backed Retrieval (GraphRAG)")
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Ask the Serving Plane")
    
    sample_queries = [
        "Why is operational capacity degraded at the Chicago Hub, and what is the transit mode to its segments?",
        "What segments connect to Chicago Logistics Hub?"
    ]
    query_input = st.selectbox("Select a sample query or write your own below:", sample_queries)
    custom_query = st.text_input("Your Custom Query:", value="")
    
    active_query = custom_query if custom_query else query_input
    
    if st.button("Run GraphRAG Retriever"):
        # 1. Semantic Search
        st.markdown("<div class='step-header'>Step 1: Semantic Document Retrieval</div>", unsafe_allow_html=True)
        with st.spinner("Executing similarity search over indexed chunks..."):
            results = st.session_state.vector_store.semantic_search(active_query, top_k=1)
            matched = results[0]["document"]
            score = results[0]["score"]
            st.write(f"Matched Document ID: `{matched['id']}` (Cosine Similarity: `{score:.4f}`)")
            st.info(matched["text"])
            
        # 2. Spanner Graph Expansion
        st.markdown("<div class='step-header'>Step 2: Spanner Graph Path Expansion</div>", unsafe_allow_html=True)
        with st.spinner("Traversing Spanner Graph paths..."):
            if not is_live:
                # Simulated query expansion
                graph_db = SpannerGraphSimulator()
                graph_expansion = graph_db.execute_graph_expansion("CHI-NODE-01")
            else:
                # Real Spanner Graph query execution
                try:
                    with registry_manager.spanner_db.snapshot() as snapshot:
                        gql_query = (
                            "GRAPH LogisticsRoutingGraph "
                            "MATCH (n:NetworkRouting {node_id: 'CHI-NODE-01'})-[e:TRANSIT_PATH]->(s:RoutingSegment) "
                            "RETURN n.name AS name, n.capacity AS capacity, s.segment_id AS target_segment_id, e.transit_mode AS transit_mode, e.avg_duration_hours AS avg_duration"
                        )
                        results = snapshot.execute_sql(gql_query)
                        rows = list(results)
                        
                        if rows:
                            # Build response mapping matching Spanner Graph query schema
                            graph_expansion = {
                                "start_node": {
                                    "id": "CHI-NODE-01",
                                    "details": {"name": rows[0][0], "capacity": rows[0][1]}
                                },
                                "connections": [{
                                    "target_segment_id": row[2],
                                    "transit_mode": row[3],
                                    "avg_duration_hours": row[4],
                                    "segment_details": {"status": "ACTIVE"}
                                } for row in rows]
                            }
                        else:
                            st.warning("⚠️ No Spanner Graph query paths returned. Seeding simulated nodes into Spanner Graph to run...")
                            
                            # Auto-seed basic data to make the live demo work instantly
                            def _seed_spanner(transaction):
                                transaction.execute_update(
                                    "INSERT OR UPDATE INTO network_routing (node_id, name, capacity) VALUES "
                                    "('CHI-NODE-01', 'Chicago Logistics Hub', 1200), "
                                    "('NYC-NODE-02', 'New York Distribution Center', 2500)"
                                )
                                transaction.execute_update(
                                    "INSERT OR UPDATE INTO network_routing_segment (segment_id, origin_node_id, destination_node_id, status) VALUES "
                                    "('SEG-CHI-NYC-01', 'CHI-NODE-01', 'NYC-NODE-02', 'ACTIVE')"
                                )
                                transaction.execute_update(
                                    "INSERT OR UPDATE INTO transit_path (path_id, source_id, target_id, transit_mode, avg_duration_hours) VALUES "
                                    "('PATH-01', 'CHI-NODE-01', 'SEG-CHI-NYC-01', 'Freight Train', 14.5)"
                                )
                            
                            registry_manager.spanner_db.run_in_transaction(_seed_spanner)
                            st.info("Successfully seeded demo data in Spanner! Re-running query...")
                            
                            # Retry GQL query
                            results = snapshot.execute_sql(gql_query)
                            rows = list(results)
                            graph_expansion = {
                                "start_node": {
                                    "id": "CHI-NODE-01",
                                    "details": {"name": rows[0][0], "capacity": rows[0][1]}
                                },
                                "connections": [{
                                    "target_segment_id": row[2],
                                    "transit_mode": row[3],
                                    "avg_duration_hours": row[4],
                                    "segment_details": {"status": "ACTIVE"}
                                } for row in rows]
                            }
                except Exception as ge:
                    st.error(f"GCP Spanner Graph GQL Query failed: {ge}")
                    st.info("Ensure the Spanner Graph schema is compiled and deployed, and your instance supports Graph features.")
                    # Fallback to simulated mapping to keep the presentation running
                    graph_db = SpannerGraphSimulator()
                    graph_expansion = graph_db.execute_graph_expansion("CHI-NODE-01")
            
            col_gr1, col_gr2 = st.columns(2)
            with col_gr1:
                st.markdown("**Starting Graph Node (NetworkRouting)**")
                st.write(graph_expansion["start_node"]["details"])
            with col_gr2:
                st.markdown("**Traversed Edge Links (TRANSIT_PATH -> RoutingSegment)**")
                st.write(graph_expansion["connections"])
                
        # 3. Context Integration & Generation
        st.markdown("<div class='step-header'>Step 3: Answer Ingestion & Synthesis</div>", unsafe_allow_html=True)
        
        # Build context
        context_payload = (
            f"--- UNSTRUCTURED DOCUMENT EVIDENCE ---\n"
            f"{matched['text']}\n\n"
            f"--- STRUCTURED GRAPH RETRIEVED RELATIONSHIPS ---\n"
            f"Hub Node: {graph_expansion['start_node']['details']['name']} (Capacity: {graph_expansion['start_node']['details']['capacity']})\n"
            f"Segment Link: {graph_expansion['connections'][0]['target_segment_id']} (Transit Mode: {graph_expansion['connections'][0]['transit_mode']}, Average Duration: {graph_expansion['connections'][0]['avg_duration_hours']} hours, Status: {graph_expansion['connections'][0]['segment_details']['status']})\n"
        )
        
        with st.expander("Show Assembled Context Window Payload"):
            st.text(context_payload)
            
        st.markdown("**Synthesized Answer:**")
        answer_text = (
            f"Based on the combined evidence:\n\n"
            f"1. Unstructured logs reveal that the **{graph_expansion['start_node']['details']['name']}** (CHI-NODE-01) "
            f"is experiencing power fluctuations causing a 40% operational capacity reduction (temporary capacity reduced to 720 units).\n"
            f"2. Spanner Graph paths reveal that this hub connects to segment **{graph_expansion['connections'][0]['target_segment_id']}** "
            f"via **{graph_expansion['connections'][0]['transit_mode']}** with an average duration of **{graph_expansion['connections'][0]['avg_duration_hours']} hours**.\n"
            f"3. The connection is currently **{graph_expansion['connections'][0]['segment_details']['status']}**.\n\n"
            f"*Conclusion*: Logistics delays should be expected at Chicago Hub, but downstream transit connections remain healthy."
        )
        st.success(answer_text)
    st.markdown("</div>", unsafe_allow_html=True)
