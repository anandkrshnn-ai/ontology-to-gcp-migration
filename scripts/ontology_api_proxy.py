#!/usr/bin/env python3
"""
Palantir Ontology API Proxy (GCP Middleware)
--------------------------------------------
This is a lightweight FastAPI server that acts as a reverse proxy for custom 
frontend applications (React, Angular) that were built on top of the Palantir 
Ontology API.

Instead of hitting Foundry, frontends hit this proxy. This proxy intercepts 
the object traversal requests (e.g., get Flight for Package) and translates 
them into optimized BigQuery SQL, specifically leveraging pre-built materialized 
views to prevent massive BigQuery scan costs on nested JSON/STRUCTs.

Execution:
    pip install fastapi uvicorn google-cloud-bigquery
    uvicorn ontology_api_proxy:app --host 0.0.0.0 --port 8080
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from pydantic import BaseModel
import logging

# In production, initialize the BigQuery client
# from google.cloud import bigquery
# client = bigquery.Client()

app = FastAPI(title="Ontology API Proxy")
logging.basicConfig(level=logging.INFO)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_token(token: str = Depends(oauth2_scheme)):
    """
    Mock token verification. In production, validate the token against 
    Google Identity or your enterprise IdP (e.g., Okta, Ping).
    """
    if not token or token != "valid-enterprise-token":
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return token

class ObjectRequest(BaseModel):
    object_type: str
    primary_key: str

class TraversalRequest(BaseModel):
    source_object_type: str
    source_primary_key: str
    link_type_id: str

class ActionRequest(BaseModel):
    action_type: str
    object_type: str
    primary_key: str
    payload: dict


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Ontology API Proxy"}

@app.post("/api/v1/ontology/objects")
def get_object(request: ObjectRequest, token: str = Depends(verify_token)):
    """
    Simulates fetching a single Palantir Object (e.g., a Package).
    Translates to a simple primary key lookup in BigQuery.
    """
    logging.info(f"Intercepted Ontology Request: Get {request.object_type} [{request.primary_key}]")
    
    # 1. Map Palantir Object to BigQuery Table
    bq_table = f"`prj-data-gold.ontology.{request.object_type.lower()}`"
    
    # 2. Generate SQL
    sql = f"""
        SELECT * FROM {bq_table} 
        WHERE id = '{request.primary_key}' 
        LIMIT 1
    """
    logging.info(f"Executing BigQuery: {sql.strip()}")
    
    # 3. Execute and format (Mocked)
    return {
        "id": request.primary_key,
        "properties": {
            "status": "DELIVERED",
            "weight_kg": 14.5
        }
    }

@app.post("/api/v1/ontology/traverse")
def traverse_links(request: TraversalRequest, token: str = Depends(verify_token)):
    """
    Simulates a Palantir Link Traversal (e.g., Get Flights for Package).
    CRITICAL: To avoid BigQuery UNNEST() cost explosions, this routes 
    traversals to pre-computed Materialized Views.
    """
    logging.info(f"Intercepted Traversal: {request.source_object_type} [{request.source_primary_key}] -> {request.link_type_id}")
    
    # Map traversal to a Materialized View to save BigQuery costs
    mv_mapping = {
        # Single-hop traversals
        ("Package", "Package_to_Flight"): "`prj-data-gold.ontology.mv_package_flight_links`",
        ("Flight", "Flight_to_Customer"): "`prj-data-gold.ontology.mv_flight_customer_links`",
        
        # Multi-hop traversals (Pre-joined to prevent runtime BigQuery explosion)
        ("Package", "Package_to_Flight_to_Customer"): "`prj-data-gold.ontology.mv_package_flight_customer_multihop`"
    }
    
    lookup_key = (request.source_object_type, request.link_type_id)
    
    if lookup_key not in mv_mapping:
        raise HTTPException(status_code=400, detail=f"Traversal '{request.link_type_id}' from '{request.source_object_type}' not supported or Materialized View missing.")
        
    bq_mv = mv_mapping[lookup_key]
    
    # Generate SQL against the Materialized View
    sql = f"""
        SELECT * 
        FROM {bq_mv} 
        WHERE source_id = '{request.source_primary_key}'
    """
    logging.info(f"Executing Optimized BigQuery Traversal: {sql.strip()}")
    
    # Execute and format (Mocked)
    return {
        "links": [
            {"target_object_type": "Flight", "properties": {"flight_id": "FL-991", "status": "IN_AIR"}}
        ]
    }

@app.post("/api/v1/ontology/actions")
def execute_action(request: ActionRequest, token: str = Depends(verify_token)):
    """
    Simulates a Palantir Action (Write-Back) using CQRS.
    CRITICAL: BigQuery is OLAP and terrible at high-frequency row mutations.
    This routes the write payload directly to a transactional database 
    (Cloud SQL / Spanner) which will eventually sync back to BigQuery via Datastream.
    """
    logging.info(f"Intercepted Action: {request.action_type} on {request.object_type} [{request.primary_key}]")
    
    # Map action to transactional database
    db_table = f"trx_{request.object_type.lower()}_mutations"
    
    # Generate SQL against Cloud SQL / Spanner (Mocked)
    sql = f"""
        UPDATE {db_table} 
        SET properties = '{request.payload}' 
        WHERE id = '{request.primary_key}'
    """
    logging.info(f"Executing CQRS Write to Cloud SQL/Spanner: {sql.strip()}")
    
    # Execute and format (Mocked)
    return {
        "status": "SUCCESS",
        "message": f"Action '{request.action_type}' applied to Cloud SQL successfully. Datastream sync pending.",
        "updated_object": request.primary_key
    }

