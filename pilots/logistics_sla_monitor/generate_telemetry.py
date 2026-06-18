import os
import json
import time
import random
import argparse
from datetime import datetime
import logging

try:
    from google.cloud import pubsub_v1
except ImportError:
    pubsub_v1 = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_telemetry_event():
    """Generates a mock logistics telemetry event."""
    # We use a constrained set of package IDs to simulate updates to the same packages
    package_id = f"PKG-{random.randint(1000, 1050)}"
    
    statuses = ["IN_TRANSIT", "AT_HUB", "DELAYED", "DELIVERED"]
    # Weight the statuses to make IN_TRANSIT and AT_HUB more common
    status = random.choices(statuses, weights=[0.5, 0.3, 0.1, 0.1])[0]
    
    # If delayed, assign a reason
    reason = None
    if status == "DELAYED":
        reason = random.choice(["WEATHER", "CUSTOMS", "VEHICLE_BREAKDOWN", "TRAFFIC"])
        
    return {
        "package_id": package_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": status,
        "location": f"HUB-{random.randint(1, 5)}",
        "delay_reason": reason
    }

def run_generator(project_id: str, topic_id: str, local: bool = False):
    logging.info(f"Starting Logistics Telemetry Generator (Local={local})")
    
    publisher = None
    topic_path = None
    if not local and pubsub_v1:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_id)
        logging.info(f"Connected to Pub/Sub Topic: {topic_path}")
    
    try:
        while True:
            event = generate_telemetry_event()
            event_json = json.dumps(event)
            
            if local:
                # Just print to stdout
                logging.info(f"Local Event: {event_json}")
            else:
                if publisher and topic_path:
                    publisher.publish(topic_path, event_json.encode("utf-8"))
                    logging.info(f"Published: {event['package_id']} -> {event['status']}")
                else:
                    logging.warning("Pub/Sub not configured. Running in dry-run mode.")
                    logging.info(f"Dry-Run Event: {event_json}")
            
            # Sleep to simulate throughput (adjust as needed)
            time.sleep(random.uniform(0.1, 0.5))
            
    except KeyboardInterrupt:
        logging.info("Generator stopped by user.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_id", default=os.environ.get("GCP_PROJECT_ID", "mock-project-id"))
    parser.add_argument("--topic_id", default="logistics-telemetry")
    parser.add_argument("--local", action="store_true", help="Run locally without Pub/Sub")
    
    args = parser.parse_args()
    run_generator(args.project_id, args.topic_id, args.local)
