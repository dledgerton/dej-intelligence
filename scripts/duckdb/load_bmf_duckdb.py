"""
IRS Business Master File loader → DuckDB for DEJ Intelligence PoC.

Adapted from scripts/loaders/load_bmf.py.
Same source, same filters, same transforms — DuckDB target instead of Supabase.

Run:
    python scripts/duckdb/load_bmf_duckdb.py
    python scripts/duckdb/load_bmf_duckdb.py --dry-run
    python scripts/duckdb/load_bmf_duckdb.py --limit 1000
    python scripts/duckdb/load_bmf_duckdb.py --region eo1
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from typing import Iterator

import duckdb
import httpx
from dotenv import load_dotenv

BMF_REGIONS = {
    "eo1": "https://www.irs.gov/pub/irs-soi/eo1.csv",
    "eo2": "https://www.irs.gov/pub/irs-soi/eo2.csv",
    "eo3": "https://www.irs.gov/pub/irs-soi/eo3.csv",
    "eo4": "https://www.irs.gov/pub/irs-soi/eo4.csv",
}

TARGET_STATES = {"DC", "MD", "VA", "MN", "NY"}
TARGET_SUBSECTIONS = {3, 6}
BATCH_SIZE = 1000
DEFAULT_DB_PATH = "data/dej_intelligence.duckdb"

NTEE_MAJOR = {
    "A": "Arts, Culture & Humanities", "B": "Education", "C": "Environment",
    "D": "Animal-Related", "E": "Health Care", "F": "Mental Health",
    "G": "Voluntary Health Associations", "H": "Medical Research",
    "I": "Crime & Legal-Related", "J": "Employment",
    "K": "Food, Agriculture & Nutrition", "L": "Housing & Shelter",
    "M": "Public Safety, Disaster Preparedness", "N": "Recreation & Sports",
    "O": "Youth Development", "P": "Human Services",
    "Q": "International, Foreign Affairs", "R": "Civil Rights, Social Action",
    "S": "Community Improvement", "T": "Philanthropy, Voluntarism",
    "U": "Science & Technology", "V": "Social Science",
    "W": "Public & Societal Benefit", "X": "Religion-Related",
    "Y": "Mutual & Membership Benefit", "Z": "Unknown",
}


def get_db_path() -> str:
    load_dotenv(".env.local")
    return os.environ.get("DEJ_DUCKDB_PATH") or DEFAULT_DB_PATH


def safe_int(value: str):
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def parse_ntee(code: str):
    if not code or not code.strip():
        return None, None
    code = code.strip().upper()
    return code, NTEE_MAJOR.get(code[0])


def parse_status(status_code: str) -> str:
    code = (status_code or "").strip()
    return "active" if code in {"01", "02", "12", "25"} else "revoked"


def stream_csv(url: str, region: str) -> Iterator[dict]:
    """Stream a remote CSV row-by-row using httpx with latin-1 decoding."""
    print(f"  → fetching {region} from {url}")
    with httpx.stream(
        "GET", url,
        timeout=120.0,
        follow_redirects=True,
        headers={"User-Agent": "DEJ-Intelligence-Loader/1.0"},
    ) as response:
        response.raise_for_status()
        response.encoding = "latin-1"
        line_iter = response.iter_lines()
        try:
            header_line = next(line_iter)
        except StopIteration:
            return
        headers = next(csv.reader([header_line]))
        for line in line_iter:
            if not line:
                continue
            try:
                values = next(csv.reader([line]))
            except (csv.Error, StopIteration):
                continue
            if len(values) < len(headers):
                values = values + [""] * (len(headers) - len(values))
            elif len(values) > len(headers):
                values = values[: len(headers)]
            yield dict(zip(headers, values))


def transform(row: dict):
    """Filter + map one BMF row to the organizations table schema."""
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
        "name": ((row.get("NAME") or "").strip() or "UNKNOWN")[:500],
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


def upsert_batch(con: duckdb.DuckDBPyConnection, batch: list[dict]) -> None:
    """Upsert org records into DuckDB using INSERT ... ON CONFLICT DO UPDATE."""
    if not batch:
        return
    cols = [
        "ein", "name", "in_care_of", "street", "city", "state", "zip",
        "subsection_code", "ntee_code", "ntee_category",
        "fiscal_year_end_month", "ruling_date",
        "asset_amount", "income_amount", "revenue_amount",
        "status", "source",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    update_set = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "ein")
    sql = (
        f"insert into organizations ({col_list}) values ({placeholders}) "
        f"on conflict (ein) do update set {update_set}, updated_at = now()"
    )
    rows_as_tuples = [tuple(r.get(c) for c in cols) for r in batch]
    con.executemany(sql, rows_as_tuples)


def main() -> None:
    p = argparse.ArgumentParser(description="Load IRS BMF into DEJ Intelligence DuckDB")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--region", choices=list(BMF_REGIONS), default=None)
    args = p.parse_args()

    db_path = get_db_path()
    print(f"Database: {db_path}")
    con = duckdb.connect(db_path)

    regions = {args.region: BMF_REGIONS[args.region]} if args.region else BMF_REGIONS

    started = time.time()
    total_seen = 0
    total_matched = 0
    total_loaded = 0
    by_state: dict = {}
    batch: list = []

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
                    upsert_batch(con, batch)
                    total_loaded += len(batch)
                    print(f"  ✓ loaded {total_loaded:,} rows  (seen {total_seen:,})")
                batch = []

        if args.limit and total_matched >= args.limit:
            break

    if batch:
        if not args.dry_run:
            upsert_batch(con, batch)
            total_loaded += len(batch)
        else:
            total_loaded = total_matched

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

    con.close()


if __name__ == "__main__":
    main()