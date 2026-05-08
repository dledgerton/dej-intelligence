"""
Validate the BMF load against known DEJ Search orgs.

Reads scripts/validation/known_orgs.json, queries Supabase for each EIN,
and reports any mismatches against expected values. This is the QA gate
that decides whether we trust the loader before shipping Phase 2.

Run:
    python scripts/validation/validate_load.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[2]
KNOWN_ORGS_PATH = ROOT / "scripts" / "validation" / "known_orgs.json"


def main() -> None:
    load_dotenv(ROOT / ".env.local")
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env.local")
    supabase = create_client(url, key)

    with open(KNOWN_ORGS_PATH) as f:
        config = json.load(f)

    orgs = [o for o in config.get("orgs", []) if o.get("ein") != "REPLACE_ME"]
    if not orgs:
        sys.exit("No validation orgs configured. Edit scripts/validation/known_orgs.json first.")

    print(f"Validating {len(orgs)} known orgs against the loaded BMF data...\n")

    total = len(orgs)
    found = 0
    mismatches: list[str] = []

    for org in orgs:
        ein = str(org["ein"]).zfill(9)
        result = supabase.table("organizations").select("*").eq("ein", ein).maybe_single().execute()
        loaded = result.data if result else None

        if not loaded:
            mismatches.append(f"  ✗ {ein} ({org.get('name', '?')}): NOT FOUND in DB")
            continue

        found += 1
        problems: list[str] = []

        if "expected_state" in org and loaded.get("state") != org["expected_state"]:
            problems.append(f"state expected {org['expected_state']!r}, got {loaded.get('state')!r}")

        if "expected_subsection" in org and loaded.get("subsection_code") != org["expected_subsection"]:
            problems.append(f"subsection expected {org['expected_subsection']}, got {loaded.get('subsection_code')}")

        if "expected_ntee_major" in org:
            ntee = (loaded.get("ntee_code") or "")[:1]
            if ntee != org["expected_ntee_major"]:
                problems.append(f"NTEE major expected {org['expected_ntee_major']!r}, got {ntee!r}")

        if problems:
            mismatches.append(f"  ⚠ {ein} ({loaded.get('name')}): " + "; ".join(problems))
        else:
            print(f"  ✓ {ein}  {loaded.get('name')}")

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"  Found in DB:   {found}/{total}")
    print(f"  Mismatches:    {len(mismatches)}")
    if mismatches:
        print()
        for m in mismatches:
            print(m)
        sys.exit(1)
    print("\n  All checks passed. BMF data is trustworthy.")


if __name__ == "__main__":
    main()
