import json
import os
from datetime import datetime, timedelta

from google import genai
import pytz

from .models import Event
from .logger import get_logger

logger = get_logger(__name__)


def filter_events_for_tomorrow(events: list[Event]) -> list[Event]:
    """Filter events to only those happening tomorrow.

    Args:
        events: List of all events

    Returns:
        List of events scheduled for tomorrow
    """
    # Use local time for tomorrow logic
    tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).date()

    return [event for event in events if event.start.date() == tomorrow]


class LLMFilter:
    """Filter events using Google Gemini LLM."""

    def __init__(self, api_key: str | None = None):
        """Initialize LLM filter.

        Args:
            api_key: Gemini API key. Defaults to GEMINI_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set. LLM filtering will be disabled.")
            return

        self.client = genai.Client(api_key=self.api_key)

    def filter_for_user(self, events: list[Event], user_preferences: str) -> list[Event]:
        """Filter and rank events based on user preferences.

        Args:
            events: List of candidate events
            user_preferences: Natural language user preferences

        Returns:
            List of events with relevance scores and reasons, sorted by relevance.
        """
        if not self.api_key or not user_preferences or not events:
            return events

        # Prepare events for context
        events_context = []
        for i, event in enumerate(events):
            events_context.append({
                "id": i,
                "title": event.title,
                "description": event.description[:200],  # Truncate for token limit
                "start": event.start.isoformat(),
            })

        prompt = f"""
        You are an expert Event Curator for València, Spain.
        
        User Preferences: "{user_preferences}"
        
        Task: 
        1. Analyze the list of events below.
        2. select ONLY the events that strongly match the user's preferences.
        3. Assign a relevance score (0.0 to 1.0).
        4. Provide a 1-sentence reason why it fits.
        
        Events:
        {json.dumps(events_context, indent=2)}
        
        Output MUST be a valid JSON list of objects with keys: "id", "score", "reason".
        Example: [{{"id": 0, "score": 0.9, "reason": "Matches interest in jazz."}}]
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=prompt
            )
            # Simple cleanup for potential markdown code blocks in response
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:-3]
            elif text.startswith("```"):
                text = text[3:-3]
            
            recommendations = json.loads(text)
            
            # Map back to event objects
            personalized_events = []
            for rec in recommendations:
                try:
                    idx = rec["id"]
                    if 0 <= idx < len(events):
                        event = events[idx].model_copy()
                        event.relevance_score = float(rec["score"])
                        event.relevance_reason = rec["reason"]
                        personalized_events.append(event)
                except (KeyError, ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse recommendation: {rec} - {e}")

            # Sort by score descending
            personalized_events.sort(key=lambda e: e.relevance_score or 0, reverse=True)
            
            return personalized_events

        except Exception as e:
            logger.error(f"LLM filtering failed: {e}")
            return events  # Fallback to original list
