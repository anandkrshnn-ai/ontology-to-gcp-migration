resource "google_spanner_instance" "main" {
  name             = var.instance_name
  config           = "regional-${var.region}"
  display_name     = "Ontology Graph Platform"
  processing_units = var.processing_units
  project          = var.project_id
  
  labels = {
    environment = "dev"
    managed_by  = "terraform"
    purpose     = "ontology-graph"
  }
}

resource "google_spanner_database" "graph_db" {
  instance = google_spanner_instance.main.name
  name     = var.database_name
  project  = var.project_id
  
  # Note: The actual DDL schema is applied by the Orchestrator via Python (google-cloud-spanner)
  # or through explicit schema migrations, rather than Terraform passing DDL strings.
  # Terraform manages the foundational Spanner DB existence.
  
  deletion_protection = false # Set to true in prod
}
