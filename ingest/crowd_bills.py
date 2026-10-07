"""Resident bill submissions: aggregate counts and medians from the project's Google Apps
Script web app (crowd/apps-script). The endpoint returns only pending counts per ZIP code
and medians for ZIP codes with at least 10 valid bills in the past 12 months; individual
responses never leave the private Google Sheet."""
import json

from ingest.common import http_get, load_sources, snapshot

SOURCE_ID = "crowd_bills"


def run() -> bool:
    url = load_sources()[SOURCE_ID]["url"]
    if not url.startswith("https://script.google.com/macros/s/"):
        print("crowd_bills: endpoint not configured yet; skipping")
        return False
    data = http_get(url).json()
    data.pop("updated", None)  # changes every call; only content changes should count as new data
    content = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return snapshot(SOURCE_ID, content, "aggregates.json",
                    {"zips_pending": len(data.get("pending", [])), "zips_published": len(data.get("published", []))}) is not None
