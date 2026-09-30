"""Seed script for Firestore with plausible scan documents for google.com and example.com."""

from datetime import datetime, timezone
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-04-f25c6b05fda3"


def seed():
    db = firestore.Client(project=PROJECT_ID)
    scans_ref = db.collection("scans")

    # Document 1: google.com (High security posture, Grade A)
    google_doc = {
        "domain": "google.com",
        "platform": "Google Workspace",
        "score": 95,
        "grade": "A",
        "mx": [
            "smtp.google.com."
        ],
        "spf": "v=spf1 include:_spf.google.com ~all",
        "dkim_selectors_found": [
            "20230601",
            "google"
        ],
        "dmarc": "v=DMARC1; p=reject; rua=mailto:mailauth-reports@google.com",
        "dmarc_policy": "reject",
        "mta_sts": True,
        "findings": [
            {
                "check": "DMARC Policy",
                "status": "PASS",
                "value": "p=reject",
                "fix": "No action needed. Strict reject policy prevents unauthorized spoofing."
            },
            {
                "check": "SPF Record",
                "status": "PASS",
                "value": "~all with valid include",
                "fix": "No action needed. SPF aligns with Google Workspace mail servers."
            },
            {
                "check": "DKIM Key Presence",
                "status": "PASS",
                "value": "Active selectors found",
                "fix": "Ensure selector keys continue regular cryptographic rotation."
            },
            {
                "check": "MTA-STS Security",
                "status": "PASS",
                "value": "Enabled",
                "fix": "TLS enforcement active via MTA-STS policy."
            }
        ],
        "scanned_at": datetime.now(timezone.utc)
    }

    # Document 2: example.com (Low security posture, Grade D)
    example_doc = {
        "domain": "example.com",
        "platform": "Generic / Unhosted",
        "score": 30,
        "grade": "D",
        "mx": [
            "mail.example.com."
        ],
        "spf": "v=spf1 ?all",
        "dkim_selectors_found": [],
        "dmarc": "v=DMARC1; p=none; sp=none",
        "dmarc_policy": "none",
        "mta_sts": False,
        "findings": [
            {
                "check": "DMARC Policy",
                "status": "FAIL",
                "value": "p=none",
                "fix": "Upgrade policy from 'none' to 'quarantine' or 'reject' to block domain spoofing."
            },
            {
                "check": "SPF Qualifier",
                "status": "WARN",
                "value": "?all (neutral)",
                "fix": "Change neutral qualifier '?all' to softfail '~all' or hardfail '-all'."
            },
            {
                "check": "DKIM Key Presence",
                "status": "FAIL",
                "value": "No common selectors discovered",
                "fix": "Generate and publish DKIM 2048-bit TXT public keys on outgoing mail services."
            },
            {
                "check": "MTA-STS Policy",
                "status": "WARN",
                "value": "Not configured",
                "fix": "Publish _mta-sts TXT record and host HTTPS daemon policy to guarantee TLS transit."
            }
        ],
        "scanned_at": datetime.now(timezone.utc)
    }

    scans_ref.document("google.com").set(google_doc)
    print("Seeded google.com successfully.")
    scans_ref.document("example.com").set(example_doc)
    print("Seeded example.com successfully.")


if __name__ == "__main__":
    seed()
