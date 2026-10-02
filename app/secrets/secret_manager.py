"""Secure Secret Management client using Google Cloud Secret Manager with zero hardcoded keys."""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)


class SecretManager:
    """Client for retrieving secrets from Google Cloud Secret Manager with local env fallback."""

    def __init__(self, project_id: str | None = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initializes the SecretManagerServiceClient if GCP credentials are present."""
        try:
            from google.cloud import secretmanager
            self._client = secretmanager.SecretManagerServiceClient()
        except Exception:
            self._client = None

    def get_secret(self, secret_id: str, version_id: str = "latest", default: str | None = None) -> str | None:
        """Retrieves secret payload from GCP Secret Manager or falls back to environment variable."""
        # Check GCP Secret Manager first if available
        if self._client and self.project_id:
            try:
                name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version_id}"
                response = self._client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as exc:
                logger.debug(
                    "GCP Secret Manager retrieval fallback to environment",
                    secret_id=secret_id,
                    reason=str(exc),
                )

        # Fallback to local environment variable
        env_val = os.getenv(secret_id) or os.getenv(secret_id.upper())
        if env_val:
            return env_val

        return default


# Global instance
secret_manager = SecretManager()
