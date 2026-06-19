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
variable "secondary_region" {
  type    = string
  default = ""
}
variable "org_id" {}
variable "access_policy_name" {
  type    = string
  default = ""
}

module "landing_zone" {
  source             = "../../modules/landing_zone"
  project_id         = var.project_id
  primary_region     = var.primary_region
  org_id             = var.org_id
  access_policy_name = var.access_policy_name
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
  instance_name    = "ontology-graph-platform-unique"
  database_name    = "ontology_graph_platform_unique"
  processing_units = 100
}
