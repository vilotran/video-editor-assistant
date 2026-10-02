output "cloud_run_service_url" {
  description = "Public URL of deployed Cloud Run Video Editor Assistant service"
  value       = google_cloud_run_v2_service.agent_service.uri
}

output "artifact_registry_repo" {
  description = "Artifact Registry Docker repository URI"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.name}"
}

output "service_account_email" {
  description = "Service account email utilized by the Cloud Run instance"
  value       = google_service_account.agent_sa.email
}

output "secret_manager_secret_id" {
  description = "Secret Manager secret ID for API keys"
  value       = google_secret_manager_secret.api_key_secret.secret_id
}
