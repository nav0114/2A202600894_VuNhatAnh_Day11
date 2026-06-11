"""
Rate Limiter Plugin for Defense-in-Depth Pipeline
"""
import time
from collections import deque

from google.genai import types
# pyrefly: ignore [missing-import]
from google.adk.plugins import base_plugin
# pyrefly: ignore [missing-import]
from google.adk.agents.invocation_context import InvocationContext

class RateLimitPlugin(base_plugin.BasePlugin):
    """Plugin that limits the number of requests a user can make in a given time window.
    
    Why is it needed: To prevent spam, brute-force prompt injection attacks, and 
    denial-of-service (DDoS) attacks that could exhaust the LLM's quota or compute resources.
    """
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        super().__init__(name="rate_limit")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.history = {}  # Map of user_id -> deque of timestamps
        self.blocked_count = 0

    def _block_response(self, text: str) -> types.Content:
        """Create the ADK Content object returned when rate limiting blocks a user."""
        return types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)],
        )

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        """Check if the user has exceeded their rate limit before processing the request."""
        # Use a default user ID if not provided in the context
        user_id = getattr(invocation_context, "user_id", "default_user")
        now = time.time()
        
        if user_id not in self.history:
            self.history[user_id] = deque()
            
        timestamps = self.history[user_id]
        
        # Remove timestamps outside the current window
        while timestamps and timestamps[0] < now - self.window_seconds:
            timestamps.popleft()
            
        # Check if the user has hit the limit
        if len(timestamps) >= self.max_requests:
            self.blocked_count += 1
            wait_time = max(1, int(self.window_seconds - (now - timestamps[0])))
            return self._block_response(
                "I cannot process your request right now. You have exceeded the maximum "
                f"number of requests ({self.max_requests} requests per {self.window_seconds} seconds). "
                f"Please try again in about {wait_time} seconds."
            )
            
        # Add the current request timestamp
        timestamps.append(now)
        return None
