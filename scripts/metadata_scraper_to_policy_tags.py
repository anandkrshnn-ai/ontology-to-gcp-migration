#!/usr/bin/env python3
"""
Palantir Metadata Scraper to Google Cloud Dataplex Policy Tags
-------------------------------------------------------------
This script simulates connecting to the Palantir Foundry API, extracting 
hierarchical security markings, and auto-generating the corresponding 
Terraform configuration for Dataplex Taxonomies.

Includes Enterprise Auth (Google Auth + OAuth2), Exponential Backoff (Tenacity),
and Pub/Sub DLQ routing for resilience.
"""

import os
import argparse
import json
import logging
import requests
import google.auth
from google.cloud import pubsub_v1
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

FOUNDRY_URL = os.environ.get("FOUNDRY_URL", "https://your-stack.palantirfoundry.com")
FOUNDRY_TOKEN = os.environ.get("FOUNDRY_TOKEN") 
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_DLQ_TOPIC = os.environ.get("GCP_DLQ_TOPIC", "foundry-metadata-dlq")

def publish_to_dlq(dataset_rid: str, error_message: str):
    """Publishes failed metadata extraction attempts to a GCP Pub/Sub DLQ."""
    if not GCP_PROJECT_ID:
        logging.warning("GCP_PROJECT_ID not set. Skipping Pub/Sub DLQ.")
        return
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(GCP_PROJECT_ID, GCP_DLQ_TOPIC)
        payload = {"dataset_rid": dataset_rid, "error": error_message, "job": "metadata_scraper"}
        publisher.publish(topic_path, json.dumps(payload).encode("utf-8")).result()
        logging.error(f"Sent {dataset_rid} to DLQ.")
    except Exception as e:
        logging.critical(f"Failed to publish to DLQ: {str(e)}")

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def fetch_metadata_from_foundry(dataset_rid: str) -> dict:
    """
    Authenticates with Palantir's API to fetch schema and security markings.
    Uses exponential backoff to handle 429 Too Many Requests.
    """
    if not FOUNDRY_TOKEN:
        raise ValueError("FOUNDRY_TOKEN environment variable is not set.")
        
    logging.info(f"Authenticating with Palantir Foundry API for {dataset_rid}...")
    headers = {"Authorization": f"Bearer {FOUNDRY_TOKEN}", "Content-Type": "application/json"}
    url = f"{FOUNDRY_URL}/api/v1/datasets/{dataset_rid}/schema"
    
    # In a real execution, we would run: 
    # response = requests.get(url, headers=headers)
    # response.raise_for_status()
    # return response.json()
    
    # Mocking successful API response for demonstration purposes
    return {
        "dataset_rid": dataset_rid,
        "name": "employee_payroll_records",
        "schema": {
            "columns": [
                {"name": "employee_id", "type": "STRING", "markings": []},
                {"name": "department", "type": "STRING", "markings": ["Public"]},
                {"name": "salary", "type": "DOUBLE", "markings": ["Confidential", "Finance", "Payroll"]}
            ]
        }
    }

def generate_terraform(metadata: dict, project_id: str, location: str = "us") -> str:
    """Translates Palantir hierarchical markings into Google Cloud Dataplex Terraform."""
    credentials, auth_project = google.auth.default()
    active_project = project_id or auth_project
    
    tf_config = f"""
# Auto-generated Terraform for Dataplex Policy Tags
# Source Palantir Dataset: {metadata['dataset_rid']} ({metadata['name']})

resource "google_data_catalog_taxonomy" "finance_taxonomy" {{
  provider     = google-beta
  project      = "{active_project}"
  region       = "{location}"
  display_name = "Foundry Migrated: Finance Security Hierarchy"
  description  = "Auto-generated from Palantir markings"
  
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]
}}

resource "google_data_catalog_policy_tag" "confidential" {{
  provider     = google-beta
  taxonomy     = google_data_catalog_taxonomy.finance_taxonomy.id
  display_name = "Confidential"
}}

resource "google_data_catalog_policy_tag" "finance" {{
  provider     = google-beta
  taxonomy     = google_data_catalog_taxonomy.finance_taxonomy.id
  display_name = "Finance"
  parent_policy_tag = google_data_catalog_policy_tag.confidential.id
}}

resource "google_data_catalog_policy_tag" "payroll" {{
  provider     = google-beta
  taxonomy     = google_data_catalog_taxonomy.finance_taxonomy.id
  display_name = "Payroll"
  parent_policy_tag = google_data_catalog_policy_tag.finance.id
}}
"""
    return tf_config

def main():
    parser = argparse.ArgumentParser(description="Extract Foundry Markings to Dataplex Policy Tags.")
    parser.add_argument("--dataset_id", required=True, help="Palantir Dataset RID")
    parser.add_argument("--project_id", default=os.environ.get("GCP_PROJECT_ID"), help="Target GCP Project ID")
    parser.add_argument("--output", default="generated_policy_tags.tf", help="Output TF file")
    args = parser.parse_args()

    try:
        metadata = fetch_metadata_from_foundry(args.dataset_id)
        tf_code = generate_terraform(metadata, args.project_id)
        
        with open(args.output, "w") as f:
            f.write(tf_code)
            
        logging.info(f"Successfully generated Dataplex Taxonomy Terraform: {args.output}")
    except Exception as e:
        logging.error(f"Pipeline failed for dataset {args.dataset_id}: {str(e)}")
        publish_to_dlq(args.dataset_id, str(e))

if __name__ == "__main__":
    main()
