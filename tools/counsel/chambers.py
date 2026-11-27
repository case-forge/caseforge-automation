#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from caseforge_cli.chambers_finder import DATA_ENV_VAR, finder_data_path

DATA_FILE: Path | None = None

POSTCODES_IO_BASE_URL = os.getenv("CASEFORGE_POSTCODES_IO_BASE_URL", "https://api.postcodes.io").rstrip("/")
POSTCODES_IO_TIMEOUT_SECONDS = float(os.getenv("CASEFORGE_POSTCODES_IO_TIMEOUT", "8"))


def _load() -> dict:
    data_file = DATA_FILE or finder_data_path()
    if not data_file.exists():
        sys.exit(
            f"Chambers dataset not found at {data_file}. Provision the chambers-finder checkout "
            f"(Ansible role caseforge_cli_tools) or set {DATA_ENV_VAR}."
        )
    with open(data_file, encoding="utf-8") as f:
        return json.load(f)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


_GENERIC_COURT_WORDS = frozenset({
    "the", "a", "an", "and", "at", "of", "in", "family", "court", "courts", "magistrates", "magistrate", "county",
    "combined", "crown", "hearing", "centre", "center", "justice", "civil", "great", "high", "district", "registry",
})


def _place_words(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z]+", str(text or "").lower().replace("'", ""))
    return frozenset(w for w in words if w not in _GENERIC_COURT_WORDS)


