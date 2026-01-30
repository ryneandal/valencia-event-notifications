"""Tests for LLM personalization."""

from unittest.mock import MagicMock, patch
from datetime import datetime
import pytest
from valencia_events.filters import LLMFilter
from valencia_events.models import Event

@pytest.fixture
def sample_events():
    return [
        Event(
            title="Jazz Night",
            start=datetime.now(),
            url="http://example.com/1",
            description="A night of smooth jazz.",
            source="test",
            event_hash="hash1"
        ),
        Event(
            title="Heavy Metal Concert",
            start=datetime.now(),
            url="http://example.com/2",
            description="Loud music.",
            source="test",
            event_hash="hash2"
        )
    ]

@patch("google.genai.Client")
def test_llm_filter_selection(mock_client_class, sample_events):
    """Test LLM filter parsing."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Mock response
    mock_response = MagicMock()
    # Mock return JSON
    mock_response.text = '```json\n[{"id": 0, "score": 0.9, "reason": "You love jazz."}]\n```'
    
    # Mock client.models.generate_content
    mock_client.models.generate_content.return_value = mock_response
    
    llm = LLMFilter(api_key="fake-key")
    filtered = llm.filter_for_user(sample_events, "I love jazz")
    
    assert len(filtered) == 1
    assert filtered[0].title == "Jazz Night"
    assert filtered[0].relevance_score == 0.9
    assert filtered[0].relevance_reason == "You love jazz."

def test_llm_filter_no_key(sample_events):
    """Test graceful degradation without API key."""
    with patch.dict("os.environ", {}, clear=True):
        llm = LLMFilter(api_key=None)
        filtered = llm.filter_for_user(sample_events, "I love jazz")
        # Should return all events unmodified
        assert len(filtered) == 2
        assert filtered[0].relevance_score is None
