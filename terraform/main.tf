# Core GCP Infrastructure for Palantir Migration Landing Zone
#
# ENTERPRISE V5 NOTE: 
# This module must be deployed across globally compliant regions (e.g., US/EU) 
# to meet data residency laws. 
# You MUST also enforce Anthos Config Management (Config Sync) and Policy Controller 
# continuously on this infrastructure to block any manual console drift.

provider "google" {
  project = var.project_id
  region  = var.primary_region
}

# 1. Google Cloud Storage (Replacing ADLS/Foundry Files)
resource "google_storage_bucket" "data_lake" {
  name          = "${var.project_id}-data-lake"
  location      = var.primary_region
  force_destroy = false

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

# 2. BigQuery Dataset (Replacing Foundry Ontology)
resource "google_bigquery_dataset" "ontology_dataset" {
  dataset_id                  = "palantir_ontology"
  friendly_name               = "Palantir Ontology Migration"
  description                 = "Core semantic layer and structured data"
  location                    = var.primary_region
  delete_contents_on_destroy  = false
}

# 3. Data Catalog Taxonomy (Replacing Foundry Markings)
resource "google_data_catalog_taxonomy" "security_markings" {
  display_name           = "Palantir Security Markings"
  description            = "Taxonomy for migrating Palantir data classification markings"
  region                 = var.primary_region
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]
}

# 4. Cloud Composer (Replacing Foundry Build)
resource "google_composer_environment" "orchestration" {
  name   = "pipeline-orchestrator"
  region = var.primary_region
  config {
    software_config {
      image_version = "composer-2-airflow-2"
    }
  }
}

# 5. Pub/Sub Topic (Replacing Magritte Streaming)
resource "google_pubsub_topic" "magritte_stream" {
  name = "magritte-replacement-stream"
}

# 6. Observability Dashboard (Executive & Engineering Visibility)
resource "google_monitoring_dashboard" "migration_dashboard" {
  dashboard_json = <<EOF
{
  "displayName": "V7 Migration Framework Observability",
  "gridLayout": {
    "columns": "2",
    "widgets": [
      {
        "title": "DLQ Volumes (Pub/Sub)",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
              }
            }
          }]
        }
      },
      {
        "title": "Ontology Proxy Latency",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "metric.type=\"run.googleapis.com/request_latencies\""
              }
            }
          }]
        }
      },
      {
        "title": "BigQuery Slot Usage",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "metric.type=\"bigquery.googleapis.com/slots/allocated_for_project\""
              }
            }
          }]
        }
      },
      {
        "title": "Semantic Gating Pass/Fail (Logs)",
        "xyChart": {
          "dataSets": [{
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "metric.type=\"logging.googleapis.com/user/semantic_hash_validation\""
              }
            }
          }]
        }
      }
    ]
  }
}
EOF
}

# 7. Lighthouse Pilot: Logistics SLA Monitor
resource "google_pubsub_topic" "logistics_telemetry" {
  name = "logistics-telemetry"
  message_retention_duration = "86600s"
}

resource "google_bigtable_instance" "logistics_sla_instance" {
  name = "logistics-sla-tracker"
  cluster {
    cluster_id   = "logistics-sla-cluster-1"
    num_nodes    = 1
    storage_type = "SSD"
    zone         = "${var.primary_region}-a"
  }
}

resource "google_bigtable_table" "package_sla_states" {
  name          = "package-sla-states"
  instance_name = google_bigtable_instance.logistics_sla_instance.name
}
