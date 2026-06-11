"""
Lab 11 — Helper Utilities
"""
import asyncio
import re

from google.genai import types


def _get_retry_delay(error: Exception, default_delay: float = 10.0) -> float:
    """Extract a retry delay from quota errors when the provider includes one."""
    match = re.search(r"retryDelay': '(\d+)s", str(error))
    if match:
        return max(float(match.group(1)) + 1.0, default_delay)
    return default_delay


def _is_quota_error(error: Exception) -> bool:
    """Check whether an exception is a transient Gemini quota/rate-limit error."""
    error_text = str(error).upper()
    return "RESOURCE_EXHAUSTED" in error_text or "429" in error_text


async def chat_with_agent(
    agent,
    runner,
    user_message: str,
    session_id=None,
    max_retries: int = 3,
):
    """Send a message to the agent and get the response.

    The helper retries transient Gemini 429 quota errors so lab test suites do
    not fail just because several prompts were sent in the same minute.

    Args:
        agent: The LlmAgent instance
        runner: The InMemoryRunner instance
        user_message: Plain text message to send
        session_id: Optional session ID to continue a conversation
        max_retries: Number of quota retry attempts before raising

    Returns:
        Tuple of (response_text, session)
    """
    user_id = "student"
    app_name = runner.app_name

    session = None
    if session_id is not None:
        try:
            session = await runner.session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
        except (ValueError, KeyError):
            pass

    if session is None:
        try:
            session = await runner.session_service.create_session(
                app_name=app_name, user_id=user_id
            )
        except Exception:
            session = await runner.session_service.create_session(
                app_name=app_name, user_id=user_id
            )

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)],
    )

    for attempt in range(max_retries + 1):
        try:
            final_response = ""
            async for event in runner.run_async(
                user_id=user_id, session_id=session.id, new_message=content
            ):
                if hasattr(event, "content") and event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            final_response += part.text
            return final_response, session
        except Exception as error:
            if not _is_quota_error(error) or attempt >= max_retries:
                raise
            delay = _get_retry_delay(error)
            print(f"Quota limit hit. Waiting {delay:.0f}s before retrying...")
            await asyncio.sleep(delay)

    return "", session
