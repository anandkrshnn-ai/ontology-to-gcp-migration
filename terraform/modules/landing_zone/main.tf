variable "project_id" {}
variable "primary_region" {}
variable "org_id" {
  description = "GCP Organization ID for VPC-SC"
  type        = string
}
variable "access_policy_name" {
  description = "Numeric name of the org Access Context Manager policy."
  type        = string
  default     = ""
}

locals {
  policy_name = var.access_policy_name != "" ? var.access_policy_name : var.org_id
}

resource "google_compute_network" "shared_vpc" {
  name                    = "vpc-enterprise-palantir-migration"
  auto_create_subnetworks = false
  project                 = var.project_id
  description             = "Central Shared VPC for all migrated Palantir workloads"
}

resource "google_compute_subnetwork" "data_subnet" {
  name                     = "subnet-data-processing"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.primary_region
  network                  = google_compute_network.shared_vpc.id
  private_ip_google_access = true
}

resource "google_compute_subnetwork" "apps_subnet" {
  name                     = "subnet-apps-actions"
  ip_cidr_range            = "10.0.2.0/24"
  region                   = var.primary_region
  network                  = google_compute_network.shared_vpc.id
  private_ip_google_access = true
}

# VPC Service Controls Perimeter
resource "google_access_context_manager_service_perimeter" "palantir_data_perimeter" {
  parent         = "accessPolicies/${local.policy_name}"
  name           = "accessPolicies/${local.policy_name}/servicePerimeters/palantir_migration_perimeter"
  title          = "Palantir Migration Data Perimeter"
  description    = "Prevents data exfiltration from BigQuery, GCS, and Dataproc"
  perimeter_type = "PERIMETER_TYPE_REGULAR"

  status {
    restricted_services = [
      "bigquery.googleapis.com",
      "storage.googleapis.com",
      "pubsub.googleapis.com",
      "dataproc.googleapis.com"
    ]
    vpc_accessible_services {
      enable_restriction = true
      allowed_services   = [
        "bigquery.googleapis.com",
        "storage.googleapis.com"
      ]
    }
  }
}
