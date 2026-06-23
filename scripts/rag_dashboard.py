import streamlit as st
import json
import os
import sys
import yaml
import numpy as np
from pyvis.network import Network
import streamlit.components.v1 as components

# Adjust sys.path to resolve local packages in the workspace root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.orchestrator import SpannerRegistryManager, Orchestrator
from scripts.graph_compiler import GraphCompiler
from scripts.run_ontology_to_graph_rag_demo import MockVectorStore, SpannerGraphSimulator

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    from vertexai.language_models import TextEmbeddingModel
except ImportError:
    pass

class VertexAIVectorStore:
    """Uses Vertex AI Text Embeddings model to generate real embeddings and perform semantic search."""
    def __init__(self, project: str, location: str):
        self.documents = [
            {
                "id": "doc_chunk_1",
                "text": "Incident Report: OAK-STN origin station is experiencing severe gate congestion today due to local power fluctuations. Segments originating from OAK may suffer dispatch delays.",
                "entities": {"routing_id": "NR-001"}
            },
            {
                "id": "doc_chunk_2",
                "text": "Maintenance Log: The air corridor segment SEG-002 from OAK-RAMP to MEM-HUB is running smoothly. Average duration remains constant.",
                "entities": {"segment_id": "SEG-002"}
            },
            {
                "id": "doc_chunk_3",
                "text": "Telemetry alert: High wind warnings are currently active along the transit corridor between Chicago and Dallas segments.",
                "entities": {"segment_id": "SEG-002"}
            }
        ]
        try:
            vertexai.init(project=project, location=location)
            self.model = TextEmbeddingModel.from_pretrained("text-embedding-004")
            texts = [doc["text"] for doc in self.documents]
            embeddings = self.model.get_embeddings(texts)
            self.embeddings = {doc["id"]: np.array(emb.values) for doc, emb in zip(self.documents, embeddings)}
            self.enabled = True
        except Exception as e:
            st.error(f"Failed to initialize Vertex AI TextEmbeddingModel: {e}")
            self.enabled = False
            self.embeddings = {doc["id"]: np.random.rand(768) for doc in self.documents}

    def _embed_text(self, text: str) -> np.ndarray:
        """Embed a single string using Vertex AI, falling back to rand(768) on failure."""
        if self.enabled:
            try:
                return np.array(self.model.get_embeddings([text])[0].values)
            except Exception:
                pass
        return np.random.rand(768)

    def add_document(self, doc: dict) -> None:
        """Append a document and embed it with the same model used at init time."""
        self.documents.append(doc)
        self.embeddings[doc["id"]] = self._embed_text(doc["text"])

    def semantic_search(self, query: str, top_k: int = 1) -> list:
        query_emb = self._embed_text(query)

        scores = []
        for doc_id, doc_vector in self.embeddings.items():
            dot_product = np.dot(query_emb, doc_vector)
            norm_q = np.linalg.norm(query_emb)
            norm_d = np.linalg.norm(doc_vector)
            score = dot_product / (norm_q * norm_d) if (norm_q > 0 and norm_d > 0) else 0.0
            scores.append((doc_id, score))
            
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for i in range(min(top_k, len(scores))):
            doc_id = scores[i][0]
            doc = next(d for d in self.documents if d["id"] == doc_id)
            results.append({
                "document": doc,
                "score": float(scores[i][1])
            })
        return results


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

st.session_state.yamls = yamls

def load_ontology_graph_config(yaml_dict: dict) -> dict:
    nodes = []
    edges = []
    for f_name, content in yaml_dict.items():
        try:
            spec = yaml.safe_load(content)
            if not spec: continue
            kind = spec.get("kind")
            table = spec.get("spec", {}).get("table")
            pk = spec.get("spec", {}).get("primaryKey", [])
            pk = pk[0] if pk else None
            attrs = [a["name"] for a in spec.get("spec", {}).get("attributes", [])]
            
            if kind == "ObjectType":
                if table and pk:
                    nodes.append({
                        "view": f"v_{table}",
                        "table": table,
                        "key": pk,
                        "properties": attrs,
                    })
            elif kind == "RelationshipType":
                source_key = spec.get("spec", {}).get("sourceKey")
                target_key = spec.get("spec", {}).get("targetKey")
                if not source_key or not target_key:
                    continue
                if table and pk:
                    edges.append({
                        "view": f"v_{table}",
                        "table": table,
                        "key": pk,
                        "source": source_key,
                        "target": target_key,
                        "properties": attrs,
                    })
        except Exception:
            pass
    return {"nodes": nodes, "edges": edges}

