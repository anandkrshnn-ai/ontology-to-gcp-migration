import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import numpy as np
from typing import Dict, Any, List
from scripts.orchestrator import SpannerRegistryManager, Orchestrator
from scripts.graph_compiler import GraphCompiler

class MockVectorStore:
    """Simulates a vector store (e.g., Vertex AI Vector Search) for document chunks."""
    def __init__(self):
        self.documents = [
            {
                "id": "doc_chunk_1",
                "text": "Incident Report: Chicago Hub (node_id: network_routing) is experiencing severe gate congestion today due to local power fluctuations. Operational capacity is temporarily reduced by 40%.",
                "entities": {"node_id": "network_routing"}
            },
            {
                "id": "doc_chunk_2",
                "text": "Maintenance Log: The transit path between Chicago Hub and New York Segment (segment_id: network_routing_segment) is running smoothly. Average duration remains constant.",
                "entities": {"segment_id": "network_routing_segment"}
            },
            {
                "id": "doc_chunk_3",
                "text": "Telemetry alert: High wind warnings are currently active along the transit corridor between Chicago and Dallas segments.",
                "entities": {"segment_id": "network_routing_segment"}
            }
        ]
        # Generate simple mock embeddings for each document
        self.embeddings = {doc["id"]: np.random.rand(128) for doc in self.documents}

    def semantic_search(self, query: str, top_k: int = 1) -> List[Dict[str, Any]]:
        """Simulates finding relevant document chunks via cosine similarity."""
        query_vector = np.random.rand(128)
        scores = []
        for doc_id, doc_vector in self.embeddings.items():
            # Mock cosine similarity score
            score = np.dot(query_vector, doc_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(doc_vector))
            scores.append((doc_id, score))
        
        # Sort by similarity score
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


class SpannerGraphSimulator:
    """Simulates the serving plane executing Spanner Graph query expansions."""
    def __init__(self):
        # Seeded relational database records matching ontology yaml definitions
        self.nodes = {
            "network_routing": {
                "CHI-NODE-01": {"name": "Chicago Logistics Hub", "location_type": "Air Hub", "latitude": 41.8781, "longitude": -87.6298, "capacity": 1200},
                "NYC-NODE-02": {"name": "New York Distribution Center", "location_type": "Land Hub", "latitude": 40.7128, "longitude": -74.0060, "capacity": 2500}
            },
            "network_routing_segment": {
                "SEG-CHI-NYC-01": {"origin_node_id": "CHI-NODE-01", "destination_node_id": "NYC-NODE-02", "distance_km": 1150.0, "status": "ACTIVE"}
            },
            "operation": {
                "OP-CHI-01": {"node_id": "CHI-NODE-01", "operation_type": "De-palletization", "operating_hours": "06:00-22:00", "active": True}
            }
        }
        self.edges = {
            "transit_path": {
                "PATH-01": {"source": "CHI-NODE-01", "target": "SEG-CHI-NYC-01", "transit_mode": "Freight Train", "avg_duration_hours": 14.5}
            }
        }

    def execute_graph_expansion(self, start_node_id: str) -> Dict[str, Any]:
        """
        Simulates executing a Spanner Graph query.
        GRAPH LogisticsRoutingGraph
        MATCH (n:NetworkRouting {node_id: 'CHI-NODE-01'})-[e:TRANSIT_PATH]->(s:RoutingSegment)
        RETURN n.name, s.segment_id, e.transit_mode
        """
        node_details = self.nodes["network_routing"].get(start_node_id)
        if not node_details:
            return {}

        connected_edges = []
        for edge_id, edge_data in self.edges["transit_path"].items():
            if edge_data["source"] == start_node_id:
                target_id = edge_data["target"]
                segment_details = self.nodes["network_routing_segment"].get(target_id)
                connected_edges.append({
                    "edge_id": edge_id,
                    "transit_mode": edge_data["transit_mode"],
                    "avg_duration_hours": edge_data["avg_duration_hours"],
                    "target_segment_id": target_id,
                    "segment_details": segment_details
                })
        
        # Build expanded graph path payload
        return {
            "start_node": {
                "id": start_node_id,
                "details": node_details
            },
            "connections": connected_edges
        }


