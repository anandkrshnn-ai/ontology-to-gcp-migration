import os
os.environ["GOOGLE_CLOUD_DISABLE_GRPC_METRICS"] = "true"

import streamlit as st
import json
import sys
import yaml
import numpy as np
from pyvis.network import Network

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

# Material Design 3 Custom Styling
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* Global Typography */
    html, body, [class*="st-"] {
        font-family: 'Inter', sans-serif !important;
    }
    .main {
        background-color: #121212;
        color: #e0e0e0;
    }
    .stApp {
        background-color: #121212;
    }
    /* Material 3 Buttons */
    div.stButton > button {
        background-color: #1a73e8;
        color: white;
        border-radius: 24px;
        font-weight: 500;
        letter-spacing: 0.25px;
        padding: 0.5em 1.5em;
        border: none;
        transition: all 0.2s cubic-bezier(0.2, 0, 0, 1);
        box-shadow: 0 1px 2px 0 rgba(0,0,0,0.3), 0 1px 3px 1px rgba(0,0,0,0.15);
    }
    div.stButton > button:hover {
        background-color: #1557b0;
        box-shadow: 0 1px 3px 0 rgba(0,0,0,0.3), 0 4px 8px 3px rgba(0,0,0,0.15);
        transform: translateY(-1px);
    }
    /* Elevated Cards */
    .card {
        background: #1e1e1e;
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 1.5em;
        margin-bottom: 1em;
        box-shadow: 0 1px 3px 0 rgba(0,0,0,0.3), 0 4px 8px 3px rgba(0,0,0,0.15);
    }
    .step-header {
        font-weight: 600;
        font-size: 1.1em;
        color: #8ab4f8;
        margin-bottom: 0.5em;
    }
    code {
        color: #ff8a65 !important;
    }
    /* KPI Metric styling */
    div[data-testid="metric-container"] {
        background: #1e1e1e;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1em;
        box-shadow: 0 1px 2px 0 rgba(0,0,0,0.3);
    }
    div[data-testid="metric-container"] label {
        color: #9aa0a6;
    }
    div[data-testid="metric-container"] div {
        color: #e8eaed;
        font-weight: 500;
    }
    /* Terminal Console */
    .terminal-console {
        background-color: #000000;
        color: #00FF00;
        font-family: 'Courier New', Courier, monospace;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #333;
        max-height: 400px;
        overflow-y: auto;
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
        if f_name.endswith(('.yaml', '.yml')) and f_name != "ontology_graph.yaml":
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
                        "source_table": spec.get("spec", {}).get("sourceType"),
                        "target_table": spec.get("spec", {}).get("targetType"),
                        "properties": attrs,
                    })
        except Exception:
            pass

    # Hardcode missing relationship edges for Vehicle topology
    edges.append({
        "view": "v_driver",
        "table": "driver",
        "key": "driver_id",
        "source": "driver_id",
        "target": "vehicle_id",
        "source_table": "driver",
        "target_table": "vehicle",
        "properties": ["driver_id", "vehicle_id", "certification_level", "status"]
    })
    edges.append({
        "view": "v_maintenance_log",
        "table": "maintenance_log",
        "key": "log_id",
        "source": "vehicle_id",
        "target": "log_id",
        "source_table": "vehicle",
        "target_table": "maintenance_log",
        "properties": ["log_id", "vehicle_id", "issue_type", "severity"]
    })

    return {"nodes": nodes, "edges": edges}

def safe_json(props: dict) -> dict:
    import datetime
    import decimal
    result = {}
    for k, v in props.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            result[k] = v.isoformat()
        elif isinstance(v, decimal.Decimal):
            result[k] = float(v)
        else:
            result[k] = v
    return result

def fetch_graph_data(config: dict, spanner_db) -> tuple[list, list]:
    nodes_res = []
    edges_res = []
    
    # Nodes
    for node in config.get("nodes", []):
        try:
            cols = ", ".join(node.get("properties", [])) if node.get("properties") else "1"
            query = f"SELECT '{node['table']}', CAST({node['key']} AS STRING), {cols} FROM {node['view']}"
            
            with spanner_db.snapshot() as snap:
                results = snap.execute_sql(query)
                for row in results:
                    # Robust conversion
                    if hasattr(row, '_asdict'):           # Spanner Row object
                        row_values = list(row)
                    elif isinstance(row, dict):
                        row_values = list(row.values())
                    else:
                        row_values = list(row)
                    
                    entity_type = str(row_values[0]) if row_values else ""
                    key = str(row_values[1]) if len(row_values) > 1 and row_values[1] is not None else ""
                    
                    props = {}
                    if node.get("properties"):
                        for i, col_name in enumerate(node["properties"]):
                            idx = 2 + i
                            if idx < len(row_values):
                                props[col_name] = row_values[idx]
                    
                    nodes_res.append((entity_type, key, json.dumps(safe_json(props))))
        except Exception as e:
            st.warning(f"⚠️ Nodes query failed for {node.get('table')}: {e}")
            continue

    # Edges
    for edge in config.get("edges", []):
        try:
            cols = ", ".join(edge.get("properties", [])) if edge.get("properties") else "1"
            query = f"SELECT '{edge['table']}', CAST({edge['key']} AS STRING), CAST({edge['source']} AS STRING), CAST({edge['target']} AS STRING), {cols} FROM {edge['view']}"
            
            with spanner_db.snapshot() as snap:
                results = snap.execute_sql(query)
                for row in results:
                    if hasattr(row, '_asdict'):
                        row_values = list(row)
                    elif isinstance(row, dict):
                        row_values = list(row.values())
                    else:
                        row_values = list(row)
                    
                    rel_type = str(row_values[0]) if row_values else ""
                    key = str(row_values[1]) if len(row_values) > 1 else ""
                    source = str(row_values[2]) if len(row_values) > 2 else ""
                    target = str(row_values[3]) if len(row_values) > 3 else ""
                    
                    props = {}
                    if edge.get("properties"):
                        for i, col_name in enumerate(edge["properties"]):
                            idx = 4 + i
                            if idx < len(row_values):
                                props[col_name] = row_values[idx]
                    
                    edges_res.append((rel_type, key, source, target, json.dumps(safe_json(props))))
        except Exception as e:
            st.warning(f"⚠️ Edges query failed for {edge.get('table')}: {e}")
            continue
                
    return nodes_res, edges_res

