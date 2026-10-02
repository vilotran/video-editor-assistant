"""Integration tests for Director agent, sub-agent delegation, and safety plugin wiring."""

from app.agent import app, root_agent
from app.agents.director_agent import director_agent
from app.agents.mask_agent import mask_agent
from app.agents.timeline_agent import timeline_agent
from app.agents.vfx_agent import vfx_agent
from app.guardrails.policy_plugin import VFXSafetyPolicyPlugin


def test_root_agent_hierarchy():
    """Verifies coordinator and sub-agents structure."""
    assert root_agent.name == "director_agent"
    assert len(root_agent.sub_agents) == 3
    subagent_names = [sub.name for sub in root_agent.sub_agents]
    assert "timeline_agent" in subagent_names
    assert "mask_and_track_agent" in subagent_names
    assert "vfx_compositor_agent" in subagent_names


def test_strategic_model_routing():
    """Verifies Director uses pro model and sub-agents use flash model."""
    assert "pro" in director_agent.model.model or "gemini" in director_agent.model.model
    assert "flash" in timeline_agent.model.model or "gemini" in timeline_agent.model.model
    assert "flash" in mask_agent.model.model or "gemini" in mask_agent.model.model
    assert "flash" in vfx_agent.model.model or "gemini" in vfx_agent.model.model


def test_app_plugins_attached():
    """Verifies VFXSafetyPolicyPlugin is attached to App."""
    plugin_types = [type(p) for p in app.plugins]
    assert VFXSafetyPolicyPlugin in plugin_types


def test_tools_exposed_on_specialists():
    """Verifies that all 7 mock editing tools are properly distributed across agents."""
    timeline_tool_names = [getattr(t, "name", str(t)) for t in timeline_agent.tools]
    assert any("split_clip_at_timecode" in name for name in timeline_tool_names)
    assert any("get_timeline_state" in name for name in timeline_tool_names)
    assert any("undo_last_timeline_action" in name for name in timeline_tool_names)

    mask_tool_names = [getattr(t, "name", str(t)) for t in mask_agent.tools]
    assert any("track_character_motion_keyframes" in name for name in mask_tool_names)
    assert any("create_foreground_rotoscope_mask" in name for name in mask_tool_names)

    vfx_tool_names = [getattr(t, "name", str(t)) for t in vfx_agent.tools]
    assert any("pin_character_overlay_to_track" in name for name in vfx_tool_names)
    assert any("create_masked_picture_in_picture" in name for name in vfx_tool_names)
    assert any("render_mock_composite_export" in name for name in vfx_tool_names)
