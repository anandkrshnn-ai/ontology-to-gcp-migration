# Landing Zone Foundations for Palantir Migration
# This file establishes the core networking and security perimeters 
# that replicate Palantir's "Walled Garden" architecture in GCP.

# ======================================================================
# 1. SHARED VPC (HUB AND SPOKE)
# ======================================================================

# The Shared VPC network hosted in the central networking project
resource "google_compute_network" "shared_vpc" {
  name                    = "vpc-enterprise-palantir-migration"
  auto_create_subnetworks = false
  project                 = var.project_id # In a real setup, this would be var.host_project_id
  description             = "Central Shared VPC for all migrated Palantir workloads"
}

# Subnet for Data Processing (Dataproc, Dataflow)
resource "google_compute_subnetwork" "data_subnet" {
  name                     = "subnet-data-processing"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.primary_region
  network                  = google_compute_network.shared_vpc.id
  private_ip_google_access = true # Mandatory for accessing BigQuery/GCS internally
}

# Subnet for Application APIs (Cloud Run VPC Connectors)
resource "google_compute_subnetwork" "apps_subnet" {
  name                     = "subnet-apps-actions"
  ip_cidr_range            = "10.0.2.0/24"
  region                   = var.primary_region
  network                  = google_compute_network.shared_vpc.id
  private_ip_google_access = true
}

# ======================================================================
# 2. VPC SERVICE CONTROLS (VPC-SC)
# Replicating the Palantir "Air Gap"
# ======================================================================

# Define an Access Policy for the organization
# Note: In production, the access policy is usually managed centrally.
# We create a placeholder data block if it exists, or define it.
data "google_access_context_manager_access_policy" "org_policy" {
  # Replace with actual organization ID in production: "organizations/123456789"
  parent = "organizations/123456789"
}

# The Security Perimeter around the migrated data
resource "google_access_context_manager_service_perimeter" "palantir_data_perimeter" {
  parent         = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy.name}"
  name           = "accessPolicies/${data.google_access_context_manager_access_policy.org_policy.name}/servicePerimeters/palantir_migration_perimeter"
  title          = "Palantir Migration Data Perimeter"
  description    = "Prevents data exfiltration from BigQuery, GCS, and Dataproc"
  perimeter_type = "PERIMETER_TYPE_REGULAR"

  status {
    # Protect the service project hosting the data
    restricted_services = [
      "bigquery.googleapis.com",
      "storage.googleapis.com",
      "pubsub.googleapis.com",
      "dataproc.googleapis.com"
    ]
    
    # Resources (Projects) placed inside this perimeter
    # Example: "projects/123456789"
    # resources = ["projects/${var.project_number}"]
    
    vpc_accessible_services {
      enable_restriction = true
      allowed_services   = [
        "bigquery.googleapis.com",
        "storage.googleapis.com"
      ]
    }
  }
}

# ======================================================================
# 3. PRIVATE SERVICE CONNECT (PSC)
# For B2B Tie-ups and Extensibility (API Gateway / Cloud Run)
# ======================================================================

# Placeholder for PSC Endpoint to expose Workshop Actions securely
# This allows M&A targets or partners to consume APIs without VPC peering.
resource "google_compute_global_address" "psc_api_address" {
  name         = "psc-workshop-actions-api"
  project      = var.project_id
  address_type = "INTERNAL"
  purpose      = "PRIVATE_SERVICE_CONNECT"
  network      = google_compute_network.shared_vpc.id
}