def fetch_graph_data(config: dict, spanner_db) -> tuple[list, list]:
    nodes_res = []
    for node in config["nodes"]:
        cols = ", ".join(node["properties"]) if node["properties"] else "1"
        query = f"SELECT '{node['table']}', CAST({node['key']} AS STRING), {cols} FROM {node['view']}"
        with spanner_db.snapshot() as snap:
            for row in snap.execute_sql(query):
                entity_type = row[0]
                key = str(row[1]) if row[1] is not None else ""
                props = dict(zip(node["properties"], row[2:])) if node["properties"] else {}
                nodes_res.append((entity_type, key, json.dumps(props)))

    edges_res = []
    for edge in config["edges"]:
        cols = ", ".join(edge["properties"]) if edge["properties"] else "1"
        query = f"SELECT '{edge['table']}', CAST({edge['key']} AS STRING), CAST({edge['source']} AS STRING), CAST({edge['target']} AS STRING), {cols} FROM {edge['view']}"
        with spanner_db.snapshot() as snap:
            for row in snap.execute_sql(query):
                rel_type = row[0]
                key = str(row[1]) if row[1] is not None else ""
                source = str(row[2]) if row[2] is not None else ""
                target = str(row[3]) if row[3] is not None else ""
                props = dict(zip(edge["properties"], row[4:])) if edge["properties"] else {}
                edges_res.append((rel_type, key, source, target, json.dumps(props)))
                
    return nodes_res, edges_res

COLOR_MAP = {
    "STATION":  "#1a73e8",
    "HUB":      "#F4A623",
    "RAMP":     "#00bfa5",
    "GATEWAY":  "#9C27B0",
    "vehicle":          "#E91E8C",
    "driver":           "#FF5722",
    "maintenance_log":  "#607D8B",
}

# Sidebar Setup
st.sidebar.title("🛠️ Mode & Connection")
conn_mode = st.sidebar.radio(
    "Select Backend Connection Mode:",
    ["Simulated (Mocked)", "Live Google Cloud Spanner"]
)

# Gemini API Key Setup in Sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("🤖 GenAI Configuration")
gemini_key = st.sidebar.text_input("Gemini API Key:", type="password", value=os.environ.get("GEMINI_API_KEY", ""))

spanner_project = ""
spanner_instance = ""
spanner_database = ""

if conn_mode == "Live Google Cloud Spanner":
    st.sidebar.markdown("---")
    st.sidebar.subheader("Spanner Configuration")
    spanner_project = st.sidebar.text_input("GCP Project ID:", value=os.environ.get("GOOGLE_CLOUD_PROJECT", "migiration-demo"))
    spanner_instance = st.sidebar.text_input("Spanner Instance ID:", value="ontology-demo")
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

