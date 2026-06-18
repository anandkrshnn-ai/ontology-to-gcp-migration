variable "project_id" {}
variable "primary_region" {}
variable "environment" {
  description = "dev or prod"
  type        = string
}

# 1. Google Cloud Storage
resource "google_storage_bucket" "data_lake" {
  name                        = "${var.project_id}-data-lake-${var.environment}"
  location                    = var.primary_region
  force_destroy               = var.environment == "dev" ? true : false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
}

# 2. BigQuery Dataset
resource "google_bigquery_dataset" "ontology_dataset" {
  dataset_id                  = "palantir_ontology_${var.environment}"
  friendly_name               = "Palantir Ontology (${var.environment})"
  description                 = "Core semantic layer and structured data"
  location                    = var.primary_region
  delete_contents_on_destroy  = var.environment == "dev" ? true : false
  default_table_expiration_ms = var.environment == "dev" ? 2592000000 : null # 30 days in dev, infinite in prod
}

# 3. Data Catalog Taxonomy
resource "google_data_catalog_taxonomy" "security_markings" {
  display_name           = "Palantir Security Markings (${var.environment})"
  description            = "Taxonomy for migrating Palantir data classification markings"
  region                 = var.primary_region
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]
}

# 4. Pub/Sub Topic
resource "google_pubsub_topic" "magritte_stream" {
  name = "magritte-replacement-stream-${var.environment}"
}

# 5. Cloud Composer (Orchestration)
resource "google_composer_environment" "orchestration" {
  # Only deploy composer in prod or if specifically required to save costs in dev
  count = var.environment == "prod" ? 1 : 0
  name   = "pipeline-orchestrator"
  region = var.primary_region
  config {
    software_config {
      image_version = "composer-2-airflow-2"
    }
  }
}
