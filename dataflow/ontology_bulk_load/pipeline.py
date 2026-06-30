

import logging

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("apache_beam").setLevel(logging.WARNING)

import argparse
import yaml
import csv
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, SetupOptions
from apache_beam.io.filesystems import FileSystems

from dataflow.ontology_bulk_load.validate_fn import ValidateRow
from dataflow.ontology_bulk_load.batch_writer import (
    SpannerBatchWriter,
    AuditBatchWriter,
)


# ✅ ✅ MAPPING LAYER (CRITICAL FIX)
TABLE_MAP = {
    "operation": "location",
    "network_routing": "route",
    "network_routing_segment": "waypoint",
    "transit_path": "transit_connection"
}


# ✅ ✅ Ontology loader (GCS safe)
def load_ontology_rules(ontology_dir, table_filter=None):
    print(f"🔥 Loading ontology from: {ontology_dir}")

    rules_dict = {}
    files = []

    for ext in ["*.yaml", "*.yml"]:
        pattern = f"{ontology_dir}/{ext}"
        print(f"🔍 Matching: {pattern}")

        matches = FileSystems.match([pattern])
        for m in matches:
            for metadata in m.metadata_list:
                print(f"✅ Found file: {metadata.path}")
                files.append(metadata.path)

    if not files:
        print(f"❌ No ontology files found in {ontology_dir}")

    for file_path in files:
        try:
            with FileSystems.open(file_path) as f:
                content = f.read()
                data = yaml.safe_load(content.decode("utf-8", errors="ignore"))
        except Exception as e:
            logging.error(f"Failed to read {file_path}: {e}")
            continue

        spec = data.get("spec", {})
        table_name = spec.get("tableName", spec.get("table"))
        rules = spec.get("rules", [])

        print(f"📊 Parsed: table={table_name}, rules={len(rules)}")

        if table_filter and table_name not in table_filter:
            continue

        if table_name and rules:
            rules_dict[table_name] = rules

    print(f"🚀 Rules loaded: {list(rules_dict.keys())}")

    return rules_dict


# ✅ ✅ Safe CSV header reader
def get_csv_headers(file_pattern):
    match_result = FileSystems.match([file_pattern])

    if not match_result or not match_result[0].metadata_list:
        raise ValueError(f"No files found: {file_pattern}")

    first_file = match_result[0].metadata_list[0].path

    with FileSystems.open(first_file) as f:
        first_line = f.readline().decode("utf-8", errors="ignore").strip()
        return next(csv.reader([first_line]))


# ✅ ✅ Safe CSV parsing
class ParseCsvDict(beam.DoFn):
    def __init__(self, headers):
        self.headers = headers

    def process(self, element):
        try:
            row = next(csv.reader([element]))

            if row != self.headers and len(row) == len(self.headers):
                yield dict(zip(self.headers, row))

        except Exception as e:
            logging.error(f"CSV parse error: {e}")


def run(argv=None):

    print("🔥🔥 NEW PIPELINE VERSION EXECUTED 🔥🔥")

    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--ontology_dir", required=True)
    parser.add_argument("--project_id", required=True)
    parser.add_argument("--instance_id", required=True)
    parser.add_argument("--database_id", required=True)
    parser.add_argument(
        "--tables",
        default="operation,network_routing,network_routing_segment,transit_path"
    )

    known_args, pipeline_args = parser.parse_known_args(argv)

    options = PipelineOptions(pipeline_args, save_main_session=True)

    # ✅ Explicitly set project (fixes your error)
    options.view_as(beam.options.pipeline_options.GoogleCloudOptions).project = known_args.project_id

    tables = [t.strip() for t in known_args.tables.split(",")]

    # ✅ Load ontology rules
    rules_dict = load_ontology_rules(
        known_args.ontology_dir,
        set(TABLE_MAP.values())
    )

    with beam.Pipeline(options=options) as p:

        audit_streams = []

        for table in tables:

            print(f"📥 Processing table: {table}")

            input_pattern = f"{known_args.input_dir.rstrip('/')}/{table}.csv"

            try:
                headers = get_csv_headers(input_pattern)
            except Exception as e:
                logging.error(f"Header read failed for {table}: {e}")
                continue

            lines = p | f"Read_{table}" >> beam.io.ReadFromText(input_pattern)

            rows = lines | f"Parse_{table}" >> beam.ParDo(ParseCsvDict(headers))

            # ✅ ✅ APPLY MAPPING FOR RULES
            ontology_table = TABLE_MAP.get(table, table)
            rules = rules_dict.get(ontology_table, [])

            print(f"🔗 Mapping: {table} → {ontology_table}")
            print(f"📊 Rules count: {len(rules)}")

            validated = (
                rows
                | f"Validate_{table}"
                >> beam.ParDo(
                    ValidateRow(table, rules)
                ).with_outputs("audit_logs", main="valid")
            )

            # ✅ ✅ APPLY MAPPING FOR SPANNER WRITE
            spanner_table = TABLE_MAP.get(table, table)

            validated.valid | f"Write_{table}" >> beam.ParDo(
		SpannerBatchWriter(
                known_args.project_id,
                known_args.instance_id,
                known_args.database_id,
                spanner_table
		)
            )

            audit_streams.append(validated.audit_logs)

        if audit_streams:
            (
                audit_streams
                | "FlattenAudit" >> beam.Flatten()
                | "WriteAudit" >> beam.ParDo(
		AuditBatchWriter(
                    known_args.project_id,
                    known_args.instance_id,
                    known_args.database_id
			)
                )
            )


if __name__ == "__main__":
    run()
