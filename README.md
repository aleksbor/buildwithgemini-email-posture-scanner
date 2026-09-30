# Email Posture Scanner

![Playground Demo](./demo.gif)

An agentic security tool built for Managed Service Providers (MSPs) to audit, score, and monitor email authentication postures across client and prospect domains.

The agent queries public DNS-over-HTTPS endpoints (requiring zero API keys or private client credentials), analyzes core email authentication protocols (MX, SPF, DKIM, DMARC, and MTA-STS), detects mail platform providers, computes a deterministic posture score and grade, and persists all scan history directly into Google Cloud Firestore. Scan outcomes are rendered natively via the Agent-to-UI (A2UI) protocol as structured cards and findings tables.

---

## What the Agent Actually Does

Based on the implemented code in `app/` and `agents-cli-manifest.yaml`, the agent is powered by Google ADK with the `gemini-3.6-flash` model and executes the following capabilities:

### Wired Tools
* **`scan_domain(domain)`**:
  * Resolves public DNS records using Google's DNS-over-HTTPS JSON API (`https://dns.google/resolve`).
  * Fetches **MX** records and classifies the mail platform (`Microsoft 365`, `Google Workspace`, `Proofpoint`, `Mimecast`, or `Other`).
  * Extracts root **SPF** (`v=spf1`) TXT records, inspects policy enforcement (`-all`, `~all`, or misconfigurations), and verifies top-level SPF include/a/mx/ptr/exists/redirect term count limits.
  * Checks common **DKIM** selectors (`selector1`, `selector2`, `google`, `default`, `s1`, `s2`) under `<selector>._domainkey.<domain>`.
  * Analyzes **DMARC** policy (`_dmarc.<domain>`) and parses policy enforcement (`p=reject`, `p=quarantine`, `p=none`).
  * Validates **MTA-STS** (`_mta-sts.<domain>`) configuration.
  * Calculates a deterministic posture score (0–100) and assigns an academic grade (`A` >= 90, `B` >= 80, `C` >= 65, `D` >= 50, `F` < 50).
  * Compiles actionable findings with checks, statuses (`PASS`, `WARN`, `FAIL`), observed values, and one-sentence remediation fixes.
  * Automatically saves the resulting scan to Firestore via `save_scan`.
* **`query_doh(name, rtype)`**: Directly performs public DNS-over-HTTPS JSON lookups against Google's public DoH resolver without authentication.
* **`get_scan(domain)`**: Retrieves an existing scan document for a given domain from the Firestore `scans` collection.
* **`list_scans()`**: Lists all stored domain scans from the Firestore `scans` collection.
* **`save_scan(scan)`**: Upserts scan details and findings into the Firestore `scans` collection keyed by domain.

### Wired Google Cloud Services
* **Google Cloud Firestore**:
  * Native mode database storing domain assessment documents in the `scans` collection with fields: `domain`, `platform`, `score`, `grade`, `mx`, `spf`, `dkim_selectors_found`, `dmarc`, `dmarc_policy`, `mta_sts`, `findings`, and `scanned_at`.

### User Interface (A2UI v0.8)
* Configured using `A2uiSchemaManager` with the Basic Catalog and connected via `after_model_callback` (`a2ui_callback`).
* **Single Domain Scan**: Rendered as a summary **Card** (Domain, Platform, Score, Grade) followed by a detailed findings **Table** (`Check`, `Status`, `Value`, `Fix`).
* **Multiple Scans / History**: Rendered as a single summary **Table** (`Domain`, `Platform`, `Score`, `Grade`, `DMARC policy`).
* Pure declarative cards and tables (no buttons or forms).

---

## Setup & Running Locally

### Prerequisites
* Python 3.11+
* Google Cloud SDK (`gcloud`) authenticated to a GCP project with Firestore enabled.
* `uv` package manager installed.

### 1. Install Dependencies
```bash
uv pip install -e .
```

### 2. Configure Environment & Project
Ensure your Google Cloud credentials and project are active:
```bash
gcloud auth application-default login
gcloud config set project <YOUR_PROJECT_ID>
```

### 3. Run the Agent via CLI
Execute one-off scans or queries from your terminal:
```bash
# Scan a domain
agents-cli run "Scan example.com"

# Query scan history
agents-cli run "Show all scans in a table"
```

### 4. Run the Agent in Playground
Launch the interactive web-based ADK development playground:
```bash
agents-cli playground --port 8080 --host 127.0.0.1
```
Access the UI in your web browser by navigating to:
```text
http://127.0.0.1:8080/dev-ui/?app=app
```

---

## Backlog - Future Improvements

*(Planned items from project brief — not yet implemented)*

* **Badge Image Generation with Cloud Storage**: Generating dynamic SVG/PNG status badges hosted on Google Cloud Storage for client reports and marketing embeds.
* **Sandbox SPF Include-Tree Lookup Counting**: Full recursive SPF include-tree expansion and evaluation to verify RFC 10-lookup DNS limits within a sandbox environment.
* **Memory Bank**: Persistent personalization for preferred tenant DKIM selectors, custom MSP discovery rules, and tailored client pitch/report phrasing styles.
* **Cloud Run Frontend**: Standalone web UI application deployed on Google Cloud Run for client-facing self-service scans.
* **Agent Platform Redeployment**: Production redeployments and CI/CD pipelines targeting the enterprise Agent Platform runtime.
