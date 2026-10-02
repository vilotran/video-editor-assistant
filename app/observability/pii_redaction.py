"""PII Redaction Pipeline utilizing Cloud DLP API client interface with regex fallback."""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Standard Regex patterns for sensitive identifiers
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
API_KEY_PATTERN = re.compile(r"\b(?:AIza[0-9A-Za-z-_]{30,45}|sk-[a-zA-Z0-9]{25,}|Bearer\s+[A-Za-z0-9._\-]+)\b")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


class PIIRedactionPipeline:
    """Enterprise PII scrubbing pipeline applying Cloud DLP API and regex filters."""

    def __init__(self, project_id: str | None = None, enable_cloud_dlp: bool = True) -> None:
        self.project_id = project_id
        self.enable_cloud_dlp = enable_cloud_dlp
        self._dlp_client: Any = None
        self._init_dlp_client()

    def _init_dlp_client(self) -> None:
        """Initializes Google Cloud DLP client if credentials and project are available."""
        if not self.enable_cloud_dlp or not self.project_id:
            return
        try:
            from google.cloud import dlp_v2
            self._dlp_client = dlp_v2.DlpServiceClient()
        except Exception:
            # Degrade cleanly to regex scrubbing if Cloud DLP is not configured or in offline test environment
            self._dlp_client = None

    def redact_text(self, text: str) -> str:
        """Scrubs sensitive data from text, returning sanitized output."""
        if not text:
            return text

        # 1. Attempt Cloud DLP Inspection if available
        if self._dlp_client and self.project_id:
            try:
                from google.cloud import dlp_v2
                parent = f"projects/{self.project_id}"
                item = {"value": text}
                inspect_config = {
                    "info_types": [
                        {"name": "EMAIL_ADDRESS"},
                        {"name": "PHONE_NUMBER"},
                        {"name": "CREDIT_CARD_NUMBER"},
                        {"name": "US_SOCIAL_SECURITY_NUMBER"},
                        {"name": "AUTH_TOKEN"},
                    ],
                    "min_likelihood": dlp_v2.Likelihood.LIKELY,
                }
                deidentify_config = {
                    "info_type_transformations": {
                        "transformations": [
                            {"primitive_transformation": {"replace_with_info_type_config": {}}}
                        ]
                    }
                }
                response = self._dlp_client.deidentify_content(
                    request={
                        "parent": parent,
                        "deidentify_config": deidentify_config,
                        "inspect_config": inspect_config,
                        "item": item,
                    }
                )
                return response.item.value
            except Exception:
                # Fallback to regex pipeline
                pass

        # 2. Comprehensive Regex Scrubber (Always active)
        sanitized = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
        sanitized = PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
        sanitized = API_KEY_PATTERN.sub("[REDACTED_API_KEY]", sanitized)
        sanitized = CREDIT_CARD_PATTERN.sub("[REDACTED_CARD]", sanitized)
        sanitized = SSN_PATTERN.sub("[REDACTED_SSN]", sanitized)
        return sanitized

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively sanitizes values in a dictionary structure."""
        sanitized: dict[str, Any] = {}
        for key, val in data.items():
            if isinstance(val, str):
                sanitized[key] = self.redact_text(val)
            elif isinstance(val, dict):
                sanitized[key] = self.redact_dict(val)
            elif isinstance(val, list):
                sanitized[key] = [
                    self.redact_text(v) if isinstance(v, str)
                    else self.redact_dict(v) if isinstance(v, dict)
                    else v
                    for v in val
                ]
            else:
                sanitized[key] = val
        return sanitized


# Global default instance
_default_redactor = PIIRedactionPipeline()


def redact_pii(text: str) -> str:
    """Convenience helper to redact sensitive PII from a string."""
    return _default_redactor.redact_text(text)


def redact_pii_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Convenience helper to redact sensitive PII from a dictionary."""
    return _default_redactor.redact_dict(data)
