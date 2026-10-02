"""Main agent entrypoint exposing root_agent (director_agent) and App."""

from __future__ import annotations

from google.adk.apps import App

from app.agents.director_agent import director_agent
from app.guardrails.policy_plugin import VFXSafetyPolicyPlugin
from app.observability.logging import app_logger

# Root agent configured as the multi-agent Director coordinator
root_agent = director_agent

# Attach the enterprise safety and guardrail plugin to the App
app = App(
    root_agent=root_agent,
    name="app",
    plugins=[VFXSafetyPolicyPlugin()],
)

app_logger.info("ADK App initialized with director_agent and VFXSafetyPolicyPlugin")
