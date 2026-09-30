"""A2UI utilities for parsing model outputs and wrapping A2UI messages."""

import json
import re
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def _wrap_a2ui_part(a2ui_message: dict) -> types.Part:
    """Wrap a single A2UI message for rendering in adk web / A2UI clients."""
    datapart_json = json.dumps({
        "kind": "data",
        "metadata": {"mimeType": "application/json+a2ui"},
        "data": a2ui_message,
    })
    blob_data = (
        b"<a2a_datapart_json>" + datapart_json.encode("utf-8") + b"</a2a_datapart_json>"
    )
    return types.Part(
        inline_data=types.Blob(
            data=blob_data,
            mime_type="text/plain",
        )
    )


def a2ui_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Convert A2UI JSON in text output to rendered components as an after_model_callback."""
    if not llm_response.content or not llm_response.content.parts:
        return None

    for part in llm_response.content.parts:
        if not part.text:
            continue
        text = part.text.strip()
        if not text:
            continue

        if not any(k in text for k in ("beginRendering", "surfaceUpdate", "dataModelUpdate", "createSurface")):
            continue

        # Strip markdown fences
        clean_text = text
        if "```json" in clean_text:
            match = re.search(r"```json\s*(.*?)\s*```", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1).strip()
        elif "```" in clean_text:
            match = re.search(r"```\s*(.*?)\s*```", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1).strip()

        # Find where JSON starts
        json_start = None
        for i, ch in enumerate(clean_text):
            if ch in ("[", "{"):
                json_start = i
                break
        if json_start is None:
            continue

        json_text = clean_text[json_start:]

        # raw_decode parses JSON and ignores trailing text
        try:
            parsed, _ = json.JSONDecoder().raw_decode(json_text)
        except json.JSONDecodeError:
            # Handle concatenated JSON objects: {"a":1} {"b":2}
            try:
                fixed = "[" + re.sub(r'\}\s*\{', '},{', json_text) + "]"
                parsed, _ = json.JSONDecoder().raw_decode(fixed)
            except json.JSONDecodeError:
                continue

        if not isinstance(parsed, list):
            parsed = [parsed]

        a2ui_keys = {"beginRendering", "surfaceUpdate", "dataModelUpdate", "deleteSurface", "createSurface"}
        a2ui_messages = [msg for msg in parsed if isinstance(msg, dict) and any(k in msg for k in a2ui_keys)]

        if not a2ui_messages:
            continue

        new_parts = [_wrap_a2ui_part(msg) for msg in a2ui_messages]
        return LlmResponse(
            content=types.Content(role="model", parts=new_parts),
            custom_metadata={"a2a:response": "true"},
        )

    return None
