"""Tests for notify.py (duplicated from shovel.watch's own notify.py)."""

import importlib
import os
from unittest.mock import MagicMock, patch


def test_notify_skips_when_no_config():
    with patch.dict(os.environ, {"SHOVEL_BOT_URL": "", "SHOVEL_BOT_API_KEY": ""}, clear=False):
        from ops_agent.daily_ops import notify
        importlib.reload(notify)
        result = notify.send_alert("error", "Test", "Test message")
    assert result is False


def test_notify_sends_request():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        with patch.dict(
            os.environ,
            {
                "SHOVEL_BOT_URL": "https://api.shovel.bot",
                "SHOVEL_BOT_API_KEY": "test-key",
                "SHOVEL_BOT_CHANNEL": "#test",
            },
            clear=False,
        ):
            from ops_agent.daily_ops import notify
            importlib.reload(notify)
            result = notify.send_alert("info", "Hello", "World")

    assert result is True
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    body = kwargs["json"]
    assert body["severity"] == "info"
    assert body["title"] == "Hello"
    assert body["app"] == "oshvl-ops-agent"


def test_send_nightly_digest_skips_when_no_config():
    with patch.dict(os.environ, {"SHOVEL_BOT_URL": "", "SHOVEL_BOT_API_KEY": ""}, clear=False):
        from ops_agent.daily_ops import notify
        importlib.reload(notify)
        result = notify.send_nightly_digest({}, {})
    assert result is False


def test_send_nightly_digest_posts_summary():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        with patch.dict(
            os.environ,
            {
                "SHOVEL_BOT_URL": "https://api.shovel.bot",
                "SHOVEL_BOT_API_KEY": "test-key",
                "SHOVEL_BOT_CHANNEL": "#test",
                "HOSTNAME": "compute.example.lan",
            },
            clear=False,
        ):
            from ops_agent.daily_ops import notify
            importlib.reload(notify)
            metrics = {"load_1": 0.1, "load_5": 0.1, "load_15": 0.1, "failed_services": []}
            result = notify.send_nightly_digest(metrics, {})

    assert result is True
    _, kwargs = mock_post.call_args
    body = kwargs["json"]
    assert "compute.example.lan" in body["message"]
    assert body["title"].startswith("Server Health — compute.example.lan | ")
    # No header block — avoids duplicating the title as its own line above
    # the message, which already opens with "Server Health — {hostname}".
    assert all(block["type"] != "header" for block in body["blocks"])
