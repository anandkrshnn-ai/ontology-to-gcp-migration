variable "project_id" {
  description = "The GCP Project ID where the migration landing zone will be deployed."
  type        = string
}

variable "primary_region" {
  description = "The primary GCP region (e.g., us-central1) for global compliance."
  type        = string
  default     = "us-central1"
}

variable "secondary_region" {
  description = "The secondary GCP region (e.g., europe-west4) for data residency."
  type        = string
  default     = "europe-west4"
}
