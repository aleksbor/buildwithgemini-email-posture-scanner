"""A2UI utilities for parsing model outputs and wrapping A2UI messages."""

import json
import logging
import re
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types

logger = logging.getLogger(__name__)


def _clean_latin1_text(s: str) -> str:
    """Normalize and convert strings to Latin-1 range, stripping non-Latin-1 characters."""
    s = re.sub(r"[🟢🟡🟠🔴]\s*", "", s)
    s = re.sub(r"✅\s*(pass)?", "PASS", s, flags=re.IGNORECASE)
    s = re.sub(r"⚠️\s*(warn(?:ing)?)?", "WARN", s, flags=re.IGNORECASE)
    s = re.sub(r"❌\s*(fail)?", "FAIL", s, flags=re.IGNORECASE)
    s = (
        s.replace("–", "-")
        .replace("—", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("‘", "'")
    )
    return "".join(ch for ch in s if ord(ch) <= 255)


def _sanitize_for_latin1(obj):
    """Recursively sanitize an object's string fields to ensure Latin-1 safety for btoa()."""
    if isinstance(obj, str):
        return _clean_latin1_text(obj)
    elif isinstance(obj, dict):
        return {_clean_latin1_text(k) if isinstance(k, str) else k: _sanitize_for_latin1(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_latin1(v) for v in obj]
    return obj


def _wrap_a2ui_part(a2ui_message: dict) -> types.Part:
    """Wrap a single A2UI message for rendering in adk web / A2UI clients.

    Guarantees Latin-1 compatibility inside the A2UI JSON payload so unpatched ADK Dev UI
    btoa() calls do not crash.
    """
    safe_message = _sanitize_for_latin1(a2ui_message)
    datapart_json = json.dumps({
        "kind": "data",
        "metadata": {"mimeType": "application/json+a2ui"},
        "data": safe_message,
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
    1. Always returns a non-empty final reply: never returns None or drops content.
    2. Preserves non-A2UI plain text (such as one-line summaries) so message bubbles never render empty.
    3. Wraps valid A2UI v0.8 messages in the exact format the ADK 2.6.2 dev UI renderer expects.
    4. If A2UI JSON fails to parse or validate, logs the parse error and returns the original text unchanged.
    """
    if llm_response is None:
        logger.warning("a2ui_callback received None llm_response")
        return llm_response

    if not llm_response.content or not llm_response.content.parts:
        return llm_response

    try:
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

            plain_prefix = ""
            plain_suffix = ""
            json_candidate = ""

            # Check for <a2ui-json> ... </a2ui-json> first
            tag_match = re.search(r"<a2ui-json>(.*?)</a2ui-json>", raw_text, re.DOTALL)
            if tag_match:
                plain_prefix = raw_text[:tag_match.start()].strip()
                plain_suffix = raw_text[tag_match.end():].strip()
                json_candidate = tag_match.group(1).strip()
            elif "<a2a_datapart_json>" in raw_text:
                # Handle model outputting <a2a_datapart_json> wrapper tags
                plain_prefix = re.split(r"<a2a_datapart_json>", raw_text)[0].strip()
                a2a_blocks = re.findall(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", raw_text, re.DOTALL)
                json_candidate = " ".join(a2a_blocks).strip()
            else:
                # Look for markdown code fence containing JSON
                fence_match = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", raw_text, re.DOTALL)
                if fence_match:
                    plain_prefix = raw_text[:fence_match.start()].strip()
                    plain_suffix = raw_text[fence_match.end():].strip()
                    json_candidate = fence_match.group(1).strip()
                else:
                    # Fallback: look for opening JSON bracket
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

            # Attempt JSON decoding, supporting single objects, lists, or multiple concatenated objects
            parsed_objs = []
            idx = 0
            candidate_str = json_candidate.strip()
            decoder = json.JSONDecoder()
            while idx < len(candidate_str):
                while idx < len(candidate_str) and candidate_str[idx] in " \t\r\n,":
                    idx += 1
                if idx >= len(candidate_str):
                    break
                try:
                    obj, end = decoder.raw_decode(candidate_str, idx)
                    parsed_objs.append(obj)
                    idx = end
                except Exception:
                    break

            if not parsed_objs:
                # Fallback: attempt regex comma insertion for concatenated objects
                try:
                    fixed = "[" + re.sub(r'\}\s*\{', '},{', candidate_str) + "]"
                    loaded = json.loads(fixed)
                    parsed_objs = loaded if isinstance(loaded, list) else [loaded]
                except Exception as fixed_err:
                    logger.warning(
                        "Failed to parse A2UI JSON from model response (fixed err: %s). "
                        "Returning original text unchanged.",
                        fixed_err,
                    )
                    new_parts.append(part)
                    continue

            # Unwrap any {"kind": "data", "metadata": ..., "data": {...}} wrappers
            a2ui_keys = {"beginRendering", "surfaceUpdate", "dataModelUpdate", "deleteSurface", "createSurface"}
            def _unwrap_items(items):
                result = []
                for it in items:
                    if isinstance(it, list):
                        result.extend(_unwrap_items(it))
                    elif isinstance(it, dict):
                        if it.get("kind") == "data" and "data" in it and isinstance(it["data"], dict):
                            inner = it["data"]
                            if any(k in inner for k in a2ui_keys):
                                result.append(inner)
                                continue
                        if any(k in it for k in a2ui_keys):
                            result.append(it)
                return result

            a2ui_messages = _unwrap_items(parsed_objs)

            if not a2ui_messages:
                logger.warning("Parsed JSON did not contain any valid A2UI message keys. Returning original text unchanged.")
                new_parts.append(part)
                continue

            has_a2ui = True

            # Preserve plain text preceding or succeeding the A2UI block, cleaning any residual tags
            cleaned_prefix = re.sub(r"</?(?:a2ui-json|a2a_datapart_json)>", "", plain_prefix).strip()
            cleaned_suffix = re.sub(r"</?(?:a2ui-json|a2a_datapart_json)>", "", plain_suffix).strip()
            full_plain = "\n\n".join(filter(None, [cleaned_prefix, cleaned_suffix])).strip()

            if full_plain:
                new_parts.append(types.Part(text=full_plain))

            # Add the wrapped A2UI parts
            for msg in a2ui_messages:
                new_parts.append(_wrap_a2ui_part(msg))

        if not has_a2ui:
            return llm_response

        # Safeguard: ensure we don't accidentally return empty parts
        if not new_parts:
            logger.warning("a2ui_callback constructed empty parts list; returning original llm_response.")
            return llm_response

        return LlmResponse(
            content=types.Content(role="model", parts=new_parts),
            custom_metadata={"a2a:response": "true"},
        )
    except Exception as exc:
        logger.error("Unexpected error in a2ui_callback: %s. Returning original response unchanged.", exc, exc_info=True)
        return llm_response