def run_full_rag_demo():
    print("================================================================================")
    print("MIGRATION PLAYBOOK: FULL ONTOLOGY-TO-GRAPHRAG SERVING PLANE DEMO")
    print("================================================================================")

    # --- Step 1: Ingest & Validate Ontology ---
    print("\n[STEP 1] Structural Validation of Raw Ontology Contracts")
    ontology_dir = "ontology"
    registry = SpannerRegistryManager(mock=True)
    orchestrator = Orchestrator(registry)
    
    try:
        validated_files = orchestrator.validate_source_dir(ontology_dir)
        print(f"[*] Validation complete. Successfully loaded {len(validated_files)} schema files.")
    except Exception as e:
        print(f"[!] Structural Validation Failed: {e}")
        return

    # --- Step 2: Compile Graph Surface Plan ---
    print("\n[STEP 2] Compiling Property Graph DDL via GraphCompiler")
    plan_info = orchestrator.run_plan(ontology_dir)
    yamls = [data for _, data in validated_files]
    graph_yaml = next((y for y in yamls if y.get("kind") == "PropertyGraph"), None)
    
    compiler = GraphCompiler(compatibility_status=plan_info["status"], schema_diffs=plan_info["schema_diffs"])
    compilation_plan = compiler.compile_plan(yamls, graph_yaml)
    
    print(f"[*] Compiler Output: Compatibility = {compilation_plan['compatibility']}")
    print(f"[*] Generated DDL Statements: {len(compilation_plan['actions'])} actions planned.")
    print("Snippet of compiled Property Graph definition:")
    print("-" * 60)
    print(compilation_plan["actions"][-1][:350] + "\n  ...")
    print("-" * 60)

    # --- Step 3: Ingestion Plane Simulation ---
    print("\n[STEP 3] Ingesting Unstructured Telemetry & Vector Embedding Generation")
    vector_store = MockVectorStore()
    print(f"[*] Vector Store Initialized with {len(vector_store.documents)} indexed logs.")

    # --- Step 4: Serving Plane: GraphRAG Query Execution ---
    print("\n[STEP 4] GraphRAG Execution: Retrieval Augmented Graph Expansion")
    query = "Why is operational capacity degraded at the Chicago Hub, and what is the transit mode to its segments?"
    print(f"User Query: \"{query}\"")
    
    # 4a. Semantic Search over chunks
    print("\n  Sub-Step 4a: Executing semantic search over document corpus...")
    search_results = vector_store.semantic_search(query, top_k=1)
    matched_doc = search_results[0]["document"]
    score = search_results[0]["score"]
    print(f"  Matched Document Chunk (Score: {score:.4f}):")
    print(f"  > \"{matched_doc['text']}\"")

    # 4b. Graph Context Expansion via Spanner Graph
    print("\n  Sub-Step 4b: Resolving Node entity and traversing Spanner Graph...")
    # Map semantically resolved context to Chicago Hub node: CHI-NODE-01
    start_node = "CHI-NODE-01"
    graph_db = SpannerGraphSimulator()
    graph_expansion = graph_db.execute_graph_expansion(start_node)
    
    print("  Retrieved Spanner Graph Path:")
    print(json.dumps(graph_expansion, indent=2))

    # --- Step 5: Answer Generation ---
    print("\n[STEP 5] Assembling Unified Evidence Context & LLM Response Generation")
    
    # Assembly logic (evidence formatting)
    context_window = (
        f"--- UNSTRUCTURED DOCUMENT EVIDENCE ---\n"
        f"{matched_doc['text']}\n\n"
        f"--- STRUCTURED GRAPH RETRIEVED RELATIONSHIPS ---\n"
        f"Hub Node: {graph_expansion['start_node']['details']['name']} (Capacity: {graph_expansion['start_node']['details']['capacity']})\n"
        f"Segment Link: {graph_expansion['connections'][0]['target_segment_id']} (Transit Mode: {graph_expansion['connections'][0]['transit_mode']}, Average Duration: {graph_expansion['connections'][0]['avg_duration_hours']} hours, Status: {graph_expansion['connections'][0]['segment_details']['status']})\n"
    )

    print("Evidence payload assembled for LLM Context:")
    print("=" * 60)
    print(context_window)
    print("=" * 60)

    # Simulated LLM output
    print("Generated Answer:")
    print("--------------------------------------------------------------------------------")
    print(
        f"Based on the combined evidence:\n"
        f"1. Unstructured logs reveal that the {graph_expansion['start_node']['details']['name']} (CHI-NODE-01) "
        f"is experiencing power fluctuations causing a 40% operational capacity reduction (temporary capacity reduced to 720 units).\n"
        f"2. Spanner Graph paths reveal that this hub connects to segment {graph_expansion['connections'][0]['target_segment_id']} "
        f"via {graph_expansion['connections'][0]['transit_mode']} with an average duration of {graph_expansion['connections'][0]['avg_duration_hours']} hours.\n"
        f"3. The connection is currently {graph_expansion['connections'][0]['segment_details']['status']}.\n"
        f"Conclusion: Logistics delays should be expected at Chicago Hub, but downstream transit connections remain healthy."
    )
    print("--------------------------------------------------------------------------------")

    print("\n================================================================================")
    print("[*] DEMO SUCCESSFUL: Integrated Ingestion-to-GraphRAG workflow executed.")
    print("================================================================================")


if __name__ == "__main__":
    run_full_rag_demo()
