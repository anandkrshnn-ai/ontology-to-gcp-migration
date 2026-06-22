import apache_beam as beam
from apache_beam.io.gcp.spanner import WriteToSpanner

class SpannerBatchWriter(beam.PTransform):
    """
    Writes a PCollection of valid rows to a specific Spanner table.
    """
    def __init__(self, project_id, instance_id, database_id, table_name):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id
        self.table_name = table_name

    def expand(self, pcoll):
        # WriteToSpanner expects instances of SpannerInsert, SpannerUpdate, or SpannerInsertOrUpdate
        # We need to transform dicts into SpannerInsertOrUpdate mutations
        mutations = pcoll | f"MapToMutations_{self.table_name}" >> beam.Map(self._create_mutation)
        
        return mutations | f"WriteToSpanner_{self.table_name}" >> WriteToSpanner(
            project_id=self.project_id,
            instance_id=self.instance_id,
            database_id=self.database_id
        )
        
    def _create_mutation(self, row):
        from apache_beam.io.gcp.spanner import spanner
        # Filter out empty string values to respect NULL columns if necessary, 
        # or leave them as is.
        clean_row = {k: v for k, v in row.items() if v != ''}
        return spanner.InsertOrUpdate(table=self.table_name, **clean_row)


class AuditBatchWriter(beam.PTransform):
    """
    Writes a PCollection of audit logs to the rule_audit table.
    """
    def __init__(self, project_id, instance_id, database_id):
        self.project_id = project_id
        self.instance_id = instance_id
        self.database_id = database_id

    def expand(self, pcoll):
        mutations = pcoll | "MapAuditMutations" >> beam.Map(self._create_audit_mutation)
        
        return mutations | "WriteAuditToSpanner" >> WriteToSpanner(
            project_id=self.project_id,
            instance_id=self.instance_id,
            database_id=self.database_id
        )
        
    def _create_audit_mutation(self, log_entry):
        from apache_beam.io.gcp.spanner import spanner
        from google.cloud import spanner as gcp_spanner
        
        # evaluated_at is passed as a string, but SpannerInsertOrUpdate might expect a datetime or timestamp
        # In beam's spanner IO, strings formatted as RFC 3339 are usually accepted.
        return spanner.InsertOrUpdate(table="rule_audit", **log_entry)