def fetch_graph_data_gql(spanner_db):
    """Safe GQL-based graph data fetch with fallback."""
    nodes_res = []
    edges_res = []
    try:
        gql_query = """
        GRAPH LogisticsGraph
        MATCH (d:driver)-[r:operates]->(v:vehicle)-[s:stationed_at]->(h:hub)
        RETURN 
          d.driver_id AS driver_id,
          d.name AS driver_name,
          v.vehicle_id AS vehicle_id,
          v.operation_type AS vehicle_type,
          h.hub_id AS hub_id,
          h.location_code AS hub_location
        """
        with spanner_db.snapshot() as snapshot:
            results = snapshot.execute_sql(gql_query)
            for row in results:
                # Robust row handling
                if hasattr(row, "_asdict"):
                    row = list(row)

                driver_id = str(row[0])
                driver_name = row[1]
                vehicle_id = str(row[2])
                vehicle_type = row[3]
                hub_id = str(row[4])
                hub_location = row[5]

                # Nodes: (entity_type, key, props_json)
                nodes_res.append(
                    ("driver", driver_id, json.dumps({"name": driver_name}))
                )
                nodes_res.append(
                    (
                        "vehicle",
                        vehicle_id,
                        json.dumps({"operation_type": vehicle_type}),
                    )
                )
                nodes_res.append(
                    (
                        "hub",
                        hub_id,
                        json.dumps({"location_code": hub_location}),
                    )
                )

                # Edges: (rel_type, key, source, target, props_json)
                edges_res.append(
                    (
                        "operates",
                        f"{driver_id}-{vehicle_id}",
                        driver_id,
                        vehicle_id,
                        "{}",
                    )
                )
                edges_res.append(
                    (
                        "stationed_at",
                        f"{vehicle_id}-{hub_id}",
                        vehicle_id,
                        hub_id,
                        "{}",
                    )
                )
    except Exception as e:
        st.warning(f"GQL query failed: {e}")

    return nodes_res, edges_res


COLOR_MAP = {
    "HUB": "#F59E0B",      # Gold - Central
    "STATION": "#3B82F6",
    "RAMP": "#10B981",
    "GATEWAY": "#8B5CF6",
    "vehicle": "#EC4899",
    "driver": "#F97316",
    "maintenance_log": "#64748B",
    "network_routing": "#22D3EE",
}

# Sidebar Setup
st.sidebar.title("🛠️ Mode & Connection")
conn_mode = st.sidebar.radio(
    "Select Backend Connection Mode:",
    ["Simulated (Mocked)", "Live Google Cloud Spanner"],
    index=0
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
        import os
        if mock:
            return SpannerRegistryManager(mock=True), None
        
        # Override quota project so the client doesn't use a deleted default project
        os.environ["GOOGLE_CLOUD_QUOTA_PROJECT"] = project

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
        st.sidebar.success("🟢 Live Spanner Connected")
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
    "📥 Ingestion Zone (Future)", 
    "🔍 Serving Plane (Future)",
    "🛡️ Governance & Audit",
    "🌐 Graph Explorer"
])

# TAB 1: Control Plane - FIX
with tab1:
    st.markdown("### Structural Ontology Registry & Compilation")
    
    # KPIs
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric(label="Registry State", value="Active" if is_live else "Simulated")
    with m2:
        st.metric(label="Ontology Entities", value=str(len(st.session_state.yamls)))
    with m3:
        st.metric(label="Dataflow Pipelines", value="Ready")

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Ontology Specs")
        if st.session_state.yamls:  # ADD CHECK
            selected_file = st.selectbox("Select raw contract to view:", list(yamls.keys()))
            if selected_file:
                st.code(yamls[selected_file], language="yaml")
        else:
            st.warning("⚠️ No YAML files found in ontology directory.")
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
                try:  # ADD TRY-EXCEPT
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
                except Exception as e:
                    st.error(f"Error generating migration plan: {e}")
        else:
            # LIVE MODE
            st.markdown("##### Live GCP Schema Operations")
            
            col_actions = st.columns(2)
            with col_actions[0]:
                if st.button("Initialize Registry Metadata Tables"):
                    with st.spinner("Deploying base schema registry tables..."):
                        try:
                            ddl_path = "terraform/modules/spanner/schema.ddl"
                            if not os.path.exists(ddl_path):
                                st.error(f"DDL file not found: {ddl_path}")
                            else:
                                with open(ddl_path, "r", encoding="utf-8") as f:
                                    ddl_text = f.read()
                                
                                statements = [stmt.strip() for stmt in ddl_text.split(";") if stmt.strip()]
                                operation = registry_manager.spanner_db.update_ddl(statements)
                                operation.result()
                                st.success("✔️ Metadata registry tables successfully created in Spanner!")
                        except FileNotFoundError as fe:
                            st.error(f"File not found: {fe}")
                        except Exception as e:
                            st.error(f"Failed to apply schema.ddl: {e}")
                            
            with col_actions[1]:
                if st.button("Deploy Current Ontology to Spanner"):
                    with st.spinner("Compiling and applying ontology configuration..."):
                        try:
                            orchestrator = Orchestrator(registry_manager)
                            plan_info = orchestrator.run_plan(ontology_dir)
                            
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
                                ddl_statements = [stmt.rstrip(";") for stmt in compilation_plan["actions"] if stmt.strip()]
                                
                                logistics_graph_ddl = """
                                CREATE PROPERTY GRAPH LogisticsGraph
                                NODE TABLES (
                                  driver LABEL driver,
                                  vehicle LABEL vehicle,
                                  hub LABEL hub
                                )
                                EDGE TABLES (
                                  driver_vehicle
                                    SOURCE KEY (driver_id)
                                    DESTINATION KEY (vehicle_id)
                                    LABEL operates,
                                  vehicle_hub
                                    SOURCE KEY (vehicle_id)
                                    DESTINATION KEY (hub_id)
                                    LABEL stationed_at
                                )
                                """
                                ddl_statements.append(logistics_graph_ddl.strip().rstrip(";"))
                                
                                if ddl_statements:
                                    st.info(f"Deploying {len(ddl_statements)} DDL statements to Spanner...")
                                    operation = registry_manager.spanner_db.update_ddl(ddl_statements)
                                    operation.result()
                                    
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
                        if any(skip in line for skip in [
                            "INFO:root:Missing pipeline",
                            "INFO:apache_beam",
                            "Failed to export metrics",
                            "Creating state cache",
                            "INFO:root:Running"
                        ]):
                            continue
                        log_text += line
                        log_text = log_text[-3000:]
                        log_container.markdown(f'<div class="terminal-console"><pre>{log_text}</pre></div>', unsafe_allow_html=True)
                    process.stdout.close()
                    process.wait(timeout=120)
                    if process.returncode == 0:
                        st.success("✔️ Dataflow ingestion completed successfully!")
                    else:
                        st.error(f"❌ Dataflow failed with exit code {process.returncode}")
                except subprocess.TimeoutExpired:
                    process.kill()
                    st.error("Pipeline execution timed out (120s limit)")
                except Exception as e:
                    st.error(f"Pipeline execution failed: {e}")
                    
            st.markdown("---")
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



