import argparse
import logging
import os
import yaml
import csv

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from apache_beam.io.filesystems import FileSystems

from dataflow.ontology_bulk_load.validate_fn import ValidateRow
from dataflow.ontology_bulk_load.batch_writer import SpannerBatchWriter, AuditBatchWriter


def load_ontology_rules(ontology_dir):
    rules_dict = {}
    if not os.path.exists(ontology_dir):
        logging.warning(f"Ontology dir {ontology_dir} not found. Skipping rule loading.")
        return rules_dict

    for filename in os.listdir(ontology_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(ontology_dir, filename), 'r') as f:
                try:
                    data = yaml.safe_load(f)
                    spec = data.get("spec", {})
                    table_name = spec.get("tableName", spec.get("table"))
                    rules = spec.get("rules", [])
                    if table_name and rules:
                        rules_dict[table_name] = rules
                except Exception as e:
                    logging.error(f"Failed to parse {filename}: {e}")
                    
    return rules_dict


def get_csv_headers(file_pattern):
    """Reads the first line of a file (GCS or local) to extract headers."""
    match_result = FileSystems.match([file_pattern])
    if not match_result[0].metadata_list:
        raise ValueError(f"No files found matching {file_pattern}")
        
    first_file = match_result[0].metadata_list[0].path
    with FileSystems.open(first_file) as f:
        first_line = f.readline().decode('utf-8').strip()
        reader = csv.reader([first_line])
        headers = next(reader)
        return headers


class ParseCsvDict(beam.DoFn):
    def __init__(self, headers):
        self.headers = headers

    def process(self, element):
        reader = csv.reader([element])
        for row in reader:
            # Skip the header row itself during processing
            if row == self.headers:
                continue
            if len(row) == len(self.headers):
                yield dict(zip(self.headers, row))


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_dir', required=True, help='Path to input CSV files (local or gs://)')
    parser.add_argument('--ontology_dir', required=True, help='Path to local ontology YAML files')
    parser.add_argument('--project_id', required=True, help='GCP Project ID')
    parser.add_argument('--instance_id', required=True, help='Spanner Instance ID')
    parser.add_argument('--database_id', required=True, help='Spanner Database ID')
    parser.add_argument('--tables', default='operation,network_routing,network_routing_segment,transit_path', help='Comma-separated list of tables to load')

    known_args, pipeline_args = parser.parse_known_args(argv)

    pipeline_options = PipelineOptions(pipeline_args)
    pipeline_options.view_as(SetupOptions).save_main_session = True

    rules_dict = load_ontology_rules(known_args.ontology_dir)
    tables_to_load = [t.strip() for t in known_args.tables.split(',')]

    with beam.Pipeline(options=pipeline_options) as p:
        
        all_audit_logs = []

        for table in tables_to_load:
            input_pattern = f"{known_args.input_dir}/{table}.csv"
            
            try:
                headers = get_csv_headers(input_pattern)
            except Exception as e:
                logging.error(f"Failed to read headers for {table}: {e}")
                continue
                
            table_rules = rules_dict.get(table, [])
            
            lines = p | f"Read_{table}" >> beam.io.ReadFromText(input_pattern)
            
            rows = lines | f"ParseCSV_{table}" >> beam.ParDo(ParseCsvDict(headers))
            
            # Apply rule validation
            validation_results = (
                rows 
                | f"Validate_{table}" >> beam.ParDo(ValidateRow(table, table_rules)).with_outputs('audit_logs', main='valid_rows')
            )
            
            valid_rows = validation_results.valid_rows
            audit_logs = validation_results.audit_logs
            
            all_audit_logs.append(audit_logs)
            
            # Write valid rows to Spanner
            valid_rows | f"WriteSpanner_{table}" >> SpannerBatchWriter(
                known_args.project_id, 
                known_args.instance_id, 
                known_args.database_id, 
                table
            )

        # Flatten and write all audit logs to the rule_audit table
        if all_audit_logs:
            (
                all_audit_logs 
                | "FlattenAuditLogs" >> beam.Flatten()
                | "WriteAuditSpanner" >> AuditBatchWriter(
                    known_args.project_id,
                    known_args.instance_id,
                    known_args.database_id
                )
            )

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()