# Reset vector store when switching connection modes to reload correct backend
if "last_conn_mode" not in st.session_state or st.session_state.last_conn_mode != conn_mode:
    st.session_state.last_conn_mode = conn_mode
    if "vector_store" in st.session_state:
        del st.session_state.vector_store

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎛️ Control Plane (Compiler)", 
    "📥 Ingestion Zone (Telemetry)", 
    "🔍 Serving Plane (GraphRAG)",
    "🛡️ Governance & Audit",
    "🌐 Graph Explorer"
])

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
                            
                            compiler = GraphCompiler(
                                compatibility_status=plan_info["status"], 
                                schema_diffs=plan_info["schema_diffs"]
                            )
                            compilation_plan = compiler.compile_plan(yamls_list, graph_yaml)
                            
                            if compilation_plan["status"] == "BLOCKED_BREAKING":
                                st.error("❌ Compilation Blocked: Breaking change detected.")
                                st.json(compilation_plan["migration_recipe"])
                            else:
                                # Apply compiled DDLs (strip trailing semicolons required by Spanner update_ddl API)
                                ddl_statements = [stmt.rstrip(";") for stmt in compilation_plan["actions"] if stmt.strip()]
                                # Prepend DROP PROPERTY GRAPH to break the dependency lock on views
                                # (Disabled to support Spanner Standard Edition / Free Trial)
                                # if graph_yaml:
                                #     graph_name = graph_yaml.get("spec", {}).get("graphName", "air_routing_graph")
                                #     ddl_statements.insert(0, f"DROP PROPERTY GRAPH IF EXISTS {graph_name}")
                                
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
            st.markdown("##### Live Data Ingestion")
            if st.button("Trigger Dataflow Bulk Load"):
                import subprocess
                st.info("Starting Dataflow ingestion via DirectRunner...")
                log_container = st.empty()
                log_text = ""
                cmd = [
                    "python", "dataflow/ontology_bulk_load/pipeline.py", 
                    "--input_dir", "ontology/test_data",
                    "--ontology_dir", "ontology",
                    "--project_id", spanner_project,
                    "--instance_id", spanner_instance, 
                    "--database_id", spanner_database
                ]
                try:
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        env={**os.environ, "PYTHONUNBUFFERED": "1"},
                        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                    )
                    for line in iter(process.stdout.readline, ''):
                        log_text += line
                        log_text = log_text[-3000:]
                        log_container.code(log_text, language="bash")
                    process.stdout.close()
                    process.wait(timeout=120)
                    if process.returncode == 0:
                        st.success("✔️ Dataflow ingestion completed successfully!")
                    else:
                        st.error(f"❌ Dataflow failed with exit code {process.returncode}")
                except Exception as e:
                    st.error(f"Pipeline execution failed: {e}")
                    
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
        if is_live:
            st.session_state.vector_store = VertexAIVectorStore(project=spanner_project, location="us-central1")
        else:
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
            new_doc = {
                "id": new_id,
                "text": new_text,
                "entities": {target_entity: target_entity}
            }
            with st.spinner("Embedding document..."):
                st.session_state.vector_store.add_document(new_doc)
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
                graph_expansion = graph_db.execute_graph_expansion("NR-001")
            else:
                # Real Spanner Graph query execution via Standard SQL JOIN (Spanner Standard compatibility)
                try:
                    from google.cloud import spanner
                    with registry_manager.spanner_db.snapshot() as snapshot:
                        sql_query = """
                        SELECT
                          r.routing_id,
                          r.service_commit,
                          s.segment_id,
                          s.transport_mode,
                          s.weight
                        FROM v_network_routing r
                        JOIN v_network_routing_segment s ON s.routing_id = r.routing_id
                        WHERE r.routing_id = @routing_id
                        ORDER BY s.segment_id
                        """
                        results = snapshot.execute_sql(
                            sql_query,
                            params={"routing_id": "NR-001"},
                            param_types={"routing_id": spanner.param_types.STRING}
                        )
                        rows = list(results)
                        
                        st.caption("💡 Graph context retrieved via relational traversal (SQL JOIN). In production, this uses GQL on Spanner Enterprise.")
                        
                        if rows:
                            # Build response mapping matching Spanner Graph query schema
                            graph_expansion = {
                                "start_node": {
                                    "id": "NR-001",
                                    "details": {"routing_id": rows[0][0], "service_commit": rows[0][1]}
                                },
                                "connections": [{
                                    "target_segment_id": row[2],
                                    "transport_mode": row[3],
                                    "weight": row[4],
                                    "segment_details": {"status": "ACTIVE"}
                                } for row in rows]
                            }
                        else:
                            st.warning("⚠️ No Spanner records returned. Run Dataflow ingestion in Tab 1 to load the data!")
                            graph_db = SpannerGraphSimulator()
                            graph_expansion = graph_db.execute_graph_expansion("NR-001")
                except Exception as ge:
                    st.error(f"GCP Spanner Graph relational query failed: {ge}")
                    # Fallback to simulated mapping to keep the presentation running
                    graph_db = SpannerGraphSimulator()
                    graph_expansion = graph_db.execute_graph_expansion("NR-001")
            
            col_gr1, col_gr2 = st.columns(2)
            with col_gr1:
                st.markdown("**Starting Graph Node (NetworkRouting)**")
                st.write(graph_expansion["start_node"]["details"])
            with col_gr2:
                st.markdown("**Traversed Edge Links (HAS_SEGMENT -> NetworkRoutingSegment)**")
                st.write(graph_expansion["connections"])
                
        # 3. Context Integration & Generation
        st.markdown("<div class='step-header'>Step 3: Answer Ingestion & Synthesis</div>", unsafe_allow_html=True)
        
        # Build context
        context_payload = (
            f"--- SYSTEM MIGRATION CONTEXT EVIDENCE ---\n"
            f"Unstructured Log Evidence:\n{matched['text']}\n\n"
            f"Structured Spanner Graph Traversal:\n"
            f"- Starting Route Node: {graph_expansion['start_node']['id']} (Commitment: {graph_expansion['start_node']['details']['service_commit']})\n"
            f"- Connected Segment: {graph_expansion['connections'][1]['target_segment_id']} (Transport Mode: {graph_expansion['connections'][1]['transport_mode']}, Weight: {graph_expansion['connections'][1]['weight']} kg, Status: ACTIVE)\n"
        )
        
        with st.expander("Show Assembled Context Window Payload"):
            st.text(context_payload)
            
        st.markdown("**Synthesized Answer:**")
        
        if is_live:
            with st.spinner("Synthesizing answer using Google Vertex AI (Gemini 1.5)..."):
                try:
                    vertexai.init(project=spanner_project, location="us-central1")
                    prompt = (
                        f"You are a helpful logistics and infrastructure database assistant. Answer the user query using ONLY the provided contexts.\n\n"
                        f"Context details:\n{context_payload}\n\n"
                        f"User Query: {active_query}\n\n"
                        f"Answer:"
                    )
                    try:
                        model = GenerativeModel("gemini-1.5-flash-001")
                        response = model.generate_content(prompt)
                        st.success(response.text)
                    except Exception as fallback_err:
                        model = GenerativeModel("gemini-1.0-pro-001")
                        response = model.generate_content(prompt)
                        st.success(response.text)
                except Exception as vertex_err:
                    # st.error(f"Vertex AI Gemini invocation failed: {vertex_err}")
                    st.warning("Vertex AI Quota exceeded/unavailable. Falling back to pre-compiled context generator.")
                    answer_text = (
                        f"Based on the combined evidence:\n\n"
                        f"1. Unstructured logs reveal that the origin station **OAK-STN** is experiencing severe gate congestion "
                        f"due to local power fluctuations, which may cause dispatch delays for segments originating from OAK.\n"
                        f"2. Spanner Graph paths reveal that the route **{graph_expansion['start_node']['id']}** "
                        f"has a service commitment of **{graph_expansion['start_node']['details']['service_commit']}**.\n"
                        f"3. Segment **{graph_expansion['connections'][1]['target_segment_id']}** connects OAK-RAMP to MEM-HUB "
                        f"via **{graph_expansion['connections'][1]['transport_mode']}** transport with weight **{graph_expansion['connections'][1]['weight']} kg**.\n\n"
                        f"*Conclusion*: Although dispatch delays might affect segments originating from OAK due to power fluctuations, the downstream connection to MEM-HUB via AIR remains active."
                    )
                    st.success(answer_text)
        elif gemini_key:
            with st.spinner("Synthesizing answer using Google Gemini..."):
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=gemini_key)
                    model = genai.GenerativeModel('gemini-1.5-flash-001')
                    
                    prompt = (
                        f"You are a helpful logistics and infrastructure database assistant. Answer the user query using ONLY the provided contexts.\n\n"
                        f"Context details:\n{context_payload}\n\n"
                        f"User Query: {active_query}\n\n"
                        f"Answer:"
                    )
                    
                    response = model.generate_content(prompt)
                    st.success(response.text)
                except Exception as gemini_err:
                    st.error(f"Gemini API invocation failed: {gemini_err}")
                    st.warning("Falling back to pre-compiled context generator.")
                    # Fallback to local static answer template
                    answer_text = (
                        f"Based on the combined evidence:\n\n"
                        f"1. Unstructured logs reveal that the origin station **OAK-STN** is experiencing severe gate congestion "
                        f"due to local power fluctuations, which may cause dispatch delays for segments originating from OAK.\n"
                        f"2. Spanner Graph paths reveal that the route **{graph_expansion['start_node']['id']}** "
                        f"has a service commitment of **{graph_expansion['start_node']['details']['service_commit']}**.\n"
                        f"3. Segment **{graph_expansion['connections'][1]['target_segment_id']}** connects OAK-RAMP to MEM-HUB "
                        f"via **{graph_expansion['connections'][1]['transport_mode']}** transport with weight **{graph_expansion['connections'][1]['weight']} kg**.\n\n"
                        f"*Conclusion*: Although dispatch delays might affect segments originating from OAK due to power fluctuations, the downstream connection to MEM-HUB via AIR remains active."
                    )
                    st.success(answer_text)
        else:
            st.info("💡 Pro-Tip: Provide your Gemini API Key in the sidebar or run in Live Mode to generate live synthesized answers.")
            # Fallback to local static answer template
            answer_text = (
                f"Based on the combined evidence:\n\n"
                f"1. Unstructured logs reveal that the origin station **OAK-STN** is experiencing severe gate congestion "
                f"due to local power fluctuations, which may cause dispatch delays for segments originating from OAK.\n"
                f"2. Spanner Graph paths reveal that the route **{graph_expansion['start_node']['id']}** "
                f"has a service commitment of **{graph_expansion['start_node']['details']['service_commit']}**.\n"
                f"3. Segment **{graph_expansion['connections'][1]['target_segment_id']}** connects OAK-RAMP to MEM-HUB "
                f"via **{graph_expansion['connections'][1]['transport_mode']}** transport with weight **{graph_expansion['connections'][1]['weight']} kg**.\n\n"
                f"*Conclusion*: Although dispatch delays might affect segments originating from OAK due to power fluctuations, the downstream connection to MEM-HUB via AIR remains active."
            )
            st.success(answer_text)
    st.markdown("</div>", unsafe_allow_html=True)