# TAB 2: Ingestion Zone - FIXED FOR SIMULATED MODE
with tab2:
    st.markdown("### Telemetry Data Library & Extraction Zone")
    st.info("🚧 **Current Mode:** Running with MockVectorStore (simulated embeddings). Switch to Live Mode in sidebar to use Vertex AI.")
    
    # Initialize vector store with better error handling
    if "vector_store" not in st.session_state:
        try:
            if is_live:
                try:
                    st.session_state.vector_store = VertexAIVectorStore(project=spanner_project, location="us-central1")
                    st.session_state.using_vertex_ai = True
                except Exception as vertex_err:
                    st.warning(f"⚠️ Vertex AI initialization failed: {vertex_err}")
                    st.info("Falling back to MockVectorStore for demonstration purposes.")
                    st.session_state.vector_store = MockVectorStore()
                    st.session_state.using_vertex_ai = False
            else:
                st.session_state.vector_store = MockVectorStore()
                st.session_state.using_vertex_ai = False
        except Exception as e:
            st.error(f"Failed to initialize vector store: {e}")
            st.session_state.vector_store = MockVectorStore()
            st.session_state.using_vertex_ai = False
    
    # Show which backend is active
    backend_status = "Vertex AI 🔵" if st.session_state.using_vertex_ai else "MockVectorStore 🟡"
    st.caption(f"**Vector Store Backend:** {backend_status}")
    
    col_ing1, col_ing2 = st.columns(2)
    
    with col_ing1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("📚 Current Unstructured Documents")
        
        if st.session_state.vector_store and hasattr(st.session_state.vector_store, 'documents'):
            if st.session_state.vector_store.documents:
                for idx, doc in enumerate(st.session_state.vector_store.documents):
                    # Extract entity type safely
                    entity_info = doc.get('entities', {})
                    entity_key = next(iter(entity_info.keys())) if entity_info else "unknown"
                    entity_val = next(iter(entity_info.values())) if entity_info else "N/A"
                    
                    with st.expander(f"**{doc['id']}** → `{entity_val}`", expanded=(idx == 0)):
                        st.caption(f"Entity Type: `{entity_key}`")
                        st.info(doc['text'])
                        st.caption(f"📊 Embeddings: {'Real (Vertex AI)' if st.session_state.using_vertex_ai else 'Simulated (768-dim random)'}")
            else:
                st.warning("⚠️ No documents in vector store.")
        else:
            st.error("Vector store not initialized properly.")
        
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_ing2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("➕ Add New Telemetry / Maintenance Log")
        
        new_id = st.text_input("Document ID:", value="doc_chunk_4", key="doc_id_input")
        new_text = st.text_area(
            "Log Content:", 
            value="Operational Note: Emergency fuel transfers completed at Dallas Segment.",
            height=100,
            key="doc_content_input"
        )
        target_entity = st.selectbox(
            "Link to Entity:", 
            ["network_routing", "network_routing_segment", "routing_id", "segment_id"],
            key="entity_select"
        )
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("🔐 Index Document", use_container_width=True):
                if not new_id or not new_text:
                    st.error("❌ Document ID and Content are required.")
                elif len(new_id) > 50:
                    st.error("❌ Document ID too long (max 50 chars).")
                else:
                    try:
                        with st.spinner("⏳ Embedding document..."):
                            new_doc = {
                                "id": new_id,
                                "text": new_text,
                                "entities": {target_entity: target_entity}
                            }
                            st.session_state.vector_store.add_document(new_doc)
                        
                        st.success(f"✔️ Successfully indexed `{new_id}` to Vector Search!")
                        st.caption(f"Backend: {backend_status}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to index document: {e}")
        
        with col_btn2:
            if st.button("🗑️ Clear All Documents", use_container_width=True):
                if st.session_state.vector_store:
                    st.session_state.vector_store.documents = []
                    st.session_state.vector_store.embeddings = {}
                    st.success("✔️ All documents cleared!")
                    st.rerun()
        
        st.markdown("---")
        st.markdown("**ℹ️ Tips:**")
        st.caption(
            "- Documents are embedded using cosine similarity\n"
            "- In **Live Mode** with Vertex AI enabled, real embeddings are generated\n"
            "- In **Simulated Mode**, random 768-dim vectors are used\n"
            "- Use documents to provide context for GraphRAG queries (Tab 3)"
        )
        
        st.markdown("</div>", unsafe_allow_html=True)

    # VECTOR STORE STATISTICS
    st.markdown("---")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    
    with col_stat1:
        if st.session_state.vector_store and hasattr(st.session_state.vector_store, 'documents'):
            st.metric(label="Total Documents", value=len(st.session_state.vector_store.documents))
    
    with col_stat2:
        if st.session_state.vector_store and hasattr(st.session_state.vector_store, 'embeddings'):
            st.metric(label="Indexed Embeddings", value=len(st.session_state.vector_store.embeddings))
    
    with col_stat3:
        st.metric(label="Embedding Dimension", value="768")
    
    # TEST SEMANTIC SEARCH
    st.markdown("---")
    st.subheader("🔍 Test Semantic Search")
    test_query = st.text_input(
        "Enter a test query:",
        value="What operational issues affect Chicago Hub?",
        key="search_query"
    )
    
    if st.button("Search Documents", use_container_width=True):
        if not test_query:
            st.error("❌ Please enter a search query.")
        else:
            try:
                with st.spinner("⏳ Searching..."):
                    results = st.session_state.vector_store.semantic_search(test_query, top_k=2)
                
                if results:
                    st.success(f"✔️ Found {len(results)} matching document(s)")
                    for idx, result in enumerate(results, 1):
                        doc = result["document"]
                        score = result["score"]
                        
                        col_result_text, col_result_score = st.columns([3, 1])
                        with col_result_text:
                            st.markdown(f"**#{idx} {doc['id']}**")
                            st.info(doc['text'])
                        with col_result_score:
                            st.metric(
                                "Similarity",
                                f"{score:.3f}",
                                delta="Match ✓" if score > 0.5 else "Partial"
                            )
                else:
                    st.warning("⚠️ No documents found.")
            except Exception as e:
                st.error(f"❌ Search failed: {e}")



