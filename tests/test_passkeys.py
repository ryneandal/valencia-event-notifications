"""Tests for passkey authentication."""

import json
from unittest.mock import MagicMock, patch
import pytest
from valencia_events.storage import EventStorage

from fastapi.testclient import TestClient
from valencia_events.web.app import app

@pytest.fixture
def client():
    return TestClient(app)

# Mock session data
@pytest.fixture
def mock_user_session(client):
    """Fixture to simulate logged-in user."""
    # We can't directly set session with TestClient easily without a route helper or mocking SessionMiddleware
    # But we can assume the routes check request.session.
    # For integration tests with TestClient, we'd need to mock the storage lookup or cookie.
    pass

@patch("valencia_events.web.auth_passkeys.make_registration_options")
@patch("valencia_events.web.auth_passkeys.EventStorage")
def test_register_options_not_logged_in(mock_storage, mock_make_options, client):
    """Test accessing register options without login calls 401."""
    response = client.post("/auth/webauthn/register/options")
    # Should be 401 because no session
    assert response.status_code == 401

@patch("valencia_events.web.auth_passkeys.make_authentication_options")
def test_login_options(mock_make_options, client):
    """Test getting login options."""
    mock_options = MagicMock()
    mock_options.challenge = b"123"
    mock_make_options.return_value = mock_options
    
    with patch("valencia_events.web.auth_passkeys.options_to_json", return_value='{"challenge": "MTIz"}'):
        response = client.post("/auth/webauthn/login/options")
        assert response.status_code == 200
        assert "challenge" in response.json()
