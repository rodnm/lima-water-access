"""Diagnose connectivity to Overpass API endpoints.

Tests the 3 endpoints used by src/lima_water/osm.py with:
    1. A trivial HEAD/GET to check reachability
    2. A small POST query that returns a handful of features

Prints a summary table so we can decide whether to retry, switch endpoint,
or fall back to a Geofabrik PBF extract.
"""
from __future__ import annotations

import sys
import time

import requests

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Trivial query: drinking water amenities within 500m of central Lima
TEST_QUERY = (
    "[out:json][timeout:25];"
    "node[amenity=drinking_water](around:500,-12.046,-77.043);"
    "out;"
)


def test_endpoint(url: str, timeout: int = 30) -> dict:
    result = {"url": url, "reachable": False, "ok": False, "elapsed_s": None,
              "elements": None, "error": None}
    t0 = time.time()
    try:
        resp = requests.post(url, data={"data": TEST_QUERY}, timeout=timeout)
        result["elapsed_s"] = round(time.time() - t0, 2)
        result["reachable"] = True
        if resp.status_code == 200:
            data = resp.json()
            result["ok"] = True
            result["elements"] = len(data.get("elements", []))
        else:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:120]}"
    except requests.exceptions.Timeout:
        result["elapsed_s"] = round(time.time() - t0, 2)
        result["error"] = f"timeout after {timeout}s"
    except Exception as exc:
        result["elapsed_s"] = round(time.time() - t0, 2)
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    print("Diagnosing Overpass API endpoints...\n")
    results = [test_endpoint(url) for url in ENDPOINTS]

    print(f"{'Endpoint':<55} {'Status':<8} {'Time(s)':<10} {'Elements':<10} {'Error'}")
    print("-" * 110)
    for r in results:
        status = "OK" if r["ok"] else ("REACH" if r["reachable"] else "FAIL")
        time_s = str(r["elapsed_s"]) if r["elapsed_s"] is not None else "-"
        elements = str(r["elements"]) if r["elements"] is not None else "-"
        error = r["error"] or ""
        # Compact the URL display
        display_url = r["url"].replace("https://", "").replace("/api/interpreter", "/api")
        print(f"{display_url:<55} {status:<8} {time_s:<10} {elements:<10} {error}")

    print()
    working = [r for r in results if r["ok"]]
    if working:
        fastest = min(working, key=lambda r: r["elapsed_s"])
        print(f"Recommended endpoint: {fastest['url']} ({fastest['elapsed_s']}s)")
        return 0
    else:
        print("All endpoints failed. Fall back to Geofabrik PBF (Plan B).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
