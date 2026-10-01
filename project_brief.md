# Project Brief: Email Posture Scanner for MSPs

## Overview
The Email Posture Scanner is an agentic application tailored for Managed Service Providers (MSPs). Given a customer or prospective domain, the agent evaluates email authentication posture by querying public DNS over HTTPS (DoH, requiring no external API keys), identifies the underlying mail platform from MX records, calculates an overall security posture score, and persists scan results into a Google Cloud Firestore collection. The results are rendered interactively for operators using A2UI scorecard components and structured findings tables.

---

## Today's Scope

### 1. DNS Scan Tool & Scoring Engine
- **DNS over HTTPS (DoH) Client**:
  - Leverages public DoH resolvers (e.g., Google or Cloudflare DoH endpoints) requiring zero API keys or authenticated client credentials.
  - Queries records for:
    - **MX**: Mail exchange records and priority list.
    - **SPF**: `v=spf1` TXT records on the root domain.
    - **DKIM**: Common/standard selectors (e.g., `google`, `selector1`, `default`, `k1`, `s1`, `mandrill`, `mailo`, `dkim`).
    - **DMARC**: `_dmarc.<domain>` TXT record analysis (`p=none`, `p=quarantine`, `p=reject`, pct, rua tags).
    - **MTA-STS**: `_mta-sts.<domain>` TXT record and policy presence check.
- **Mail Platform Detection**:
  - Identifies host platform based on MX record patterns (e.g., Google Workspace, Microsoft 365, Proofpoint, Mimecast, etc.).
- **Posture Scoring**:
  - Evaluates authentication configurations and computes a weighted posture score (e.g., 0–100 scale) based on:
    - DMARC enforcement policy (`reject` vs `quarantine` vs `none` vs absent).
    - SPF syntax, validity, and strictness (`~all`, `-all`, or misconfigured `+all`/missing).
    - DKIM key presence on common selectors.
    - MTA-STS policy adoption.

### 2. Firestore Persistence
- **Collection**: Stores scan runs under a dedicated `scans` collection in Firestore.
- **Document Structure**:
  - `domain`: String (target domain scanned).
  - `timestamp`: Timestamp of scan.
  - `mailPlatform`: Detected mail provider.
  - `overallScore`: Computed numeric score and rating band.
  - `records`: Raw/parsed DNS records (MX, SPF, DKIM, DMARC, MTA-STS).
  - `findings`: Array of identified risks, misconfigurations, and recommendations.

### 3. A2UI Presentation
- **Scorecard Cards**:
  - Top-level visual summary highlighting Domain, Detected Platform, Overall Posture Score, and Status Badge (e.g., Secure, Warning, At Risk).
- **Findings Tables**:
  - Tabular breakdown of each protocol (MX, SPF, DKIM, DMARC, MTA-STS).
  - Displays record contents, configuration status, risk impact, and recommended MSP remediation steps.

### 4. Privacy & Security Constraints
- Exclusively queries publicly accessible DNS records.
- No client credentials, user authentication secrets, or private data accessed or stored.

---

## Backlog - Future Improvements
The following items are deferred from today's scope and scheduled for subsequent iterations:

1. **Badge Image Generation with Cloud Storage**: Generating dynamic SVG/PNG status badges hosted on Google Cloud Storage for client reports and marketing embeds.
2. **Sandbox SPF Include-Tree Lookup Counting**: Full recursive SPF include-tree expansion and evaluation to verify RFC 10-lookup DNS limits within a sandbox environment.
3. **Memory Bank**: Persistent personalization for preferred tenant DKIM selectors, custom MSP discovery rules, and tailored client pitch/report phrasing styles.
4. **Cloud Run Frontend**: Standalone web UI application deployed on Google Cloud Run for client-facing self-service scans.
5. **Agent Platform Redeployment**: Production redeployments and CI/CD pipelines targeting the enterprise Agent Platform runtime.
6. **Fix A2UI card rendering in ADK dev UI**: Refine A2UI component rendering and data part encapsulation for ADK dev UI.
