"""
IRS Business Master File loader for DEJ Intelligence.

Pulls the four regional Exempt Organization (EO) BMF files from the IRS,
filters to target geographies and subsection codes, maps fields to the
`organizations` table schema, and upserts in batches to Supabase.

Run:
    python scripts/loaders/load_bmf.py            # full load (default)
    python scripts/loaders/load_bmf.py --dry-run  # parse + count, no DB writes
    python scripts/loaders/load_bmf.py --limit 1000  # test with 1000 rows

Source: https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
from pathlib import Path
from typing import Iterator

import httpx
from dotenv import load_dotenv
from supabase import Client, create_client

# --- Config ---------------------------------------------------------------

# IRS publishes four regional BMF files. URLs are stable.
BMF_REGIONS = {
    "eo1": "https://www.irs.gov/pub/irs-soi/eo1.csv",  # Northeast
    "eo2": "https://www.irs.gov/pub/irs-soi/eo2.csv",  # Mid-Atlantic + Great Lakes
    "eo3": "https://www.irs.gov/pub/irs-soi/eo3.csv",  # South + Southeast
    "eo4": "https://www.irs.gov/pub/irs-soi/eo4.csv",  # West
}

# Target states: DMV practice + Minnesota + NY (national HQ density)
TARGET_STATES = {"DC", "MD", "VA", "MN", "NY"}

# Target subsection codes:
#   3  = 501(c)(3) — public charities and private foundations
#   6  = 501(c)(6) — business leagues, associations, chambers
TARGET_SUBSECTIONS = {3, 6}

BATCH_SIZE = 1000  # rows per Supabase upsert call

# --- Field mapping --------------------------------------------------------

# IRS BMF column headers (these are the actual column names in the CSV).
# Reference: IRS publishes a data dictionary; these are stable across years.
BMF_COLUMNS = {
    "EIN": "ein",
    "NAME": "name",
    "ICO": "in_care_of",          # "in care of" — useful for fiscal sponsors
    "STREET": "street",
    "CITY": "city",
    "STATE": "state",
    "ZIP": "zip",
    "GROUP": "group_exemption",
    "SUBSECTION": "subsection_code",
    "AFFILIATION": "affiliation",
    "CLASSIFICATION": "classification",
    "RULING": "ruling_date",       # YYYYMM
    "DEDUCTIBILITY": "deductibility",
    "FOUNDATION": "foundation_code",
    "ACTIVITY": "activity_codes",
    "ORGANIZATION": "organization_code",
    "STATUS": "status_code",
    "TAX_PERIOD": "tax_period",
    "ASSET_CD": "asset_code",
    "INCOME_CD": "income_code",
    "FILING_REQ_CD": "filing_req_code",
    "PF_FILING_REQ_CD": "pf_filing_req_code",
    "ACCT_PD": "accounting_period",  # MM — fiscal year end month
    "ASSET_AMT": "asset_amount",
    "INCOME_AMT": "income_amount",
    "REVENUE_AMT": "revenue_amount",
    "NTEE_CD": "ntee_code",
    "SORT_NAME": "sort_name",
}

# --- NTEE category mapping ------------------------------------------------

# Map first letter of NTEE code → human-readable major category.
# This makes filtering and reporting in the UI much friendlier.
NTEE_MAJOR = {
    "A": "Arts, Culture & Humanities",
    "B": "Education",
    "C": "Environment",
    "D": "Animal-Related",
    "E": "Health Care",
    "F": "Mental Health",
    "G": "Voluntary Health Associations",
    "H": "Medical Research",
    "I": "Crime & Legal-Related",
    "J": "Employment",
    "K": "Food, Agriculture & Nutrition",
    "L": "Housing & Shelter",
    "M": "Public Safety, Disaster Preparedness",
    "N": "Recreation & Sports",
    "O": "Youth Development",
    "P": "Human Services",
    "Q": "International, Foreign Affairs",
    "R": "Civil Rights, Social Action",
    "S": "Community Improvement",
    "T": "Philanthropy, Voluntarism",
    "U": "Science & Technology",
    "V": "Social Science",
    "W": "Public & Societal Benefit",
    "X": "Religion-Related",
    "Y": "Mutual & Membership Benefit",
    "Z": "Unknown",
}

# --- Helpers --------------------------------------------------------------

def get_supabase() -> Client:
    """Create a Supabase client using the service-role key."""
    load_dotenv(".env.local")
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env.local")
    return create_client(url, key)


def safe_int(value: str) -> int | None:
    """Parse an int, returning None on empty or invalid."""
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def parse_ntee(code: str) -> tuple[str | None, str | None]:
    """Return (full_code, major_category) for an NTEE code."""
    if not code or not code.strip():
        return None, None
    code = code.strip().upper()
    major = NTEE_MAJOR.get(code[0])
    return code, major


def parse_status(status_code: str) -> str:
    """
    Map IRS status code to our enum:
      01 = Unconditional Exemption → active
      02 = Conditional Exemption  → active
      12 = Trust description       → active
      25 = Pre-1969 ruling         → active
      Anything else                → inactive
    Reference: IRS Pub 4838.
    """
    code = (status_code or "").strip()
    return "active" if code in {"01", "02", "12", "25"} else "inactive"


def stream_csv(url: str, region: str) -> Iterator[dict[str, str]]:
    """Stream a remote CSV row-by-row without loading it all into memory."""
    print(f"  → fetching {region} from {url}")
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as response:
        response.raise_for_status()
        # IRS files are latin-1 encoded; the BMF has occasional non-UTF8 characters
        buffer = io.StringIO(response.content.decode("latin-1"))
        reader = csv.DictReader(buffer)
        yield from reader


def transform(row: dict[str, str]) -> dict | None:
    """
    Filter + map one BMF row to our `organizations` table schema.
    Returns None if the row should be skipped.
    """
    state = (row.get("STATE") or "").strip().upper()
    if state not in TARGET_STATES:
        return None

    subsection = safe_int(row.get("SUBSECTION", ""))
    if subsection not in TARGET_SUBSECTIONS:
        return None

    ein = (row.get("EIN") or "").strip().zfill(9)
    if not ein or not ein.isdigit() or len(ein) != 9:
        return None

    ntee_code, ntee_category = parse_ntee(row.get("NTEE_CD", ""))

    return {
        "ein": ein,
        "name": (row.get("NAME") or "").strip()[:500] or None,
        "in_care_of": (row.get("ICO") or "").strip()[:200] or None,
        "street": (row.get("STREET") or "").strip()[:200] or None,
        "city": (row.get("CITY") or "").strip()[:100] or None,
        "state": state,
        "zip": (row.get("ZIP") or "").strip()[:10] or None,
        "subsection_code": subsection,
        "ntee_code": ntee_code,
        "ntee_category": ntee_category,
        "fiscal_year_end_month": safe_int(row.get("ACCT_PD", "")),
        "ruling_date": (row.get("RULING") or "").strip() or None,
        "asset_amount": safe_int(row.get("ASSET_AMT", "")),
        "income_amount": safe_int(row.get("INCOME_AMT", "")),
        "revenue_amount": safe_int(row.get("REVENUE_AMT", "")),
        "status": parse_status(row.get("STATUS", "")),
        "source": "irs_bmf",
    }


def upsert_batch(supabase: Client, batch: list[dict]) -> None:
    """Upsert a batch of org records, retrying once on transient failure."""
    for attempt in (1, 2):
        try:
            supabase.table("organizations").upsert(batch, on_conflict="ein").execute()
            return
        except Exception as e:
            if attempt == 2:
                raise
            print(f"    ! batch failed ({type(e).__name__}), retrying in 3s...")
            time.sleep(3)


# --- Main -----------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Load IRS BMF into DEJ Intelligence")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count only; no DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N matching rows (testing)")
    parser.add_argument("--region", choices=list(BMF_REGIONS), default=None, help="Load only one region")
    args = parser.parse_args()

    supabase = None if args.dry_run else get_supabase()

    regions = {args.region: BMF_REGIONS[args.region]} if args.region else BMF_REGIONS

    started = time.time()
    total_seen = 0
    total_matched = 0
    total_loaded = 0
    by_state: dict[str, int] = {}
    batch: list[dict] = []

    for region, url in regions.items():
        print(f"\n=== Region: {region} ===")
        for raw in stream_csv(url, region):
            total_seen += 1
            mapped = transform(raw)
            if mapped is None:
                continue

            total_matched += 1
            by_state[mapped["state"]] = by_state.get(mapped["state"], 0) + 1
            batch.append(mapped)

            if args.limit and total_matched >= args.limit:
                break

            if len(batch) >= BATCH_SIZE:
                if not args.dry_run:
                    upsert_batch(supabase, batch)
                    total_loaded += len(batch)
                    print(f"  ✓ loaded {total_loaded:,} rows  (seen {total_seen:,})")
                batch = []

        if args.limit and total_matched >= args.limit:
            break

    # Final partial batch
    if batch:
        if not args.dry_run:
            upsert_batch(supabase, batch)
            total_loaded += len(batch)
        else:
            total_loaded = total_matched  # dry-run: report what would have loaded

    elapsed = time.time() - started

    print("\n" + "=" * 60)
    print("BMF LOAD SUMMARY")
    print("=" * 60)
    print(f"  Rows seen:    {total_seen:,}")
    print(f"  Rows matched: {total_matched:,}")
    print(f"  Rows loaded:  {total_loaded:,}{'  (DRY RUN)' if args.dry_run else ''}")
    print(f"  Elapsed:      {elapsed:.1f}s")
    print(f"\n  By state:")
    for state in sorted(by_state):
        print(f"    {state}: {by_state[state]:>7,}")
    print()


if __name__ == "__main__":
    main()
