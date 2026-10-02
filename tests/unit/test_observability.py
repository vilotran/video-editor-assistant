"""Unit tests for Observability: structured logging, intent/outcome, tracing, and PII redaction."""

from app.observability.intent_outcome import IntentOutcomeAuditLogger
from app.observability.pii_redaction import PIIRedactionPipeline
from app.observability.tracing import trace_span


def test_pii_redaction_regex():
    pipeline = PIIRedactionPipeline(enable_cloud_dlp=False)
    raw_text = "Contact me at director@hollywood.com or call +1 555-123-4567 with API key AIzaSyA123456789012345678901234567890."
    sanitized = pipeline.redact_text(raw_text)
    assert "director@hollywood.com" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "[REDACTED_PHONE]" in sanitized
    assert "[REDACTED_API_KEY]" in sanitized


def test_pii_redaction_dict():
    raw_dict = {
        "user_email": "editor@studio.com",
        "nested": {"phone": "555-444-3333", "ok": "keep_this"},
    }
    pipeline = PIIRedactionPipeline(enable_cloud_dlp=False)
    cleaned = pipeline.redact_dict(raw_dict)
    assert cleaned["user_email"] == "[REDACTED_EMAIL]"
    assert cleaned["nested"]["phone"] == "[REDACTED_PHONE]"
    assert cleaned["nested"]["ok"] == "keep_this"


def test_intent_outcome_logger():
    # Verify no exceptions raised during logging
    start_t = IntentOutcomeAuditLogger.log_intent(
        correlation_id="test_corr_01",
        agent_name="TimelineAgent",
        tool_name="test_tool",
        arguments={"param": 1},
        intent_summary="Test execution intent",
    )
    assert start_t > 0
    IntentOutcomeAuditLogger.log_outcome(
        correlation_id="test_corr_01",
        agent_name="TimelineAgent",
        tool_name="test_tool",
        start_time=start_t,
        status="SUCCESS",
        result={"output": "ok"},
    )


def test_trace_span_context_manager():
    with trace_span("test_span", {"test_key": "test_val"}) as span:
        assert span is not None
