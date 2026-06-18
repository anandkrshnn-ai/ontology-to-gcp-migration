import os
import json
import requests
import logging
from google.cloud import storage, pubsub_v1
import google.auth
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configure these environment variables before running
FOUNDRY_URL = os.environ.get("FOUNDRY_URL", "https://your-stack.palantirfoundry.com")
FOUNDRY_TOKEN = os.environ.get("FOUNDRY_TOKEN") # Bearer token for API access
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "foundry-egress-bucket")
GCP_DLQ_TOPIC = os.environ.get("GCP_DLQ_TOPIC", "foundry-egress-dlq")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def publish_to_dlq(dataset_rid: str, file_path: str, error_message: str):
    """
    Publishes failed egress attempts to a GCP Pub/Sub Dead-Letter Queue.
    This fits perfectly within the GCP Free Trial / Free Tier limits.
    """
    if not GCP_PROJECT_ID:
        logging.warning("GCP_PROJECT_ID not set. Skipping Pub/Sub DLQ.")
        return

    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(GCP_PROJECT_ID, GCP_DLQ_TOPIC)
        
        payload = {
            "dataset_rid": dataset_rid,
            "file_path": file_path,
            "error": error_message
        }
        
        data = json.dumps(payload).encode("utf-8")
        future = publisher.publish(topic_path, data)
        future.result() # Wait for publish to complete
        logging.error(f"Sent {file_path} to DLQ topic: {GCP_DLQ_TOPIC}")
    except Exception as e:
        logging.critical(f"Failed to publish to DLQ: {str(e)}")

# Retry on standard HTTP errors (like 429 Too Many Requests or 500+ Server Errors)
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def fetch_from_foundry(url: str, headers: dict, stream: bool = False):
    """
    Makes a request to the Foundry API with Exponential Backoff.
    This prevents the pipeline from collapsing when Palantir throttles (HTTP 429).
    """
    response = requests.get(url, headers=headers, stream=stream)
    response.raise_for_status()
    return response

def export_dataset_to_gcs(dataset_rid: str):
    """
    Exports a Palantir Foundry dataset (raw files) directly to Google Cloud Storage.
    Includes Enterprise Auth, Exponential Backoff, and Pub/Sub DLQ.
    """
    logging.info(f"Starting export for dataset: {dataset_rid}")
    
    # 1. Initialize GCP Storage Client (Using Application Default Credentials)
    credentials, project = google.auth.default()
    storage_client = storage.Client(credentials=credentials, project=GCP_PROJECT_ID or project)
    bucket = storage_client.bucket(GCP_BUCKET_NAME)

    # 2. Get list of files in the Foundry dataset
    headers = {
        "Authorization": f"Bearer {FOUNDRY_TOKEN}",
        "Content-Type": "application/json"
    }
    
    list_files_url = f"{FOUNDRY_URL}/api/v1/datasets/{dataset_rid}/files"
    
    try:
        response = fetch_from_foundry(list_files_url, headers)
        files = response.json().get('data', [])
        logging.info(f"Found {len(files)} files in dataset.")
    except Exception as e:
        logging.error(f"Failed to list files for dataset {dataset_rid}: {str(e)}")
        publish_to_dlq(dataset_rid, "ALL_FILES", str(e))
        return

    # 3. Stream each file to GCS
    for file_info in files:
        file_path = file_info['path']
        download_url = f"{FOUNDRY_URL}/api/v1/datasets/{dataset_rid}/files/{file_path}/content"
        
        logging.info(f"Transferring {file_path} to GCS...")
        
        try:
            # Stream the file from Foundry with exponential backoff
            response = fetch_from_foundry(download_url, headers, stream=True)
            
            # Upload directly to GCS via stream
            gcs_blob = bucket.blob(f"{dataset_rid}/{file_path}")
            gcs_blob.upload_from_file(response.raw)
                
            logging.info(f"Successfully uploaded {file_path} to gs://{GCP_BUCKET_NAME}/{dataset_rid}/{file_path}")
        except Exception as e:
            logging.error(f"Permanent failure transferring {file_path}: {str(e)}")
            publish_to_dlq(dataset_rid, file_path, str(e))

if __name__ == "__main__":
    sample_dataset_rid = "ri.foundry.main.dataset.YOUR_DATASET_RID_HERE"
    
    if not FOUNDRY_TOKEN:
        logging.error("FOUNDRY_TOKEN environment variable is not set.")
        exit(1)
        
    export_dataset_to_gcs(sample_dataset_rid)
    logging.info("Export pipeline run completed.")
