"""DNS over HTTPS (DoH) scanner and scoring engine for Email Posture Scanner."""

import re
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.firestore_backend import save_scan

DOH_URL = "https://dns.google/resolve"
DKIM_SELECTORS = ["selector1", "selector2", "google", "default", "s1", "s2"]


def query_doh(name: str, rtype: str, timeout: float = 5.0) -> List[str]:
    """Query Google's DNS-over-HTTPS JSON API for records of a given type.

    Args:
        name: Domain name or FQDN to query.
        rtype: Record type string (e.g. 'MX', 'TXT').
        timeout: Network timeout in seconds.

    Returns:
        List of data strings from Answer section, or empty list if NXDOMAIN / error / no answer.
    """
    params = urllib.parse.urlencode({"name": name.strip(), "type": rtype.strip()})
    url = f"{DOH_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/dns-json", "User-Agent": "EmailPostureScanner/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return []
            payload = json.loads(response.read().decode("utf-8"))
            # Status 0 = NOERROR, 3 = NXDOMAIN
            answers = payload.get("Answer", [])
            results = []
            for ans in answers:
                data = ans.get("data", "")
                if data:
                    # Clean surrounding quotes from TXT strings
                    cleaned = data.strip().strip('"')
                    # Some resolvers return multi-chunk strings like '"part1" "part2"'
                    if '""' in data or '" "' in data:
                        cleaned = "".join(part.strip('"') for part in re.findall(r'"([^"]*)"', data))
                    results.append(cleaned)
            return results
    except Exception:
        # Gracefully handle timeouts, network errors, NXDOMAIN without crashing
        return []


def detect_platform(mx_records: List[str]) -> str:
    """Detect email platform from MX records.

    outlook.com = Microsoft 365
    google.com or googlemail.com = Google Workspace
    pphosted.com = Proofpoint
    mimecast.com = Mimecast
    else Other
    """
    combined = " ".join(mx_records).lower()
    if "outlook.com" in combined:
        return "Microsoft 365"
    if "google.com" in combined or "googlemail.com" in combined:
        return "Google Workspace"
    if "pphosted.com" in combined:
        return "Proofpoint"
    if "mimecast.com" in combined:
        return "Mimecast"
    return "Other"


