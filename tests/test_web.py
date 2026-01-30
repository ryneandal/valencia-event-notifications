"""Tests for the web application."""

import pytest
from fastapi.testclient import TestClient
from valencia_events.web.app import app
from valencia_events.storage import EventStorage

@pytest.fixture
def client():
    return TestClient(app)

def test_home_page(client):
    """Test landing page loads."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Valencia Events" in response.text
    assert "Sign in with Google" in response.text

def test_dashboard_redirects_when_not_logged_in(client):
    """Test dashboard requires login."""
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"] == "/"

def test_dashboard_access_with_session(client):
    """Test dashboard loads for logged in user."""
    # TODO: Implement this test
    pass
