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
    """Convert A2UI JSON in text output to rendered components as an after_model_callback.

    Guarantees:
    1. Preserves non-A2UI plain text (such as one-line summaries) so message bubbles never render empty.
    2. Wraps valid A2UI v0.8 messages in the exact format the ADK 2.6.2 dev UI renderer expects.
    3. Never drops the model's text: if A2UI parsing fails, returns the original response unchanged.
    """
    if not llm_response.content or not llm_response.content.parts:
        return llm_response

    new_parts = []
    has_a2ui = False

    for part in llm_response.content.parts:
        if not part.text:
            new_parts.append(part)
            continue

        raw_text = part.text
        if not any(k in raw_text for k in ("beginRendering", "surfaceUpdate", "dataModelUpdate", "createSurface")):
            new_parts.append(part)
            continue

        # Look for markdown code fence containing JSON
        fence_match = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", raw_text, re.DOTALL)
        plain_prefix = ""
        plain_suffix = ""
        json_candidate = ""

        if fence_match:
            plain_prefix = raw_text[:fence_match.start()].strip()
            plain_suffix = raw_text[fence_match.end():].strip()
            json_candidate = fence_match.group(1).strip()
        else:
            # Fallback: find first JSON bracket
            first_bracket = -1
            for idx, ch in enumerate(raw_text):
                if ch in ("[", "{"):
                    first_bracket = idx
                    break
            if first_bracket != -1:
                plain_prefix = raw_text[:first_bracket].strip()
                json_candidate = raw_text[first_bracket:].strip()

        if not json_candidate:
            new_parts.append(part)
            continue

        # Attempt JSON decoding
        parsed = None
        try:
            parsed, _ = json.JSONDecoder().raw_decode(json_candidate)
        except json.JSONDecodeError:
            try:
                # Handle concatenated JSON objects: {"beginRendering":...} {"surfaceUpdate":...}
                fixed = "[" + re.sub(r'\}\s*\{', '},{', json_candidate) + "]"
                parsed, _ = json.JSONDecoder().raw_decode(fixed)
            except json.JSONDecodeError:
                # Parsing failed - keep original part unchanged
                new_parts.append(part)
                continue

        if not isinstance(parsed, list):
            parsed = [parsed]

        a2ui_keys = {"beginRendering", "surfaceUpdate", "dataModelUpdate", "deleteSurface", "createSurface"}
        a2ui_messages = [msg for msg in parsed if isinstance(msg, dict) and any(k in msg for k in a2ui_keys)]

        if not a2ui_messages:
            # No valid A2UI messages found - retain original part
            new_parts.append(part)
            continue

        has_a2ui = True

        # Preserve plain text preceding or succeeding the A2UI block
        full_plain = "\n\n".join(filter(None, [plain_prefix, plain_suffix])).strip()
        if full_plain:
            new_parts.append(types.Part(text=full_plain))

        # Add the wrapped A2UI parts
        for msg in a2ui_messages:
            new_parts.append(_wrap_a2ui_part(msg))

    if not has_a2ui:
        return llm_response

    return LlmResponse(
        content=types.Content(role="model", parts=new_parts),
        custom_metadata={"a2a:response": "true"},
    )
