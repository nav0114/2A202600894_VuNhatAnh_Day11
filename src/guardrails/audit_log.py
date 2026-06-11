"""
Audit Log Plugin for Defense-in-Depth Pipeline
"""
import json
import time
from pathlib import Path
from uuid import uuid4

from google.genai import types
# pyrefly: ignore [missing-import]
from google.adk.plugins import base_plugin
# pyrefly: ignore [missing-import]
from google.adk.agents.invocation_context import InvocationContext

class AuditLogPlugin(base_plugin.BasePlugin):
    """Plugin that logs all interactions (input, output, latency) to a JSON file.
    
    Why is it needed: To monitor the system for malicious activity, keep records of 
    what the AI said to customers (for compliance), and track performance metrics 
    like latency.
    """
    def __init__(self, log_file: str = "audit_log.json"):
        super().__init__(name="audit_log")
        self.log_file = Path(log_file)
        self.logs = []
        self._start_time = {}

    def _extract_text(self, content) -> str:
        """Extract plain text from a Content or LLM response object."""
        if hasattr(content, "content") and content.content:
            content = content.content

        if not content or not content.parts:
            return ""

        text = ""
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                text += part.text
        return text

    def _get_context_value(self, context, name: str, default=None):
        """Read a value from a callback context without assuming its exact type."""
        return getattr(context, name, default) if context is not None else default

    def _set_context_value(self, context, name: str, value):
        """Best-effort context annotation used to correlate input and output logs."""
        if context is not None:
            try:
                setattr(context, name, value)
            except Exception:
                pass

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        """Log the incoming user message and start the timer."""
        request_id = self._get_context_value(
            invocation_context, "request_id", f"req-{uuid4().hex}"
        )
        
        self._set_context_value(invocation_context, "request_id", request_id)
        self._start_time[request_id] = time.time()
        
        log_entry = {
            "timestamp": time.time(),
            "request_id": request_id,
            "user_id": self._get_context_value(invocation_context, "user_id", "unknown"),
            "user_input": self._extract_text(user_message),
            "status": "started",
            "layer_blocked": None,
        }
        self.logs.append(log_entry)
        self.export_json()
        
        return None

    async def after_model_callback(
        self,
        *,
        callback_context,
        llm_response,
    ):
        """Log the agent's response and calculate latency."""
        request_id = self._get_context_value(callback_context, "request_id")
        
        log_entry = None
        for log in reversed(self.logs):
            if log.get("request_id") == request_id:
                log_entry = log
                break
            if request_id is None and log.get("status") == "started":
                log_entry = log
                break
                
        if log_entry:
            start_time = self._start_time.get(request_id, log_entry["timestamp"])
            latency = time.time() - start_time
            
            log_entry["response"] = self._extract_text(llm_response)
            log_entry["latency_seconds"] = round(latency, 3)
            log_entry["status"] = "completed"
            
            self.export_json()
            
        return llm_response
        
    def export_json(self):
        """Export the collected logs to the JSON file."""
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self.logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to write audit log: {e}")
