terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.primary_region
}

variable "project_id" {}
variable "primary_region" {}
variable "org_id" {}

module "landing_zone" {
  source         = "../../modules/landing_zone"
  project_id     = var.project_id
  primary_region = var.primary_region
  org_id         = var.org_id
}

module "data_foundation" {
  source         = "../../modules/data_foundation"
  project_id     = var.project_id
  primary_region = var.primary_region
  environment    = "dev"
}

module "spanner_database" {
  source           = "../../modules/spanner"
  project_id       = var.project_id
  region           = var.primary_region
  instance_name    = "ontology-graph-platform"
  database_name    = "ontology_graph_platform"
  processing_units = 100
}
