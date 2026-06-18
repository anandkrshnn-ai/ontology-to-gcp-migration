output "data_lake_bucket_name" {
  description = "The GCS bucket for raw Palantir extractions."
  value       = google_storage_bucket.data_lake.name
}

output "bigquery_ontology_dataset" {
  description = "The BigQuery dataset serving as the new Ontology."
  value       = google_bigquery_dataset.ontology_dataset.dataset_id
}

output "composer_environment_id" {
  description = "The Cloud Composer environment for orchestration."
  value       = google_composer_environment.orchestration.id
}
