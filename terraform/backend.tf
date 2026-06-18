# -----------------------------------------------------------------------------
# Enterprise Remote State Backend
# -----------------------------------------------------------------------------
# This file configures the remote backend for Terraform using Google Cloud Storage.
# It ensures that state is stored securely, enabling state locking and preventing
# CI/CD state corruption or drift during concurrent migration runs.
#
# Prerequisite: Create this bucket manually or via a separate bootstrap process.
# gsutil mb -p YOUR_PROJECT_ID -l YOUR_REGION gs://YOUR_PROJECT_ID-tf-state
# -----------------------------------------------------------------------------

terraform {
  backend "gcs" {
    # Replace these placeholders with your actual bootstrap bucket name and prefix
    bucket = "YOUR_PROJECT_ID-tf-state"
    prefix = "terraform/palantir-migration/state"
  }
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}
