"""Tests for email functionality.

Test acceptance criteria:
- HTML email can be built from event list
- Email sending works with mock SMTP server
- Credentials are read from environment variables
- Error handling for missing credentials
"""

from unittest.mock import patch

import pytest


class TestMailer:
    """Test suite for mailer functionality."""

    @pytest.fixture
    def sample_events(self):
        """Create sample events for email testing."""
        from datetime import datetime

        from valencia_events.models import Event
        return [
            Event(
                title="Test Event 1",
                start=datetime(2025, 10, 12, 10, 0),
                url="https://example.com/1",
                description="Desc 1",
                source="test"
            ),
            Event(
                title="Test Event 2",
                start=datetime(2025, 10, 12, 14, 0),
                url="https://example.com/2",
                source="test"
            )
        ]

    def test_build_html(self, sample_events):
        """Test HTML email building."""
        from datetime import datetime

        from valencia_events.mailer import build_html

        html = build_html(sample_events, datetime(2025, 10, 12))
        assert "<html>" in html
        assert "Test Event 1" in html
        assert "Test Event 2" in html
        assert "Desc 1" in html

    def test_build_html_empty_events(self):
        """Test HTML building with no events."""
        from datetime import datetime

        from valencia_events.mailer import build_html

        html = build_html([], datetime(2025, 10, 12))
        assert "No events found" in html

    @patch("smtplib.SMTP")
    def test_send_email_success(self, mock_smtp):
        """Test email sending with mocked SMTP."""
        import os

        from valencia_events.mailer import send_email

        # Mock env vars
        with patch.dict(os.environ, {"SMTP_USER": "u", "SMTP_APP_PASSWORD": "p"}):
            result = send_email("Subj", "Body", "to@example.com")

        assert result is True
        mock_smtp.assert_called()
        instance = mock_smtp.return_value.__enter__.return_value
        instance.starttls.assert_called()
        instance.login.assert_called_with("u", "p")
        instance.send_message.assert_called()

    def test_send_email_missing_credentials(self):
        """Test that missing credentials raise ValueError."""
        import os

        from valencia_events.mailer import send_email

        # Clear env vars
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                send_email("S", "B", "t")
