"""Build system prompt for root_agent using A2uiSchemaManager and Basic Catalog v0.8."""

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from a2ui.schema.manager import A2uiSchemaManager
    from a2ui.basic_catalog.provider import BasicCatalog

# Initialize Schema Manager with version 0.8 and Basic Catalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

ROLE_DESCRIPTION = (
    "You are an Email Posture Scanner assistant for Managed Service Providers (MSPs). "
    "You evaluate email authentication posture (SPF, DKIM, DMARC, MTA-STS, MX) for domains, "
    "query DNS records, retrieve past scans from Firestore, and save scan results."
)

WORKFLOW_DESCRIPTION = (
    "When a user asks to scan a domain, use the scan_domain tool. "
    "When asked for past scans or a specific domain scan, use get_scan or list_scans. "
    "Present the output using A2UI components according to the UI guidelines."
)

UI_DESCRIPTION = (
    "CRITICAL UI REQUIREMENTS:\n"
    "1. When presenting a scan for a single domain: render a Card with domain, platform, score, and grade, "
    "followed by a findings Table with columns Check, Status, Value, Fix.\n"
    "   - In the Card: Show the grade LARGE at the very top of the card using a prominent heading with a colored circle emoji:\n"
    "     * '🟢 Grade A' or '🟢 Grade B' for grades A and B\n"
    "     * '🟡 Grade C' for grade C\n"
    "     * '🟠 Grade D' for grade D\n"
    "     * '🔴 Grade F' for grade F\n"
    "     Followed by domain, platform, and numeric score (e.g., 'Score: 95/100').\n"
    "   - In the findings Table: In the 'Status' column, you MUST use the following format:\n"
    "     * '✅ pass' for passing checks\n"
    "     * '⚠️ warn' for warning checks\n"
    "     * '❌ fail' for failing checks\n"
    "2. When multiple scans are requested or listed: render one Table with columns Domain, Platform, Score, Grade, DMARC policy. "
    "Use the grade emoji ('🟢 A', '🟢 B', '🟡 C', '🟠 D', '🔴 F') in the Grade column.\n"
    "3. Use Cards and Tables only. Do NOT render buttons, forms, text inputs, or interactive controls."
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    A2UI_SYSTEM_INSTRUCTION = schema_manager.generate_system_prompt(
        role_description=ROLE_DESCRIPTION,
        workflow_description=WORKFLOW_DESCRIPTION,
        ui_description=UI_DESCRIPTION,
        include_schema=True,
        include_examples=True,
    )
