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


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=SCANNER_INSTRUCTION,
    tools=[scan_domain, query_doh, get_scan, list_scans, save_scan],
)

app = App(
    root_agent=root_agent,
    name="app",
)
