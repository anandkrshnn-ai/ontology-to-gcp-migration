variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The GCP Region for Spanner (e.g. us-central1)"
  type        = string
}

variable "instance_name" {
  description = "The name of the Spanner instance"
  type        = string
}

variable "database_name" {
  description = "The name of the Spanner database"
  type        = string
}

variable "processing_units" {
  description = "Spanner compute capacity (processing units)"
  type        = number
  default     = 100
}