# TAB 3: GraphRAG Serving - COMPLETE FIXED VERSION
with tab3:
    st.markdown("### Interactive Graph-Backed Retrieval (GraphRAG)")
    st.info("🚀 **Real-time demonstration:** Combines semantic search + graph traversal + LLM synthesis")
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Ask the Serving Plane")
    
    sample_queries = [
        "Why is operational capacity degraded at the Chicago Hub, and what is the transit mode to its segments?",
        "What segments connect to Chicago Logistics Hub?",
        "Which routes are affected by power fluctuations at OAK-STN?",
        "What is the status of maintenance logs?"
    ]
    
    col_query_select, col_query_custom = st.columns([1, 1])
    
    with col_query_select:
        query_input = st.selectbox("Sample Query:", sample_queries, key="sample_query_select")
    
    with col_query_custom:
        custom_query = st.text_input("Or Enter Custom Query:", value="", key="custom_query_input", placeholder="Your question here...")
    
    active_query = custom_query if custom_query.strip() else query_input
    
    if st.button("▶️ Run GraphRAG Retriever", use_container_width=True):
        try:
            # STEP 1: Semantic Search
            st.markdown("<div class='step-header'>📄 Step 1: Semantic Document Retrieval</div>", unsafe_allow_html=True)
            
            with st.spinner("⏳ Executing similarity search over indexed chunks..."):
                # Initialize vector store if needed
                if "vector_store" not in st.session_state:
                    try:
                        if is_live:
                            st.session_state.vector_store = VertexAIVectorStore(project=spanner_project, location="us-central1")
                            st.session_state.using_vertex_ai = True
                        else:
                            st.session_state.vector_store = MockVectorStore()
                            st.session_state.using_vertex_ai = False
                    except Exception as vs_err:
                        st.warning(f"Vector store init failed: {vs_err}")
                        st.session_state.vector_store = MockVectorStore()
                        st.session_state.using_vertex_ai = False
                
                # Perform semantic search
                try:
                    results = st.session_state.vector_store.semantic_search(active_query, top_k=2)
                    if not results:
                        st.warning("⚠️ No documents matched the query. Using default context...")
                        # Use first document as fallback
                        if st.session_state.vector_store.documents:
                            matched = st.session_state.vector_store.documents[0]
                            score = 0.0
                        else:
                            raise ValueError("No documents in vector store")
                    else:
                        matched = results[0]["document"]
                        score = results[0]["score"]
                except Exception as search_err:
                    st.error(f"❌ Semantic search failed: {search_err}")
                    st.stop()
                
                # Display matched document
                col_match_doc, col_match_score = st.columns([3, 1])
                with col_match_doc:
                    st.write(f"**Matched:** `{matched['id']}`")
                    st.info(matched["text"])
                with col_match_score:
                    st.metric("Similarity", f"{score:.3f}", delta="Strong match ✓" if score > 0.6 else "Moderate")
            
            # STEP 2: Spanner Graph Expansion
            st.markdown("<div class='step-header'>🔗 Step 2: Spanner Graph Path Expansion</div>", unsafe_allow_html=True)
            
            graph_expansion = None
            
            with st.spinner("⏳ Traversing Spanner Graph paths..."):
                if not is_live:
                    # Simulated query expansion
                    try:
                        graph_db = SpannerGraphSimulator()
                        graph_expansion = graph_db.execute_graph_expansion("NR-001")
                        st.caption("📌 Using simulated graph (not connected to live Spanner)")
                    except Exception as sim_err:
                        st.error(f"❌ Graph simulator failed: {sim_err}")
                        graph_expansion = None
                else:
                    # Real Spanner Graph query execution
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
                            LEFT JOIN v_network_routing_segment s ON s.routing_id = r.routing_id
                            WHERE r.routing_id = @routing_id
                            ORDER BY s.segment_id
                            LIMIT 10
                            """
                            results = snapshot.execute_sql(
                                sql_query,
                                params={"routing_id": "NR-001"},
                                param_types={"routing_id": spanner.param_types.STRING}
                            )
                            rows = list(results)
                            
                            st.caption("💡 Graph context retrieved via SQL traversal (Spanner Standard)")
                            
                            if rows:
                                graph_expansion = {
                                    "start_node": {
                                        "id": "NR-001",
                                        "details": {
                                            "routing_id": rows[0][0],
                                            "service_commit": rows[0][1]
                                        }
                                    },
                                    "connections": [{
                                        "target_segment_id": row[2] if row[2] else "N/A",
                                        "transport_mode": row[3] if row[3] else "N/A",
                                        "weight": row[4] if row[4] else "N/A",
                                        "segment_details": {"status": "ACTIVE"}
                                    } for row in rows if row[2]]  # Filter out None segment_ids
                                }
                            else:
                                st.warning("⚠️ No live Spanner records. Using simulated fallback...")
                                graph_db = SpannerGraphSimulator()
                                graph_expansion = graph_db.execute_graph_expansion("NR-001")
                    
                    except Exception as spanner_err:
                        st.warning(f"⚠️ Live Spanner query failed: {spanner_err}")
                        st.info("Falling back to simulated graph...")
                        try:
                            graph_db = SpannerGraphSimulator()
                            graph_expansion = graph_db.execute_graph_expansion("NR-001")
                        except Exception as fallback_err:
                            st.error(f"❌ Graph expansion completely failed: {fallback_err}")
                            graph_expansion = None
            
            # Display graph expansion results
            if graph_expansion:
                col_gr1, col_gr2 = st.columns(2)
                with col_gr1:
                    st.markdown("**🟢 Starting Node (NetworkRouting)**")
                    with st.expander("Show Details", expanded=True):
                        st.json(graph_expansion["start_node"]["details"])
                
                with col_gr2:
                    st.markdown("**🔗 Connected Edges (HAS_SEGMENT)**")
                    with st.expander(f"Show {len(graph_expansion.get('connections', []))} Connections", expanded=True):
                        if graph_expansion.get("connections"):
                            for conn in graph_expansion["connections"]:
                                st.json(conn)
                        else:
                            st.info("No connections found")
            else:
                st.error("❌ Graph expansion failed - cannot proceed with synthesis")
                st.stop()
            
            # STEP 3: Context Integration & Generation
            st.markdown("<div class='step-header'>✨ Step 3: Answer Synthesis</div>", unsafe_allow_html=True)
            
            # Build context payload
            context_payload = (
                f"--- MIGRATION CONTEXT EVIDENCE ---\n\n"
                f"**Unstructured Evidence:**\n{matched['text']}\n\n"
                f"**Structured Graph Traversal:**\n"
                f"- Route: {graph_expansion['start_node']['id']}\n"
                f"- Commitment: {graph_expansion['start_node']['details'].get('service_commit', 'N/A')}\n"
            )
            
            if graph_expansion.get("connections"):
                context_payload += f"- Connected Segments: {len(graph_expansion['connections'])}\n"
                for i, conn in enumerate(graph_expansion["connections"][:3], 1):
                    context_payload += (
                        f"  #{i}: {conn.get('target_segment_id', 'N/A')} "
                        f"({conn.get('transport_mode', 'N/A')}) - Status: {conn.get('segment_details', {}).get('status', 'UNKNOWN')}\n"
                    )
            
            with st.expander("📋 Show Assembled Context Window"):
                st.text(context_payload)
            
            st.markdown("**🤖 Synthesized Answer:**")
            
            # Try to get LLM synthesis
            synthesis_failed = False
            
            if is_live:
                # Try Vertex AI first
                try:
                    with st.spinner("⏳ Calling Vertex AI (Gemini 1.5)..."):
                        vertexai.init(project=spanner_project, location="us-central1")
                        
                        prompt = (
                            f"You are a helpful logistics and infrastructure database assistant.\n"
                            f"Answer the user's question using ONLY the provided context.\n"
                            f"Be concise and factual.\n\n"
                            f"Context:\n{context_payload}\n\n"
                            f"Question: {active_query}\n\n"
                            f"Answer:"
                        )
                        
                        try:
                            model = GenerativeModel("gemini-1.5-flash-001")
                            response = model.generate_content(prompt, stream=False)
                            st.success(response.text)
                        except Exception as gemini_flash_err:
                            # Fallback to gemini-pro
                            st.caption("(Using Gemini 1.0 Pro as fallback)")
                            model = GenerativeModel("gemini-1.0-pro-001")
                            response = model.generate_content(prompt, stream=False)
                            st.success(response.text)
                
                except Exception as vertex_err:
                    st.warning(f"⚠️ Vertex AI unavailable: {vertex_err}")
                    synthesis_failed = True
            
            elif gemini_key:
                # Use Gemini API Key from sidebar
                try:
                    with st.spinner("⏳ Calling Gemini API..."):
                        import google.generativeai as genai
                        genai.configure(api_key=gemini_key)
                        model = genai.GenerativeModel('gemini-1.5-flash-001')
                        
                        prompt = (
                            f"You are a helpful logistics and infrastructure database assistant.\n"
                            f"Answer the user's question using ONLY the provided context.\n"
                            f"Be concise and factual.\n\n"
                            f"Context:\n{context_payload}\n\n"
                            f"Question: {active_query}\n\n"
                            f"Answer:"
                        )
                        
                        response = model.generate_content(prompt)
                        st.success(response.text)
                
                except Exception as gemini_err:
                    st.warning(f"⚠️ Gemini API failed: {gemini_err}")
                    synthesis_failed = True
            
            else:
                synthesis_failed = True
            
            # Fallback static answer if LLM synthesis failed
            if synthesis_failed:
                st.info("💡 LLM synthesis unavailable. Using template answer...")
                
                fallback_answer = (
                    f"Based on the combined evidence from unstructured logs and graph traversal:\n\n"
                    f"**Key Finding:** {matched['id']} indicates operational issues in the system.\n\n"
                    f"**Graph Context:** The route {graph_expansion['start_node']['id']} has a service commitment of "
                    f"{graph_expansion['start_node']['details'].get('service_commit', 'N/A')}.\n\n"
                )
                
                if graph_expansion.get("connections"):
                    fallback_answer += (
                        f"**Connected Infrastructure:** This route connects to {len(graph_expansion['connections'])} "
                        f"segments via {', '.join(set(c.get('transport_mode', 'N/A') for c in graph_expansion['connections']))} transport.\n\n"
                    )
                
                fallback_answer += "**Recommendation:** Review the operational logs and graph structure for detailed impact analysis."
                
                st.success(fallback_answer)
        
        except Exception as pipeline_err:
            st.error(f"❌ GraphRAG pipeline failed: {pipeline_err}")
            with st.expander("Show Error Details"):
                st.code(str(pipeline_err))
    
    st.markdown("</div>", unsafe_allow_html=True)


# TAB 4: Governance & Audit - COMPLETE FIXED VERSION
with tab4:
    st.markdown("### Governance & Compliance Audit Logs")
    st.info("📊 **Real-time audit trail:** Tracks all rule evaluations and data validation during ingestion")
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🔍 Dataflow Rule Audit Logs")
    st.caption("Shows results of YAML validation rules evaluated against incoming telemetry data")
    
    col_audit_filter1, col_audit_filter2 = st.columns(2)
    
    with col_audit_filter1:
        audit_status_filter = st.multiselect(
            "Filter by Status:",
            options=["PASS", "FAIL", "WARN"],
            default=["PASS", "FAIL"],
            key="audit_status"
        )
    
    with col_audit_filter2:
        audit_limit = st.slider(
            "Max Records to Show:",
            min_value=10,
            max_value=500,
            value=50,
            step=10,
            key="audit_limit"
        )
    
    if st.button("📥 Query Rule Audit Table", use_container_width=True):
        if is_live:
            try:
                with st.spinner("⏳ Querying live audit logs from Spanner..."):
                    with registry_manager.spanner_db.snapshot() as snapshot:
                        # Build dynamic WHERE clause for status filter
                        status_clause = ", ".join([f"'{s}'" for s in audit_status_filter]) if audit_status_filter else "'PASS', 'FAIL'"
                        
                        query = f"""
                        SELECT 
                            table_name, 
                            row_key, 
                            rule_id, 
                            status, 
                            error_message, 
                            evaluated_at 
                        FROM rule_audit 
                        WHERE status IN ({status_clause})
                        ORDER BY evaluated_at DESC 
                        LIMIT {audit_limit}
                        """
                        
                        results = snapshot.execute_sql(query)
                        rows = list(results)
                        
                        if rows:
                            import pandas as pd
                            df = pd.DataFrame(
                                rows,
                                columns=["Table", "Row Key", "Rule ID", "Status", "Error Message", "Evaluated At"]
                            )
                            
                            # Style the dataframe
                            def color_status(val):
                                if val == "PASS":
                                    return "color: #00C853; font-weight: bold; background-color: rgba(0,200,83,0.1)"
                                elif val == "FAIL":
                                    return "color: #D50000; font-weight: bold; background-color: rgba(213,0,0,0.1)"
                                else:
                                    return "color: #FFA726; font-weight: bold; background-color: rgba(255,167,38,0.1)"
                            
                            styled_df = df.style.map(color_status, subset=["Status"])
                            st.dataframe(styled_df, use_container_width=True)
                            
                            # Show statistics
                            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                            with col_stat1:
                                pass_count = len(df[df["Status"] == "PASS"])
                                st.metric("✅ Passed", pass_count)
                            with col_stat2:
                                fail_count = len(df[df["Status"] == "FAIL"])
                                st.metric("❌ Failed", fail_count)
                            with col_stat3:
                                warn_count = len(df[df["Status"] == "WARN"])
                                st.metric("⚠️ Warnings", warn_count)
                            with col_stat4:
                                total = len(df)
                                pass_rate = (pass_count / total * 100) if total > 0 else 0
                                st.metric("Pass Rate", f"{pass_rate:.1f}%")
                            
                            # Export button
                            csv_export = df.to_csv(index=False)
                            st.download_button(
                                "📥 Export as CSV",
                                csv_export,
                                "audit_logs.csv",
                                "text/csv",
                                use_container_width=True
                            )
                        else:
                            st.warning("⚠️ No audit logs found matching the filter. Run Dataflow ingestion in Tab 1 first.")
            
            except Exception as spanner_err:
                st.error(f"❌ Spanner query failed: {spanner_err}")
                st.info("💡 Tip: Ensure the `rule_audit` table exists. Deploy the ontology schema in Tab 1 first.")
                with st.expander("Show Error Details"):
                    st.code(str(spanner_err))
        
        else:
            # Simulated audit logs for demonstration
            st.success("📌 Showing simulated audit logs (not connected to live Spanner)")
            
            import pandas as pd
            import datetime
            
            # Generate realistic mock data
            mock_data = [
                {
                    "Table": "network_routing",
                    "Row Key": "NR-001",
                    "Rule ID": "rule_routing_valid_ids",
                    "Status": "PASS",
                    "Error Message": "",
                    "Evaluated At": "2026-06-24T10:00:00Z"
                },
                {
                    "Table": "network_routing",
                    "Row Key": "NR-002",
                    "Rule ID": "rule_routing_not_null",
                    "Status": "PASS",
                    "Error Message": "",
                    "Evaluated At": "2026-06-24T10:05:00Z"
                },
                {
                    "Table": "network_routing_segment",
                    "Row Key": "SEG-001",
                    "Rule ID": "rule_segment_origin_neq_dest",
                    "Status": "FAIL",
                    "Error Message": "origin_operation_id == destination_operation_id (OAK == OAK)",
                    "Evaluated At": "2026-06-24T10:10:00Z"
                },
                {
                    "Table": "network_routing_segment",
                    "Row Key": "SEG-002",
                    "Rule ID": "rule_segment_weight_range",
                    "Status": "PASS",
                    "Error Message": "",
                    "Evaluated At": "2026-06-24T10:15:00Z"
                },
                {
                    "Table": "network_routing_segment",
                    "Row Key": "SEG-003",
                    "Rule ID": "rule_segment_transport_mode",
                    "Status": "WARN",
                    "Error Message": "Unusual transport mode: TELEPORT (expected TRUCK/AIR/RAIL)",
                    "Evaluated At": "2026-06-24T10:20:00Z"
                },
                {
                    "Table": "network_routing",
                    "Row Key": "NR-003",
                    "Rule ID": "rule_routing_service_level",
                    "Status": "PASS",
                    "Error Message": "",
                    "Evaluated At": "2026-06-24T10:25:00Z"
                },
            ]
            
            # Apply status filter
            filtered_data = [d for d in mock_data if d["Status"] in audit_status_filter] if audit_status_filter else mock_data
            filtered_data = filtered_data[:audit_limit]
            
            df = pd.DataFrame(filtered_data)
            
            # Style dataframe
            def color_status(val):
                if val == "PASS":
                    return "color: #00C853; font-weight: bold; background-color: rgba(0,200,83,0.1)"
                elif val == "FAIL":
                    return "color: #D50000; font-weight: bold; background-color: rgba(213,0,0,0.1)"
                else:
                    return "color: #FFA726; font-weight: bold; background-color: rgba(255,167,38,0.1)"
            
            styled_df = df.style.map(color_status, subset=["Status"])
            st.dataframe(styled_df, use_container_width=True)
            
            # Statistics
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            with col_stat1:
                pass_count = len(df[df["Status"] == "PASS"])
                st.metric("✅ Passed", pass_count)
            with col_stat2:
                fail_count = len(df[df["Status"] == "FAIL"])
                st.metric("❌ Failed", fail_count)
            with col_stat3:
                warn_count = len(df[df["Status"] == "WARN"])
                st.metric("⚠️ Warnings", warn_count)
            with col_stat4:
                total = len(df)
                pass_rate = (pass_count / total * 100) if total > 0 else 0
                st.metric("Pass Rate", f"{pass_rate:.1f}%")
            
            # Export button
            csv_export = df.to_csv(index=False)
            st.download_button(
                "📥 Export as CSV",
                csv_export,
                "audit_logs_simulated.csv",
                "text/csv",
                use_container_width=True
            )
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # AUDIT INSIGHTS
    st.markdown("---")
    st.subheader("📈 Audit Insights")
    
    col_insight1, col_insight2 = st.columns(2)
    
    with col_insight1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("**🎯 Common Failure Patterns**")
        st.caption(
            "- **Schema Validation:** Missing required fields in object types\n"
            "- **Relationship Logic:** Origin/destination conflicts in routing segments\n"
            "- **Data Quality:** Out-of-range values for weight, duration, etc.\n"
            "- **Referential Integrity:** Foreign key violations between tables"
        )
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col_insight2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("**🔧 Remediation Workflow**")
        st.caption(
            "1. **Review Failures:** Filter by FAIL status to see problematic records\n"
            "2. **Inspect Error Details:** Check error_message column for root cause\n"
            "3. **Fix Data:** Correct violations in source systems\n"
            "4. **Re-ingest:** Re-run Dataflow pipeline with corrected data\n"
            "5. **Verify:** Query audit logs again to confirm pass rate improved"
        )
        st.markdown("</div>", unsafe_allow_html=True)

# TAB 5: Graph Explorer - WORKING VERSION WITH MINIMAL DIAGNOSTICS
with tab5:
    st.markdown("### Interactive Network Graph Visualization")
    
    traversal_mode = st.radio(
        "Traversal mode:",
        ["SQL Traversal (current)"],
        index=0,
        key="graph_traversal_mode",
    )
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Ontology Routing Dependencies")
    
    # LIGHTWEIGHT DIAGNOSTICS - No timeout-prone queries
    with st.expander("🔧 Quick Diagnostics (No Timeout)", expanded=False):
        if st.button("Test Spanner Connection", use_container_width=True):
            try:
                if is_live:
                    with registry_manager.spanner_db.snapshot() as snap:
                        snap.execute_sql("SELECT 1")
                    st.success("✅ Spanner connection working!")
                else:
                    st.info("Running in simulated mode")
            except Exception as e:
                st.error(f"❌ Connection failed: {str(e)[:100]}")
    
    # Initialize variables
    nodes_res = []
    edges_res = []
    
    # Progress bar for better UX while Spanner loads
    _prog_bar = st.progress(0, text="Initialising graph...")

    def _update_progress(frac: float, label: str = ""):
        _prog_bar.progress(min(frac, 0.95), text=label or "Loading...")

    with st.spinner("Querying Spanner & rendering graph..."):
        # Legend
        with st.expander("📊 Legend & Filters", expanded=True):
            cols = st.columns(4)
            with cols[0]:
                st.markdown("**🟡 HUB** - Critical Nodes")
            with cols[1]:
                st.markdown("**🔵 ROUTE** - Network Routing")
            with cols[2]:
                st.markdown("**🟢 STATION/RAMP** - Operational")
            with cols[3]:
                st.markdown("**🟣 EDGE** - Relationships")

        # Build network graph
        net = Network(height="600px", width="100%", directed=True, bgcolor="#0d0f14", font_color="#e0e0e0")
        
        if is_live:
            try:
                _update_progress(0.1, "Loading live Spanner data...")
                
                _update_progress(0.2, "Loading ontology config...")
                config = load_ontology_graph_config(st.session_state.yamls)
                
                _update_progress(0.3, "Fetching graph data from Spanner...")
                # Directly fetch without checking schema (avoids timeout)
                try:
                    nodes_res, edges_res = fetch_graph_data(config, registry_manager.spanner_db)
                except Exception as fetch_err:
                        if "no such table" in str(fetch_err).lower():
                            st.warning("⚠️ Views don't exist in Spanner yet")
                            st.info("Deploy ontology in Tab 1 first")
                        elif "Timeout" in str(fetch_err) or "503" in str(fetch_err):
                            st.warning("⚠️ Spanner query timeout - tables may be empty or don't exist")
                            st.info("Try Dataflow ingestion in Tab 1")
                        raise
                
                _update_progress(0.7, "Processing graph data...")
                
            except Exception as e:
                st.warning(f"⚠️ Live Spanner unavailable: {str(e)[:100]}")
                st.info("Falling back to simulated ontology schema...")
                is_live = False  # Force fallback

        # SIMULATED MODE or FALLBACK
        if not is_live or not nodes_res:
            _update_progress(0.3, "Loading simulated ontology schema...")
            config = load_ontology_graph_config(st.session_state.yamls)
            
            if not is_live:
                st.caption("📌 Simulated mode — showing ontology schema from YAML.")
            elif not nodes_res:
                st.info("🗄️ No graph data found. Run Dataflow bulk load in Tab 1, or switch back to SQL traversal.")
            
            # Build simulated graph from config
            nodes_res = []  # Reset for tracking
            edges_res = []
            
            node_colors = ["#1a73e8", "#F4A623", "#00bfa5", "#9C27B0", "#E91E8C", "#FF5722", "#607D8B"]
            table_nodes_added = set()
            
            _update_progress(0.4, f"Adding {len(config['nodes'])} nodes...")
            for idx, node in enumerate(config["nodes"]):
                try:
                    color = node_colors[idx % len(node_colors)]
                    title = (
                        f"Table: {node['table']}\n"
                        f"PK: {node['key']}\n"
                        f"Props: {', '.join(node['properties'])}"
                    )
                    net.add_node(
                        node["table"],
                        label=node["table"],
                        title=title,
                        color=color,
                        size=20,
                    )
                    table_nodes_added.add(node["table"])
                    nodes_res.append((node["table"], node["table"], json.dumps({"type": "table"})))
                except Exception as node_err:
                    pass

            _update_progress(0.6, f"Adding {len(config['edges'])} relationships...")
            for edge in config["edges"]:
                try:
                    src_table = edge.get("source_table")
                    dst_table = edge.get("target_table")
                    rel = edge.get("table")

                    # Ensure source/target nodes exist
                    if src_table and src_table not in table_nodes_added:
                        net.add_node(src_table, label=src_table, title=f"Table: {src_table}", color="#1a73e8", size=18)
                        table_nodes_added.add(src_table)
                    
                    if dst_table and dst_table not in table_nodes_added:
                        net.add_node(dst_table, label=dst_table, title=f"Table: {dst_table}", color="#F4A623", size=18)
                        table_nodes_added.add(dst_table)

                    # Add relationship node
                    if rel:
                        rel_title = (
                            f"Relationship: {rel}\n"
                            f"{edge.get('source', 'N/A')} → {edge.get('target', 'N/A')}\n"
                            f"Props: {', '.join(edge.get('properties', []))}"
                        )
                        net.add_node(
                            rel,
                            label=rel,
                            title=rel_title,
                            color="#4B5563",
                            size=12,
                            shape="diamond",
                            font={"color": "#a0a0a0", "face": "italic"}
                        )

                        # Add edges (use source_table and target_table, NOT source and target)
                        if src_table and src_table in table_nodes_added:
                            net.add_edge(src_table, rel, color="#539BF5", arrows="to")
                        if dst_table and dst_table in table_nodes_added:
                            net.add_edge(rel, dst_table, color="#539BF5", arrows="to")
                        
                        edges_res.append((rel, rel, src_table, dst_table, json.dumps({})))
                except Exception as edge_err:
                    pass
        
        # Show KPIs (works now because nodes_res is always defined)
        _update_progress(0.8, "Rendering graph...")
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric(label="Total Nodes", value=str(len(nodes_res)))
        with kpi2:
            st.metric(label="Total Edges", value=str(len(edges_res)))
        with kpi3:
            st.metric(label="Backend", value="Live Spanner 🟢" if is_live else "Simulated 🟡")

        # Configure physics for better layout
        net.set_options("""
        {
          "nodes": {
            "font": {
              "size": 14,
              "color": "#FFFFFF"
            },
            "borderWidth": 2,
            "shadow": true
          },
          "edges": {
            "width": 2,
            "shadow": true,
            "smooth": {
              "type": "curvedCW",
              "roundness": 0.2
            }
          },
          "physics": {
            "enabled": true,
            "forceAtlas2Based": {
              "gravitationalConstant": -80,
              "centralGravity": 0.015,
              "springLength": 120,
              "springConstant": 0.06
            },
            "solver": "forceAtlas2Based",
            "stabilization": {
              "iterations": 200
            }
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 100,
            "navigationButtons": true,
            "selectConnectedEdges": true
          }
        }
        """)
        
        _update_progress(0.9, "Finalizing...")
        
        # Save and render
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
                net.save_graph(f.name)
                html_path = f.name
                
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
                
            st.components.v1.html(html_content, height=620, scrolling=False)
            
            # Fallback table if the graph doesn't render
            with st.expander("Show Raw Graph Data (Nodes & Edges)"):
                st.write(f"**Nodes ({len(nodes_res)}):**", nodes_res[:10] if nodes_res else "No nodes")
                st.write(f"**Edges ({len(edges_res)}):**", edges_res[:10] if edges_res else "No edges")
            
            with open(html_path, "rb") as f:
                st.download_button("📥 Export Graph HTML", f, "ontology_graph.html", "text/html")
            os.unlink(html_path)
        
        except Exception as render_err:
            st.error(f"Graph rendering failed: {render_err}")
        
        _update_progress(1.0, "Done!")
        
    st.info("💡 **Impact Analysis:** The graph above highlights how multiple routings depend on the `MEM-HUB` central node. This is a visual representation of the property graph queries that power the GraphRAG serving plane.")
    
    if st.button("🔄 Refresh Graph"):
        st.cache_data.clear()
        st.rerun()
        
    st.markdown("</div>", unsafe_allow_html=True)