def court_for_name(courts: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    text = str(name or "")
    if not text.strip() or "[" in text:
        return None
    wanted = _place_words(text)
    if not wanted:
        return None
    hits = [
        court for court in courts
        if court.get("lat") is not None and court.get("lon") is not None
        and wanted in {_place_words(court.get("name")), _place_words(court.get("location")), *(_place_words(a) for a in court.get("aliases") or [])}
    ]
    return hits[0] if len(hits) == 1 else None


def chambers_near_court(data: dict[str, Any], court: dict[str, Any], *, count: int = 10) -> list[dict[str, Any]]:
    best: dict[str, tuple[float, dict[str, Any], dict[str, Any]]] = {}
    for chambers in data.get("chambers") or []:
        for branch in chambers.get("branches") or []:
            if branch.get("lat") is None or branch.get("lon") is None:
                continue
            miles = _haversine(court["lat"], court["lon"], branch["lat"], branch["lon"])
            key = str(chambers.get("id") or chambers.get("name") or "")
            if key not in best or miles < best[key][0]:
                best[key] = (miles, chambers, branch)
    rows = sorted(best.values(), key=lambda row: row[0])
    return [
        {"name": c.get("name") or "", "email": c.get("email") or "", "distance_miles": round(miles, 1), "branch": b.get("name") or ""}
        for miles, c, b in rows[: max(1, count)]
    ]


def geocode_postcode(postcode: str) -> dict[str, Any]:
    clean = "".join(str(postcode or "").split())
    if not clean:
        return {"ok": False, "message": "Enter a UK postcode."}
    try:
        response = requests.get(
            f"{POSTCODES_IO_BASE_URL}/postcodes/{clean}",
            headers={"Accept": "application/json"},
            timeout=POSTCODES_IO_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return {"ok": False, "message": f"Postcode lookup service unavailable: {exc}"}
    if response.status_code == 404:
        return {"ok": False, "message": f"'{postcode}' is not a recognised UK postcode."}
    try:
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "message": f"Postcode lookup service returned an unexpected response: {exc}"}
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or result.get("latitude") is None or result.get("longitude") is None:
        return {"ok": False, "message": f"No coordinates returned for '{postcode}'."}
    return {"ok": True, "lat": float(result["latitude"]), "lon": float(result["longitude"])}


def find_nearest_chambers(lat: float, lon: float, *, count: int = 5) -> list[dict[str, Any]]:
    data = _load()
    results: list[tuple[float, dict, dict]] = []
    for c in data["chambers"]:
        for branch in c.get("branches", []):
            if branch.get("lat") is not None and branch.get("lon") is not None:
                dist = _haversine(lat, lon, branch["lat"], branch["lon"])
                results.append((dist, c, branch))
    results.sort(key=lambda x: x[0])
    return [
        {"distance_miles": dist, "chambers": c, "branch": branch}
        for dist, c, branch in results[: max(1, count)]
    ]


def find_nearest_chambers_by_postcode(postcode: str, *, count: int = 5) -> dict[str, Any]:
    geocoded = geocode_postcode(postcode)
    if not geocoded.get("ok"):
        return geocoded
    nearest = find_nearest_chambers(geocoded["lat"], geocoded["lon"], count=count)
    return {"ok": True, "postcode": postcode, "nearest_chambers": nearest}


def _format_chamber(c: dict, branch: dict | None = None, distance_mi: float | None = None) -> str:
    lines = [f"  {c['name']}"]
    if branch:
        lines[0] += f" — {branch['name']}"
    if distance_mi is not None:
        lines[0] += f"  ({distance_mi:.1f} mi)"
    if c.get("email"):
        lines.append(f"    Email:   {c['email']}")
    if branch and branch.get("phone"):
        lines.append(f"    Phone:   {branch['phone']}")
    elif c.get("phone"):
        lines.append(f"    Phone:   {c['phone']}")
    if c.get("website"):
        lines.append(f"    Website: {c['website']}")
    if c.get("notes"):
        for note in c["notes"]:
            if note:
                lines.append(f"    Note:    {note}")
    return "\n".join(lines)


def cmd_list(data: dict) -> None:
    print(f"Chambers ({len(data['chambers'])} total):\n")
    for c in sorted(data["chambers"], key=lambda x: x["name"]):
        branches = ", ".join(b["name"] for b in c.get("branches", []))
        print(f"  {c['name']:<45} {c.get('email','')}")
        if branches:
            print(f"    branches: {branches}")
    print(f"\nCourts in dataset: {len(data['courts'])}")


def find_chambers_by_name(query: str) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return []
    data = _load()
    return [
        {
            "name": c["name"],
            "email": c.get("email", ""),
            "phone": c.get("phone", ""),
            "website": c.get("website", ""),
            "aliases": list(c.get("aliases", [])),
        }
        for c in data["chambers"]
        if q in c["name"].lower() or any(q in a.lower() for a in c.get("aliases", []))
    ]


def find_chambers_by_domain(domain: str) -> list[dict[str, Any]]:
    d = (domain or "").strip().lower().lstrip("@")
    if not d:
        return []
    rows = []
    for c in _load()["chambers"]:
        host = str(c.get("email") or "").rpartition("@")[2].strip().lower()
        if host and (host == d or d.endswith("." + host)):
            rows.append({
                "name": c["name"], "email": c.get("email", ""), "phone": c.get("phone", ""),
                "website": c.get("website", ""), "aliases": list(c.get("aliases", [])),
            })
    return rows


def cmd_name(data: dict, query: str) -> None:
    q = query.lower()
    hits = [
        c for c in data["chambers"]
        if q in c["name"].lower()
        or any(q in a.lower() for a in c.get("aliases", []))
    ]
    if not hits:
        print(f"No chambers matching '{query}'")
        return
    for c in hits:
        print(_format_chamber(c))
        print()


def cmd_court(data: dict, court_name: str, radius_mi: float = 30.0) -> None:
    q = court_name.lower()
    court = next(
        (ct for ct in data["courts"]
         if q in ct["name"].lower()
         or any(q in a.lower() for a in ct.get("aliases", []))),
        None
    )
    if not court:
        print(f"Court not found: '{court_name}'")
        print("Nearby courts:", [ct["name"] for ct in data["courts"] if q[:4] in ct["name"].lower()][:5])
        return

    print(f"Court: {court['name']} ({court['location']})\n")

    results: list[tuple[float, dict, dict]] = []
    for c in data["chambers"]:
        for branch in c.get("branches", []):
            if branch.get("lat") and branch.get("lon"):
                dist = _haversine(court["lat"], court["lon"], branch["lat"], branch["lon"])
                if dist <= radius_mi:
                    results.append((dist, c, branch))

    if not results:
        print(f"No chambers within {radius_mi} miles.")
        return

    results.sort(key=lambda x: x[0])
    print(f"Chambers within {radius_mi} miles ({len(results)} found):\n")
    for dist, c, branch in results:
        print(_format_chamber(c, branch, dist))
        print()


def cmd_postcode(postcode: str, count: int) -> None:
    result = find_nearest_chambers_by_postcode(postcode, count=count)
    if not result.get("ok"):
        print(result.get("message", "Lookup failed."))
        return
    nearest = result["nearest_chambers"]
    print(f"Nearest {len(nearest)} chambers to {postcode}:\n")
    for row in nearest:
        print(_format_chamber(row["chambers"], row["branch"], row["distance_miles"]))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chambers lookup from chambers-finder's finder-data.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list",     action="store_true", help="List all chambers")
    group.add_argument("--name",     metavar="QUERY",     help="Search by chambers name or alias")
    group.add_argument("--court",    metavar="COURT",     help="Find chambers near a court")
    group.add_argument("--postcode", metavar="POSTCODE",  help="Find chambers nearest a UK postcode (geocoded via postcodes.io)")
    parser.add_argument("--radius", type=float, default=30.0, help="Radius in miles for --court (default: 30)")
    parser.add_argument("--count", type=int, default=5, help="Number of nearest chambers to return for --postcode (default: 5)")
    args = parser.parse_args()

    if args.postcode:
        cmd_postcode(args.postcode, args.count)
        return

    data = _load()

    if args.list:
        cmd_list(data)
    elif args.name:
        cmd_name(data, args.name)
    elif args.court:
        cmd_court(data, args.court, args.radius)


if __name__ == "__main__":
    main()
