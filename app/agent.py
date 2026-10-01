# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types


MODEL = "gemini-3.6-flash"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


from app.firestore_backend import get_scan, list_scans, save_scan
from app.dns_scanner import query_doh, scan_domain


SCANNER_INSTRUCTION = (
    "You are an Email Posture Scanner assistant for Managed Service Providers (MSPs). "
    "You evaluate email authentication posture (SPF, DKIM, DMARC, MTA-STS, MX) for domains, "
    "query DNS records via DNS-over-HTTPS, retrieve past scans from Firestore, and save scan results.\n\n"
    "Formatting Guidelines:\n"
    "1. After executing scan_domain, reply in clean markdown:\n"
    "   - A heading with the domain and a colored grade emoji:\n"
    "     * 🟢 for Grade A or B (e.g., '# Domain: example.com 🟢 Grade A')\n"
    "     * 🟡 for Grade C (e.g., '# Domain: example.com 🟡 Grade C')\n"
    "     * 🟠 for Grade D (e.g., '# Domain: example.com 🟠 Grade D')\n"
    "     * 🔴 for Grade F (e.g., '# Domain: example.com 🔴 Grade F')\n"
    "   - A line with platform and score: 'Platform: <platform> | Score: <score>/100'\n"
    "   - A findings table with columns: Check | Status | Value | Fix\n"
    "     In the Status column, use:\n"
    "     * ✅ pass\n"
    "     * ⚠️ warn\n"
    "     * ❌ fail\n\n"
    "2. For 'show all scans' or when listing scans (list_scans), reply with one markdown table with columns:\n"
    "   Domain | Platform | Score | Grade | DMARC policy\n"
    "   Use the grade emojis in the Grade column (e.g., 🟢 A, 🟢 B, 🟡 C, 🟠 D, 🔴 F).\n\n"
    "Always provide a helpful and complete markdown response after tool execution."
)


import io
import os
from PIL import Image
from google import genai
from google.cloud import storage
from google.adk.tools import ToolContext

COLOR_MAP = {
    "A": "green",
    "B": "teal",
    "C": "amber",
    "D": "orange",
    "F": "red",
}


async def generate_badge(domain: str, grade: str, tool_context: ToolContext = None) -> str:
    """Generate a clean, flat shield-style badge image for an email posture grade.

    Args:
        domain: The domain name scanned (e.g. 'example.com').
        grade: The letter grade received ('A', 'B', 'C', 'D', 'F').

    Returns:
        The public HTTPS URL of the uploaded badge image.
    """
    domain_clean = domain.lower().strip()
    grade_clean = grade.strip().upper()
    if len(grade_clean) > 1 and grade_clean.startswith("GRADE "):
        grade_letter = grade_clean.split()[-1]
    else:
        grade_letter = grade_clean[:1] if grade_clean else "F"
    if grade_letter not in COLOR_MAP:
        grade_letter = "F"
    color = COLOR_MAP.get(grade_letter, "red")

    prompt = (
        f"A clean, flat shield-style badge with a solid {color} background and the single letter {grade_letter}. "
        f"Minimalist vector graphic style, centered single letter {grade_letter}, no other text, no shadows, modern flat design."
    )

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-f25c6b05fda3")
    client = genai.Client(vertexai=True, project=project_id, location="global")
    resp = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    raw_bytes = resp.candidates[0].content.parts[0].inline_data.data
    img = Image.open(io.BytesIO(raw_bytes))
    out = io.BytesIO()
    img.save(out, format="PNG")
    png_bytes = out.getvalue()

    filename = f"{domain_clean}.png"
    if tool_context and hasattr(tool_context, "save_artifact"):
        part = types.Part.from_bytes(data=png_bytes, mime_type="image/png")
        await tool_context.save_artifact(filename=filename, artifact=part)

    bucket_name = "email-posture-badges-17c8d5"
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    blob_path = f"badges/{domain_clean}.png"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(png_bytes, content_type="image/png")

    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_path}"

    # Update Firestore scan document
    from app.firestore_backend import get_firestore_client
    db = get_firestore_client()
    doc_ref = db.collection("scans").document(domain_clean)
    if doc_ref.get().exists:
        doc_ref.update({"badge_url": public_url})

    return public_url


from app.prompt_builder import A2UI_SYSTEM_INSTRUCTION
from app.a2ui_utils import a2ui_callback


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=A2UI_SYSTEM_INSTRUCTION,
    after_model_callback=a2ui_callback,
    tools=[scan_domain, generate_badge, query_doh, get_scan, list_scans, save_scan],
)

app = App(
    root_agent=root_agent,
    name="app",
)