def calculate_score_and_findings(
    mx_records: List[str],
    spf_record: Optional[str],
    dkim_selectors_found: List[str],
    dmarc_record: Optional[str],
    dmarc_policy: Optional[str],
    mta_sts: bool
) -> Tuple[int, str, List[Dict[str, str]]]:
    """Calculate deterministic score out of 100, letter grade, and findings.

    Scoring rules:
      - MX present: 10
      - SPF present: 15
      - SPF qualifier: -all -> 10, ~all -> 7 (other qualifiers -> 0)
      - SPF terms: plus 10 if SPF has 10 or fewer include/a/mx/ptr/exists/redirect terms at top level
      - DKIM found: 20 (if at least one common selector found)
      - DMARC present: 15
      - DMARC policy: reject -> 15, quarantine -> 10, none -> 3
      - MTA-STS: 5

    Grades:
      A >= 90, B >= 80, C >= 65, D >= 50, F < 50
    """
    score = 0
    findings: List[Dict[str, str]] = []

    # 1. MX Check (10 pts)
    if mx_records:
        score += 10
        findings.append({
            "check": "MX Records",
            "status": "PASS",
            "value": f"{len(mx_records)} record(s) found",
            "fix": "No action needed. Inbound mail routing is operational."
        })
    else:
        findings.append({
            "check": "MX Records",
            "status": "FAIL",
            "value": "Missing",
            "fix": "Publish MX records pointing to your email provider."
        })

    # 2. SPF Check (15 pts present, 10 for -all or 7 for ~all, 10 for <=10 terms)
    if spf_record:
        score += 15
        
        # Check qualifier
        qualifier_match = re.search(r'([+\-~?])all', spf_record)
        qualifier = qualifier_match.group(0) if qualifier_match else "missing"
        if qualifier == "-all":
            score += 10
            findings.append({
                "check": "SPF Enforcement",
                "status": "PASS",
                "value": "-all (hardfail)",
                "fix": "No action needed. Hardfail provides strict sender authorization."
            })
        elif qualifier == "~all":
            score += 7
            findings.append({
                "check": "SPF Enforcement",
                "status": "PASS",
                "value": "~all (softfail)",
                "fix": "Consider graduating from softfail (~all) to hardfail (-all) once mail sources are verified."
            })
        else:
            findings.append({
                "check": "SPF Enforcement",
                "status": "WARN",
                "value": qualifier,
                "fix": "Change SPF default qualifier to '~all' or '-all' to reject unauthorized senders."
            })

        # Count top-level terms: include, a, mx, ptr, exists, redirect
        # Split SPF by whitespace
        tokens = spf_record.split()
        lookup_terms = [
            t for t in tokens[1:]
            if any(t.lower().startswith(prefix) for prefix in ["include:", "a", "mx", "ptr", "exists:", "redirect="])
        ]
        if len(lookup_terms) <= 10:
            score += 10
            findings.append({
                "check": "SPF Lookup Limit",
                "status": "PASS",
                "value": f"{len(lookup_terms)} top-level term(s)",
                "fix": "No action needed. Top-level SPF terms are within safe limits."
            })
        else:
            findings.append({
                "check": "SPF Lookup Limit",
                "status": "FAIL",
                "value": f"{len(lookup_terms)} top-level term(s)",
                "fix": "Flatten your SPF record to avoid exceeding the 10-lookup DNS evaluation limit."
            })
    else:
        findings.append({
            "check": "SPF Record",
            "status": "FAIL",
            "value": "Missing",
            "fix": "Add a TXT record beginning with 'v=spf1' defining authorized sending IPs."
        })

    # 3. DKIM Check (20 pts)
    if dkim_selectors_found:
        score += 20
        findings.append({
            "check": "DKIM Selectors",
            "status": "PASS",
            "value": f"Found: {', '.join(dkim_selectors_found)}",
            "fix": "No action needed. Active cryptographic signing keys detected."
        })
    else:
        findings.append({
            "check": "DKIM Selectors",
            "status": "FAIL",
            "value": "None found on common selectors",
            "fix": "Enable DKIM signing in your mail platform and publish public keys in DNS."
        })

    # 4. DMARC Check (15 pts present, 15 reject / 10 quarantine / 3 none)
    if dmarc_record:
        score += 15
        p = (dmarc_policy or "none").lower()
        if p == "reject":
            score += 15
            findings.append({
                "check": "DMARC Policy",
                "status": "PASS",
                "value": "p=reject",
                "fix": "No action needed. Strict reject policy prevents unauthorized spoofing."
            })
        elif p == "quarantine":
            score += 10
            findings.append({
                "check": "DMARC Policy",
                "status": "PASS",
                "value": "p=quarantine",
                "fix": "Graduate policy to 'p=reject' once legitimate sender reports confirm alignment."
            })
        elif p == "none":
            score += 3
            findings.append({
                "check": "DMARC Policy",
                "status": "WARN",
                "value": "p=none",
                "fix": "Upgrade policy from 'none' to 'quarantine' or 'reject' to block domain spoofing."
            })
        else:
            findings.append({
                "check": "DMARC Policy",
                "status": "WARN",
                "value": f"p={p}",
                "fix": "Ensure policy tag is set to 'reject' or 'quarantine'."
            })
    else:
        findings.append({
            "check": "DMARC Record",
            "status": "FAIL",
            "value": "Missing",
            "fix": "Publish a TXT record at _dmarc.<domain> with at least 'v=DMARC1; p=quarantine'."
        })

    # 5. MTA-STS Check (5 pts)
    if mta_sts:
        score += 5
        findings.append({
            "check": "MTA-STS",
            "status": "PASS",
            "value": "Present",
            "fix": "No action needed. Strict transport security policy enabled."
        })
    else:
        findings.append({
            "check": "MTA-STS",
            "status": "WARN",
            "value": "Missing",
            "fix": "Configure MTA-STS by publishing a TXT record at _mta-sts.<domain>."
        })

    # Calculate Grade
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 65:
        grade = "C"
    elif score >= 50:
        grade = "D"
    else:
        grade = "F"

    return score, grade, findings