# TAB 4: Governance & Audit
with tab4:
    st.markdown("### Governance & Compliance Logs")
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Dataflow Rule Audit Logs")
    st.info("💡 Shows the results of the YAML rules evaluated against incoming telemetry data during the Dataflow ingestion pipeline.")
    
    if st.button("Query Rule Audit Table"):
        if is_live:
            try:
                with registry_manager.spanner_db.snapshot() as snapshot:
                    query = "SELECT table_name, row_key, rule_id, status, error_message, evaluated_at FROM rule_audit ORDER BY evaluated_at DESC LIMIT 50"
                    results = snapshot.execute_sql(query)
                    rows = list(results)
                    if rows:
                        import pandas as pd
                        df = pd.DataFrame(rows, columns=["table_name", "row_key", "rule_id", "status", "error_message", "evaluated_at"])
                        
                        # Apply coloring to status
                        def color_status(val):
                            color = '#00C853' if val == 'PASS' else '#D50000'
                            return f'color: {color}; font-weight: bold;'
                            
                        st.dataframe(df.style.map(color_status, subset=['status']), use_container_width=True)
                    else:
                        st.warning("No audit logs found. Run the Dataflow pipeline first.")
            except Exception as e:
                st.error(f"Error querying rule_audit table: {e}")
        else:
            st.warning("Connect to Live Google Cloud Spanner to view real audit logs.")
            
            # Mock Data
            st.markdown("**Simulated Audit Logs**")
            import pandas as pd
            mock_data = [
                {"table_name": "network_routing", "row_key": "NR-001", "rule_id": "NR-001", "status": "PASS", "error_message": "", "evaluated_at": "2026-06-22T10:00:00Z"},
                {"table_name": "network_routing_segment", "row_key": "SEG-005", "rule_id": "SEG-002", "status": "FAIL", "error_message": "origin (OAK) == destination (OAK)", "evaluated_at": "2026-06-22T10:05:00Z"}
            ]
            df = pd.DataFrame(mock_data)
            def color_status(val):
                color = '#00C853' if val == 'PASS' else '#D50000'
                return f'color: {color}; font-weight: bold;'
            st.dataframe(df.style.map(color_status, subset=['status']), use_container_width=True)
            
    st.markdown("</div>", unsafe_allow_html=True)

