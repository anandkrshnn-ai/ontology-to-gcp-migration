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
                "NR-001": {"origin_operation_id": "OAK-STN", "destination_operation_id": "DAL-STN", "service_commit": "2-DAY", "zulu_day": "2026-06-18"},
                "NR-002": {"origin_operation_id": "OAK-STN", "destination_operation_id": "ORD-STN", "service_commit": "2-DAY", "zulu_day": "2026-06-18"}
            },
            "network_routing_segment": {
                "SEG-001": {"routing_id": "NR-001", "origin_operation_id": "OAK-STN", "destination_operation_id": "OAK-RAMP", "transport_mode": "SURFACE", "weight": 1450, "pieces": 62, "zulu_day": "2026-06-18"},
                "SEG-002": {"routing_id": "NR-001", "origin_operation_id": "OAK-RAMP", "destination_operation_id": "MEM-HUB", "transport_mode": "AIR", "weight": 1450, "pieces": 62, "zulu_day": "2026-06-18"}
            },
            "operation": {
                "OAK-STN": {"operation_type": "STATION", "location_code": "OAK"},
                "MEM-HUB": {"operation_type": "HUB", "location_code": "MEM"}
            }
        }
        self.edges = {
            "has_segments": {
                "EDGE-001": {"source": "NR-001", "target": "SEG-001", "relationship": "HAS_SEGMENT"},
                "EDGE-002": {"source": "NR-001", "target": "SEG-002", "relationship": "HAS_SEGMENT"}
            }
        }

    def execute_graph_expansion(self, start_node_id: str) -> Dict[str, Any]:
        """
        Simulates executing a Spanner Graph query.
        GRAPH air_routing_graph
        MATCH (r:NetworkRouting {routing_id: 'NR-001'})-[e:HAS_SEGMENT]->(s:NetworkRoutingSegment)
        RETURN r.routing_id, r.service_commit, s.segment_id, s.transport_mode, s.weight
        """
        node_details = self.nodes["network_routing"].get(start_node_id)
        if not node_details:
            return {}

        connected_edges = []
        for edge_id, edge_data in self.edges["has_segments"].items():
            if edge_data["source"] == start_node_id:
                target_id = edge_data["target"]
                segment_details = self.nodes["network_routing_segment"].get(target_id)
                connected_edges.append({
                    "edge_id": edge_id,
                    "transport_mode": segment_details["transport_mode"],
                    "weight": segment_details["weight"],
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
    query = "Why are segments originating from OAK experiencing delays, and what transport mode satisfies SEG-002?"
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
    start_node = "NR-001"
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
        f"Route: {graph_expansion['start_node']['id']} (Commitment: {graph_expansion['start_node']['details']['service_commit']})\n"
        f"Segment Link: {graph_expansion['connections'][1]['target_segment_id']} (Transport Mode: {graph_expansion['connections'][1]['transport_mode']}, Weight: {graph_expansion['connections'][1]['weight']} kg, Status: ACTIVE)\n"
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
        f"1. Unstructured logs reveal that the origin station OAK-STN is experiencing severe gate congestion "
        f"due to local power fluctuations, which may cause dispatch delays for segments originating from OAK.\n"
        f"2. Spanner Graph paths reveal that the route {graph_expansion['start_node']['id']} "
        f"has a service commitment of {graph_expansion['start_node']['details']['service_commit']}.\n"
        f"3. Segment {graph_expansion['connections'][1]['target_segment_id']} connects OAK-RAMP to MEM-HUB "
        f"via {graph_expansion['connections'][1]['transport_mode']} transport with weight {graph_expansion['connections'][1]['weight']} kg.\n"
        f"Conclusion: Although dispatch delays might affect segments originating from OAK due to power fluctuations, the downstream connection to MEM-HUB via AIR remains active."
    )
    print("--------------------------------------------------------------------------------")

    print("\n================================================================================")
    print("[*] DEMO SUCCESSFUL: Integrated Ingestion-to-GraphRAG workflow executed.")
    print("================================================================================")


if __name__ == "__main__":
    run_full_rag_demo()
