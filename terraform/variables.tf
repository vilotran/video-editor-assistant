variable "project_id" {
  description = "The Google Cloud Project ID where resources will be provisioned"
  type        = string
  default     = "l200-509713"
}

variable "region" {
  description = "The GCP region for Cloud Run and Artifact Registry"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "The name of the Cloud Run agent service"
  type        = string
  default     = "video-editor-assistant"
}

variable "container_image" {
  description = "The container image to deploy to Cloud Run"
  type        = string
  default     = "us-central1-docker.pkg.dev/l200-509713/video-editor-assistant/agent:latest"
}

variable "director_model" {
  description = "Gemini model identifier for Director coordinator agent"
  type        = string
  default     = "gemini-2.5-pro"
}

variable "subagent_model" {
  description = "Gemini model identifier for specialist sub-agents"
  type        = string
  default     = "gemini-2.5-flash"
}
