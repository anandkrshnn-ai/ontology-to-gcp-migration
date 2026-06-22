import apache_beam as beam
from google.cloud import spanner

class SpannerWriteDoFn(beam.DoFn):
    def __init__(self, project_id, instance_id, database_id, table_name):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.table_name = table_name

    def setup(self):
        self.client = spanner.Client(project=self.project_id)
        self.instance = self.client.instance(self.instance_id)
        self.database = self.instance.database(self.database_id)

    def process(self, element):
        clean_row = {k: v for k, v in element.items() if v != ''}
        with self.database.batch() as batch:
            batch.insert_or_update(
                table=self.table_name,
                columns=tuple(clean_row.keys()),
                values=[tuple(clean_row.values())]
            )
        yield element

class SpannerBatchWriter(beam.PTransform):
    def __init__(self, project_id, instance_id, database_id, table_name):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.table_name = table_name

    def expand(self, pcoll):
        return pcoll | f"WriteToSpanner_{self.table_name}" >> beam.ParDo(
            SpannerWriteDoFn(self.project_id, self.instance_id, self.database_id, self.table_name)
        )

class AuditWriteDoFn(beam.DoFn):
    def __init__(self, project_id, instance_id, database_id):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id

    def setup(self):
        self.client = spanner.Client(project=self.project_id)
        self.instance = self.client.instance(self.instance_id)
        self.database = self.instance.database(self.database_id)

    def process(self, element):
        with self.database.batch() as batch:
            batch.insert_or_update(
                table="rule_audit",
                columns=tuple(element.keys()),
                values=[tuple(element.values())]
            )
        yield element

class AuditBatchWriter(beam.PTransform):
    def __init__(self, project_id, instance_id, database_id):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id

    def expand(self, pcoll):
        return pcoll | "WriteAuditToSpanner" >> beam.ParDo(
            AuditWriteDoFn(self.project_id, self.instance_id, self.database_id)
        )
