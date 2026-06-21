#!/usr/bin/env python
import os
import sys
import csv
from datetime import datetime
from decimal import Decimal
from google.cloud import spanner

def load_csv(file_path):
    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").date()

def main():
    instance_id = "ontology-demo"
    database_id = "ontology-db"
    
    print(f"Connecting to Spanner Instance: {instance_id}, Database: {database_id}...")
    try:
        client = spanner.Client()
        instance = client.instance(instance_id)
        database = instance.database(database_id)
    except Exception as e:
        print(f"Failed to initialize Spanner Client: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. Load Operation CSV
    print("Loading operation.csv...")
    ops = load_csv("ontology/test_data/operation.csv")
    op_values = [[r["operation_id"], r["operation_type"], r["location_code"]] for r in ops]
    
    # 2. Load NetworkRouting CSV
    print("Loading network_routing.csv...")
    routings = load_csv("ontology/test_data/network_routing.csv")
    routing_values = [
        [r["routing_id"], r["origin_operation_id"], r["destination_operation_id"], r["service_commit"], parse_date(r["zulu_day"])]
        for r in routings
    ]

    # 3. Load NetworkRoutingSegment CSV
    print("Loading network_routing_segment.csv...")
    segments = load_csv("ontology/test_data/network_routing_segment.csv")
    segment_values = [
        [
            r["segment_id"],
            r["routing_id"],
            r["origin_operation_id"],
            r["destination_operation_id"],
            r["transport_mode"],
            Decimal(r["weight"]) if r["weight"] else None,
            int(r["pieces"]) if r["pieces"] else None,
            parse_date(r["zulu_day"])
        ]
        for r in segments
    ]

    # 4. Load TransitPath CSV
    print("Loading transit_path.csv...")
    paths = load_csv("ontology/test_data/transit_path.csv")
    path_values = [
        [r["transit_path_id"], r["segment_id"], int(r["total_transit_minutes"]) if r["total_transit_minutes"] else None]
        for r in paths
    ]

    def write_transaction(transaction):
        # Clear existing data first
        transaction.execute_update("DELETE FROM transit_path WHERE TRUE")
        transaction.execute_update("DELETE FROM network_routing_segment WHERE TRUE")
        transaction.execute_update("DELETE FROM network_routing WHERE TRUE")
        transaction.execute_update("DELETE FROM operation WHERE TRUE")
        
        # Insert operations
        print("Inserting operations...")
        transaction.insert(
            table="operation",
            columns=["operation_id", "operation_type", "location_code"],
            values=op_values
        )
        
        # Insert network routings
        print("Inserting network routings...")
        transaction.insert(
            table="network_routing",
            columns=["routing_id", "origin_operation_id", "destination_operation_id", "service_commit", "zulu_day"],
            values=routing_values
        )
        
        # Insert segments
        print("Inserting segments...")
        transaction.insert(
            table="network_routing_segment",
            columns=["segment_id", "routing_id", "origin_operation_id", "destination_operation_id", "transport_mode", "weight", "pieces", "zulu_day"],
            values=segment_values
        )
        
        # Insert transit paths
        print("Inserting transit paths...")
        transaction.insert(
            table="transit_path",
            columns=["transit_path_id", "segment_id", "total_transit_minutes"],
            values=path_values
        )

    try:
        database.run_in_transaction(write_transaction)
        print("🎉 Successfully loaded all synthetic test data into Google Cloud Spanner!")
    except Exception as e:
        print(f"Transaction failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
