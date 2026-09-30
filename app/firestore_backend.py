"""Firestore backend for Email Posture Scanner."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-04-f25c6b05fda3"


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    return firestore.Client(project=PROJECT_ID)


def get_scan(domain: str) -> Optional[Dict[str, Any]]:
    """Retrieve an email posture scan by domain.

    Args:
        domain: The domain name to look up.

    Returns:
        The scan document as a dictionary, or None if not found.
    """
    db = get_firestore_client()
    doc_ref = db.collection("scans").document(domain.lower().strip())
    doc = doc_ref.get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if data and "scanned_at" in data and isinstance(data["scanned_at"], datetime):
        data["scanned_at"] = data["scanned_at"].isoformat()
    return data


def list_scans() -> List[Dict[str, Any]]:
    """List all email posture scans in the database.

    Returns:
        A list of scan documents.
    """
    db = get_firestore_client()
    docs = db.collection("scans").order_by("scanned_at", direction=firestore.Query.DESCENDING).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        if data and "scanned_at" in data and isinstance(data["scanned_at"], datetime):
            data["scanned_at"] = data["scanned_at"].isoformat()
        results.append(data)
    return results


def save_scan(scan: Dict[str, Any]) -> Dict[str, Any]:
    """Save an email posture scan to Firestore.

    Args:
        scan: Dictionary containing scan fields: domain, platform, score,
              grade, mx, spf, dkim_selectors_found, dmarc, dmarc_policy,
              mta_sts, findings, scanned_at.

    Returns:
        The saved scan document.
    """
    db = get_firestore_client()
    domain = scan.get("domain", "").lower().strip()
    if not domain:
        raise ValueError("Field 'domain' is required to save a scan.")

    # Ensure scanned_at is a proper datetime or firestore timestamp
    scanned_at = scan.get("scanned_at")
    if scanned_at is None:
        scanned_at = datetime.now(timezone.utc)
    elif isinstance(scanned_at, str):
        try:
            scanned_at = datetime.fromisoformat(scanned_at.replace("Z", "+00:00"))
        except Exception:
            scanned_at = datetime.now(timezone.utc)

    doc_data = {
        "domain": domain,
        "platform": scan.get("platform", "Unknown"),
        "score": int(scan.get("score", 0)),
        "grade": str(scan.get("grade", "F")),
        "mx": list(scan.get("mx", [])),
        "spf": str(scan.get("spf", "")),
        "dkim_selectors_found": list(scan.get("dkim_selectors_found", [])),
        "dmarc": str(scan.get("dmarc", "")),
        "dmarc_policy": str(scan.get("dmarc_policy", "none")),
        "mta_sts": bool(scan.get("mta_sts", False)),
        "findings": list(scan.get("findings", [])),
        "scanned_at": scanned_at,
    }

    db.collection("scans").document(domain).set(doc_data)
    
    # Return formatted result
    return_data = dict(doc_data)
    if isinstance(return_data["scanned_at"], datetime):
        return_data["scanned_at"] = return_data["scanned_at"].isoformat()
    return return_data
