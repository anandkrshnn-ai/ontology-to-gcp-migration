import argparse
import json
import logging
import hashlib
from datetime import datetime

try:
    import apache_beam as beam
    from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
    from apache_beam.transforms.window import FixedWindows
except ImportError:
    beam = None
    logging.warning("apache-beam not installed. This script requires apache-beam.")

def generate_row_key(package_id: str, timestamp_iso: str) -> str:
    """
    Generates a salted row key for Bigtable to prevent hotspotting.
    Format: <hash(package_id)>#<package_id>#<timestamp>
    """
    # 1. Hash the package ID to create a salt (using first 4 chars of MD5)
    salt = hashlib.md5(package_id.encode('utf-8')).hexdigest()[:4]
    
    # 2. Extract a cleaner timestamp for the key (optional, depending on query patterns)
    # Using the raw ISO string for simplicity here.
    
    return f"{salt}#{package_id}#{timestamp_iso}"

class ProcessTelemetry(beam.DoFn):
    """
    Parses the telemetry JSON and prepares it for Bigtable insertion.
    Includes SLA logic detection.
    """
    def process(self, element):
        try:
            # If reading from Pub/Sub, element might be bytes
            if isinstance(element, bytes):
                element = element.decode('utf-8')
                
            data = json.loads(element)
            package_id = data.get("package_id")
            timestamp = data.get("timestamp")
            status = data.get("status")
            
            if not package_id or not timestamp:
                return
            
            # SLA Logic: Flag if delayed
            sla_breach = "TRUE" if status == "DELAYED" else "FALSE"
            
            # Bigtable Row Key
            row_key = generate_row_key(package_id, timestamp)
            
            # In a real pipeline, we would yield a DirectRow object for Bigtable:
            # from google.cloud.bigtable import row
            # direct_row = row.DirectRow(row_key_encoded)
            # direct_row.set_cell('telemetry', 'status', status)
            # direct_row.set_cell('telemetry', 'sla_breach', sla_breach)
            # yield direct_row
            
            # For demonstration, we yield a dictionary
            yield {
                "row_key": row_key,
                "package_id": package_id,
                "status": status,
                "sla_breach": sla_breach,
                "timestamp": timestamp,
                "delay_reason": data.get("delay_reason", "")
            }
            
        except Exception as e:
            logging.error(f"Failed to process element: {e}")

def run(project_id: str, topic_id: str, local: bool = False):
    if not beam:
        logging.error("Apache Beam is not available. Please install it: pip install apache-beam[gcp]")
        return
        
    options = PipelineOptions()
    if not local:
        options.view_as(StandardOptions).streaming = True

    with beam.Pipeline(options=options) as p:
        
        if local:
            # Mock data source for local testing
            events = p | "Generate Mock Events" >> beam.Create([
                '{"package_id": "PKG-1001", "timestamp": "2023-10-27T10:00:00Z", "status": "IN_TRANSIT"}',
                '{"package_id": "PKG-1002", "timestamp": "2023-10-27T10:05:00Z", "status": "DELAYED", "delay_reason": "WEATHER"}'
            ])
        else:
            # Real Pub/Sub Source
            subscription_path = f"projects/{project_id}/subscriptions/{topic_id}-sub"
            events = p | "Read from Pub/Sub" >> beam.io.ReadFromPubSub(subscription=subscription_path)
            
        processed_events = (
            events
            | "Parse & Apply SLA Logic" >> beam.ParDo(ProcessTelemetry())
        )
        
        if local:
            # Print to console for local testing
            processed_events | "Print Output" >> beam.Map(lambda x: logging.info(f"Writing to Bigtable Mock: {x}"))
        else:
            # In a real execution, we write to Bigtable:
            # processed_events | "Write to Bigtable" >> WriteToBigTable(project_id, instance_id, table_id)
            processed_events | "Log Processed" >> beam.Map(lambda x: logging.info(f"Processed: {x['row_key']}"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_id", default="mock-project-id")
    parser.add_argument("--topic_id", default="logistics-telemetry")
    parser.add_argument("--local", action="store_true", help="Run with mock data locally")
    
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.INFO)
    run(args.project_id, args.topic_id, args.local)
