terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.25"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# -----------------------------------------------------------------------------
# Service Account for Cloud Run Agent
# -----------------------------------------------------------------------------

resource "google_service_account" "agent_sa" {
  account_id   = "${var.service_name}-sa"
  display_name = "Service Account for ${var.service_name}"
}

# IAM Role Bindings for Service Account
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

# -----------------------------------------------------------------------------
# Artifact Registry Repository
# -----------------------------------------------------------------------------

resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.service_name
  description   = "Docker repository for AI Video Editor Assistant"
  format        = "DOCKER"
}

# -----------------------------------------------------------------------------
# Google Cloud Secret Manager Secret
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "api_key_secret" {
  secret_id = "${var.service_name}-api-key"
  replication {
    auto {}
  }
}

# -----------------------------------------------------------------------------
# Cloud Run Service (v2)
# -----------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "agent_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.agent_sa.email

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "2000m"
          memory = "2Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "DIRECTOR_MODEL"
        value = var.director_model
      }
      env {
        name  = "SUBAGENT_MODEL"
        value = var.subagent_model
      }
      env {
        name  = "SQLITE_DB_PATH"
        value = "/tmp/editor_state.db"
      }
      env {
        name  = "OTEL_TO_CLOUD"
        value = "true"
      }

      ports {
        container_port = 8000
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8000
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8000
        }
        period_seconds    = 15
        failure_threshold = 3
      }
    }
  }

  depends_on = [
    google_project_iam_member.vertex_ai_user,
    google_project_iam_member.secret_accessor,
  ]
}

# Allow unauthenticated invocations (can be restricted via IAP / IAM in enterprise)
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