# TAB 5: Graph Explorer
with tab5:
    st.markdown("### Interactive Network Graph Visualization")
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Ontology Routing Dependencies")
    
    with st.spinner("Rendering Graph..."):
        # Build network graph
        net = Network(height="600px", width="100%", directed=True, bgcolor="#0d0f14", font_color="#e0e0e0")
        
        if is_live:
            try:
                config = load_ontology_graph_config(st.session_state.yamls)

                with registry_manager.spanner_db.snapshot() as snap:
                    # Guard against schema drift: only query views that actually exist in Spanner
                    existing_tables_res = snap.execute_sql("SELECT table_name FROM information_schema.tables")
                    existing_views = {row[0] for row in existing_tables_res}
                    
                config["nodes"] = [n for n in config["nodes"] if n["view"] in existing_views]
                config["edges"] = [e for e in config["edges"] if e["view"] in existing_views]
                
                nodes_res, edges_res = fetch_graph_data(config, registry_manager.spanner_db)
                
                if not nodes_res:
                    st.info("🗄️ Database empty. Run ingestion from Tab 1.")
                else:
                    for entity_type, key, props_json in nodes_res:
                        props = json.loads(props_json) if props_json else {}
                        op_type = props.get("operation_type")
                        
                        entity_color = (
                            COLOR_MAP.get(op_type)
                            or COLOR_MAP.get(entity_type)
                            or "#888"
                        )
                        size = 30 if op_type == "HUB" else 15
                        
                        title_text = "\n".join(f"{k}: {v}" for k, v in props.items())
                        net.add_node(
                            key,
                            label=key,
                            title=title_text,
                            color=entity_color,
                            size=size
                        )
                        
                    for rel_type, key, source, target, props_json in edges_res:
                        props = json.loads(props_json) if props_json else {}
                        title_text = "\n".join(f"{k}: {v}" for k, v in props.items())
                        net.add_edge(
                            source, target,
                            title=title_text,
                            color="#539BF5",
                            arrows="to"
                        )
            except Exception as e:
                st.error(f"Error querying graph data from Spanner: {e}")
        else:
            st.warning("Connect to Live Spanner to view dynamic graph data. Run ingestion to populate.")
        
        # Configure physics for better layout
        net.set_options("""
        var options = {
          "physics": {
            "hierarchicalRepulsion": {
              "centralGravity": 0.0,
              "springLength": 150,
              "nodeDistance": 150
            },
            "minVelocity": 0.75,
            "solver": "hierarchicalRepulsion"
          }
        }
        """)
        
        # Save and render
        html_path = "artifacts/graph.html"
        os.makedirs("artifacts", exist_ok=True)
        net.save_graph(html_path)
        
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        components.html(html_content, height=620)
        
    st.info("💡 **Impact Analysis:** The graph above highlights how multiple routings depend on the `MEM-HUB` central node. This is a visual representation of the property graph queries that power the GraphRAG serving plane.")
    
    if st.button("🔄 Refresh Graph"):
        st.cache_data.clear()
        st.rerun()
        
    st.markdown("</div>", unsafe_allow_html=True)