def scan_domain(domain: str) -> Dict[str, Any]:
    """Scans domain email posture via DNS over HTTPS, scores it, and saves to Firestore.

    Args:
        domain: The domain name to inspect (e.g. 'google.com').

    Returns:
        The evaluated scan document dictionary stored in Firestore.
    """
    clean_domain = domain.lower().strip()
    if clean_domain.startswith("http://") or clean_domain.startswith("https://"):
        clean_domain = urllib.parse.urlparse(clean_domain).netloc

    # 1. Query MX records
    mx_answers = query_doh(clean_domain, "MX")
    mx_list = [ans for ans in mx_answers if ans]
    platform = detect_platform(mx_list)

    # 2. Query root TXT for SPF (v=spf1)
    txt_answers = query_doh(clean_domain, "TXT")
    spf_record = None
    for txt in txt_answers:
        if txt.lower().startswith("v=spf1"):
            spf_record = txt
            break

    # 3. Query common DKIM selectors at <selector>._domainkey.<domain>
    dkim_selectors_found = []
    for sel in DKIM_SELECTORS:
        dkim_fqdn = f"{sel}._domainkey.{clean_domain}"
        dkim_answers = query_doh(dkim_fqdn, "TXT")
        if dkim_answers:
            # Check if any record looks like DKIM (v=DKIM1 or p=...)
            if any("p=" in ans or "v=dkim1" in ans.lower() for ans in dkim_answers):
                dkim_selectors_found.append(sel)

    # 4. Query DMARC at _dmarc.<domain>
    dmarc_fqdn = f"_dmarc.{clean_domain}"
    dmarc_answers = query_doh(dmarc_fqdn, "TXT")
    dmarc_record = None
    dmarc_policy = None
    for ans in dmarc_answers:
        if "v=dmarc1" in ans.lower():
            dmarc_record = ans
            policy_match = re.search(r'\bp\s*=\s*([a-zA-Z]+)', ans, re.IGNORECASE)
            if policy_match:
                dmarc_policy = policy_match.group(1).lower()
            break

    # 5. Query MTA-STS at _mta-sts.<domain>
    mta_sts_fqdn = f"_mta-sts.{clean_domain}"
    mta_sts_answers = query_doh(mta_sts_fqdn, "TXT")
    mta_sts = False
    for ans in mta_sts_answers:
        if "v=stsv1" in ans.lower() or "id=" in ans.lower():
            mta_sts = True
            break

    # 6. Deterministic scoring and findings
    score, grade, findings = calculate_score_and_findings(
        mx_records=mx_list,
        spf_record=spf_record,
        dkim_selectors_found=dkim_selectors_found,
        dmarc_record=dmarc_record,
        dmarc_policy=dmarc_policy,
        mta_sts=mta_sts
    )

    scan_doc = {
        "domain": clean_domain,
        "platform": platform,
        "score": score,
        "grade": grade,
        "mx": mx_list,
        "spf": spf_record or "",
        "dkim_selectors_found": dkim_selectors_found,
        "dmarc": dmarc_record or "",
        "dmarc_policy": dmarc_policy or "none",
        "mta_sts": mta_sts,
        "findings": findings,
        "scanned_at": datetime.now(timezone.utc).isoformat()
    }

    # Save to Firestore
    saved_doc = save_scan(scan_doc)
    return saved_doc
