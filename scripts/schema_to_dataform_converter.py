#!/usr/bin/env python3
"""
Palantir Schema to Dataform (.sqlx) Converter
---------------------------------------------
This script parses a Palantir dataset schema (JSON) and translates it into
a native Google Cloud Dataform `.sqlx` definition. Crucially, it translates
Palantir's proprietary incremental append flags into Dataform `incremental` 
table types and BigQuery partition keys.

Execution:
    python schema_to_dataform_converter.py --input palantir_schema.json
"""

import argparse
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def mock_read_palantir_schema(file_path: str) -> dict:
    """
    Simulates reading a Palantir dataset schema JSON.
    """
    # Mocking the JSON content that would normally be read from the file
    logging.info(f"Reading Palantir schema from {file_path}")
    return {
        "dataset_name": "flight_telemetry",
        "description": "Raw telemetry ping events from aircraft.",
        "foundry_build_type": "APPEND",  # Palantir incremental flag
        "partitioning": {
            "type": "time",
            "field": "event_timestamp"
        },
        "columns": [
            {"name": "flight_id", "type": "STRING", "description": "Unique flight identifier"},
            {"name": "event_timestamp", "type": "TIMESTAMP", "description": "Time of ping"},
            {"name": "altitude", "type": "INTEGER", "description": "Altitude in feet"}
        ]
    }

def generate_sqlx(schema: dict) -> str:
    """
    Translates the Palantir schema into a Dataform config block and SQL statement.
    """
    dataset_name = schema.get("dataset_name", "unknown_table")
    build_type = schema.get("foundry_build_type", "SNAPSHOT")
    
    # Map Palantir Build Type to Dataform Table Type
    dataform_type = "table"
    if build_type == "APPEND":
        dataform_type = "incremental"
    elif build_type == "VIEW":
        dataform_type = "view"

    # Handle Partitioning
    partition_config = ""
    if "partitioning" in schema:
        part_field = schema["partitioning"]["field"]
        partition_config = f"""
  bigquery: {{
    partitionBy: "DATE({part_field})"
  }},"""

    # Generate Column Descriptions
    columns_config = "\n".join([f'    {col["name"]}: "{col["description"]}",' for col in schema.get("columns", [])])

    sqlx = f"""config {{
  type: "{dataform_type}",
  description: "{schema.get('description', '')}",{partition_config}
  columns: {{
{columns_config}
  }}
}}

/* 
 * Migrated from Palantir Dataset: {dataset_name}
 * Note: Update the source table reference below to match your landing zone.
 */

SELECT
  CAST(flight_id AS STRING) AS flight_id,
  CAST(event_timestamp AS TIMESTAMP) AS event_timestamp,
  CAST(altitude AS INT64) AS altitude
FROM
  ${{ref("landing_{dataset_name}")}}

"""
    
    # Add incremental logic block if applicable
    if dataform_type == "incremental":
        sqlx += f"""
${{when(incremental(), `
  WHERE event_timestamp > (SELECT MAX(event_timestamp) FROM ${{self()}})
`)}}
"""
    return sqlx

def main():
    parser = argparse.ArgumentParser(description="Convert Foundry Schema to Dataform SQLX.")
    parser.add_argument("--input", required=True, help="Path to Palantir schema JSON")
    parser.add_argument("--output_dir", default="definitions", help="Output directory for .sqlx files")
    args = parser.parse_args()

    # 1. Read
    schema = mock_read_palantir_schema(args.input)
    
    # 2. Transform
    sqlx_content = generate_sqlx(schema)
    
    # 3. Load
    os.makedirs(args.output_dir, exist_ok=True)
    output_file = os.path.join(args.output_dir, f"{schema['dataset_name']}.sqlx")
    
    with open(output_file, "w") as f:
        f.write(sqlx_content)
        
    logging.info(f"Successfully generated Dataform script: {output_file}")
    logging.info(f"Handled Palantir incremental logic: {schema.get('foundry_build_type') == 'APPEND'}")

if __name__ == "__main__":
    main()
