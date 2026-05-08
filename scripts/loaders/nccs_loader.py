"""
NCCS Core Files loader for DEJ Intelligence.

Pulls the harmonized NCCS Core Files (PZ for charities + 501CE, PF for
private foundations), filters to EINs already in the `organizations`
table, maps fields to the existing `filings` table schema, and upserts
in batches to Supabase.

NCCS Core does NOT contain geography fields — state, city, NTEE all live
in the BMF (organizations table) and are accessed via EIN join.

Source values written:
  nccs_pz_charities  — 501(c)(3) public charities, PZ family (990 + 990EZ)
  nccs_pz_501ce      — Other 501(c) types, PZ family
  nccs_pf            — 501(c)(3) private foundations, PF family

Run:
    python scripts/loaders/nccs_loader.py            # full load (default)
    python scripts/loaders/nccs_loader.py --dry-run  # parse + count, no DB writes
    python scripts/loaders/nccs_loader.py --limit 1000  # test with 1000 rows
    python scripts/loaders/nccs_loader.py --core-file-type PZ_CHARITIES
    python scripts/loaders/nccs_loader.py --refresh-cache  # force re-download

Source: https://urbaninstitute.github.io/nccs/catalogs/catalog-core.html
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx
from dotenv import load_dotenv
from supabase import Client, create_client

# --- Config ---------------------------------------------------------------

NCCS_S3_BASE = "https://nccsdata.s3.amazonaws.com/harmonized/core"

# Three Core file families. PZ chosen over PC for charities/501CE — broader
# universe (includes 990EZ filers, which catches mid-size DEJ Search prospects).
FILE_TEMPLATES = {
    "PZ_CHARITIES": (
        f"{NCCS_S3_BASE}/501c3-pz/CORE-{{year}}-501C3-CHARITIES-PZ-HRMN.csv",
        "501C3-CHARITIES-PZ",
        "nccs_pz_charities",  # source value written to filings.source
        "990",                # form_type written to filings.form_type
    ),
    "PZ_501CE": (
        f"{NCCS_S3_BASE}/501ce-pz/CORE-{{year}}-501CE-NONPROFIT-PZ-HRMN.csv",
        "501CE-NONPROFIT-PZ",
        "nccs_pz_501ce",
        "990",
    ),
    "PF": (
        f"{NCCS_S3_BASE}/501c3-pf/marts/CORE-{{year}}-501C3-PRIVFOUND-PF-HRMN-V0.csv",
        "501C3-PRIVFOUND-PF",
        "nccs_pf",
        "990PF",
    ),
}

# Years per file family. PF starts at 2019 — 2017 (0.3 MB) and 2018 (1.9 MB)
# are functionally empty (electronic filing wasn't mandatory yet).
YEAR_RANGES = {
    "PZ_CHARITIES": list(range(2016, 2023)),   # 2016-2022
    "PZ_501CE":     list(range(2016, 2023)),   # 2016-2022
    "PF":           list(range(2019, 2024)),   # 2019-2023
}

CACHE_DIR = Path("./data/nccs/_cache")
BATCH_SIZE = 1000  # rows per Supabase upsert call
PARTIAL_THRESHOLD = 0.5  # file <50% of prior years' avg size → partial flag

# --- Field mapping --------------------------------------------------------

# NCCS harmonized files use F9_XX_* prefixes for Form 990 part numbers,
# and PF_XX_* for Form 990-PF parts. Field naming is stable across vintages
# within a family, but PZ and PF use entirely different schemas.

PZ_FIELDS = {
    "ein":               ["EIN2", "F9_00_ORG_EIN", "EIN"],
    "tax_year":          ["F9_00_TAX_YEAR"],
    "period_end":        ["F9_00_TAX_PERIOD_END_DATE"],
    "total_revenue":     ["F9_08_REV_TOT_TOT", "F9_01_REV_TOT_CY"],
    "total_expenses":    ["F9_09_EXP_TOT_TOT", "F9_01_EXP_TOT_CY"],
    "total_assets":      ["F9_10_ASSET_TOT_EOY"],
    "total_liabilities": ["F9_10_LIAB_TOT_EOY"],
    "net_assets_eoy":    ["F9_10_NAFB_TOT_EOY", "F9_01_NAFB_TOT_EOY"],
    "contributions":     ["F9_08_REV_CONTR_TOT", "F9_01_REV_CONTR_TOT_CY_2"],
    "program_revenue":   ["F9_08_REV_PROG_TOT_TOT"],
    "comp_employees":    ["F9_09_EXP_COMP_DTK_TOT", "F9_07_COMP_DTK_COMP_ORG_TOT"],
    "outnccs":           ["OUTNCCS"],
}

PF_FIELDS = {
    "ein":               ["EIN2", "EIN"],
    "tax_year":          ["F9_00_TAX_YEAR"],
    "period_end":        ["F9_00_TAX_PERIOD_END_DATE"],
    "total_revenue":     ["PF_01_REV_TOT_BOOKS", "PF_01_REV_TOT_NET"],
    "total_expenses":    ["PF_01_EXP_TOT_EXP_DISBMT_BOOKS", "PF_01_EXP_TOT_EXP_DISBMT_NET"],
    "total_assets":      ["PF_02_ASSET_TOT_EOY_FMV", "PF_02_ASSET_TOT_EOY_BV"],
    "total_liabilities": ["PF_02_LIAB_TOT_EOY_BV"],
    "net_assets_eoy":    ["PF_02_NAFB_TOT_EOY_BV"],
    "contributions":     ["PF_01_REV_CONTR_REC_BOOKS"],
    "outnccs":           ["OUTNCCS"],
    # PF has no direct equivalent for program_revenue or comp_employees on
    # Form 990-PF; those fields will be null for PF rows.
}

# Required fields for the schema probe. If a file's header doesn't contain
# at least one candidate for each of these, abort that file with a clear error.
REQUIRED_PROBE = ["ein", "total_revenue"]

# --- Helpers --------------------------------------------------------------

def get_supabase() -> Client:
    """Create a Supabase client using the service-role key."""
    load_dotenv(".env.local")
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env.local")
    return create_client(url, key)


def load_bmf_eins(supabase: Client) -> set[str]:
    """
    Pull all EINs from the organizations table into a set for fast lookup.
    Supabase has a default 1000-row limit per query, so paginate through.
    """
    print("Loading BMF EIN set from organizations table...")
    eins: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        resp = (
            supabase.table("organizations")
            .select("ein")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        for row in rows:
            ein = (row.get("ein") or "").strip()
            if ein:
                eins.add(ein)
        if len(rows) < page_size:
            break
        offset += page_size
    print(f"  ✓ loaded {len(eins):,} BMF EINs")
    return eins


def safe_int(value) -> int | None:
    """Parse an int, returning None on empty, NA, or invalid."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.upper() in ("NA", "N/A", "NULL", "NONE", ".", "-"):
        return None
    try:
        return int(float(s))  # handle "1234.0" form
    except (ValueError, TypeError):
        return None


def find_field(row: dict, candidates: list[str]):
    """Return the value of the first candidate field present in row."""
    for cand in candidates:
        if cand in row:
            return row[cand]
        lower = cand.lower()
        for k in row:
            if k.lower() == lower:
                return row[k]
    return None


def normalize_ein(value) -> str | None:
    """
    Normalize NCCS EIN format to BMF format.
    NCCS uses 'EIN-01-0015091' (prefix + dash); BMF uses '010015091' (9 digits).
    Strips the EIN- prefix and any dashes, then zero-pads to 9 digits.
    """
    if value is None:
        return None
    s = str(value).strip().upper()
    if s.startswith("EIN-"):
        s = s[4:]
    s = "".join(c for c in s if c.isdigit())
    if not s:
        return None
    s = s.zfill(9)
    if len(s) != 9:
        return None
    return s

def derive_tax_year(tax_year_raw, period_end_raw, fallback_year: int) -> int:
    """
    Resolve the real tax year for a Core row.
    Priority: F9_00_TAX_YEAR field > year-portion of F9_00_TAX_PERIOD_END_DATE
              > filename year (last resort).
    NCCS file vintage (filename year) is unreliable — same file can contain
    filings spanning multiple real tax years.
    """
    ty = safe_int(tax_year_raw)
    if ty and 2000 <= ty <= 2030:
        return ty
    # F9_00_TAX_PERIOD_END_DATE is YYYYMM (e.g., '201706')
    if period_end_raw:
        s = str(period_end_raw).strip()
        if len(s) >= 4 and s[:4].isdigit():
            year = int(s[:4])
            month = safe_int(s[4:6]) if len(s) >= 6 else None
            # Tax year for fiscal years ending Jan-Jun is the prior calendar year
            # in IRS convention, but NCCS reports tax year as the calendar year
            # the period ends in. Match NCCS convention.
            if 2000 <= year <= 2030:
                return year
    return fallback_year


def parse_period_end(value) -> str | None:
    """Convert YYYYMM string to YYYY-MM-01 date for filings.period_end."""
    if not value:
        return None
    s = str(value).strip()
    if len(s) < 6 or not s[:6].isdigit():
        return None
    year = s[:4]
    month = s[4:6]
    if not (1 <= int(month) <= 12):
        return None
    return f"{year}-{month}-01"

# --- File specs -----------------------------------------------------------

@dataclass
class FileSpec:
    core_file_type: str
    schema_key: str           # "PZ" | "PF"
    year: int
    url: str
    label: str
    source_value: str         # written to filings.source
    form_type: str            # written to filings.form_type

    @property
    def cache_path(self) -> Path:
        return CACHE_DIR / f"CORE-{self.year}-{self.label}-HRMN.csv"


def build_specs(types: list[str] | None = None) -> list[FileSpec]:
    selected = types or list(FILE_TEMPLATES.keys())
    specs: list[FileSpec] = []
    for cft in selected:
        url_tmpl, label, source_value, form_type = FILE_TEMPLATES[cft]
        schema_key = "PF" if cft == "PF" else "PZ"
        for year in YEAR_RANGES[cft]:
            specs.append(FileSpec(
                core_file_type=cft,
                schema_key=schema_key,
                year=year,
                url=url_tmpl.format(year=year),
                label=label,
                source_value=source_value,
                form_type=form_type,
            ))
    return specs

# --- Download + partial detection ----------------------------------------

def head_size(client: httpx.Client, url: str) -> int | None:
    try:
        r = client.head(url, timeout=30.0, follow_redirects=True)
        if r.status_code == 200:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except httpx.HTTPError:
        return None
    return None


def assess_partial_years(client: httpx.Client, specs: list[FileSpec]) -> dict:
    """Flag (cft, year) as partial if size <50% of avg of prior years."""
    sizes: dict[str, dict[int, int]] = {}
    for spec in specs:
        size = head_size(client, spec.url)
        if size is None:
            continue
        sizes.setdefault(spec.core_file_type, {})[spec.year] = size
        print(f"  HEAD {spec.core_file_type} {spec.year}: {size/1024/1024:.1f} MB")

    flags: dict[tuple[str, int], bool] = {}
    for cft, year_sizes in sizes.items():
        sorted_years = sorted(year_sizes.keys())
        for i, year in enumerate(sorted_years):
            if i == 0:
                flags[(cft, year)] = False
                continue
            prior_avg = sum(year_sizes[y] for y in sorted_years[:i]) / i
            is_partial = year_sizes[year] < (PARTIAL_THRESHOLD * prior_avg)
            flags[(cft, year)] = is_partial
            if is_partial:
                print(f"  ⚠ PARTIAL: {cft} {year} "
                      f"({year_sizes[year]/1024/1024:.1f} MB vs "
                      f"prior avg {prior_avg/1024/1024:.1f} MB)")
    return flags


def download_to_cache(client: httpx.Client, spec: FileSpec, refresh: bool = False) -> bool:
    """Download a Core file to cache. Returns False if the file 404s."""
    if spec.cache_path.exists() and not refresh:
        return True
    print(f"  → downloading {spec.core_file_type} {spec.year}")
    try:
        r = client.get(spec.url, timeout=300.0, follow_redirects=True)
        if r.status_code == 404:
            print(f"    ! 404 NOT FOUND, skipping")
            return False
        r.raise_for_status()
        spec.cache_path.parent.mkdir(parents=True, exist_ok=True)
        spec.cache_path.write_bytes(r.content)
        print(f"    ✓ saved {spec.cache_path.stat().st_size/1024/1024:.1f} MB")
        return True
    except httpx.HTTPError as e:
        print(f"    ! download failed: {e}")
        return False

# --- Parse + transform ----------------------------------------------------

def probe_schema(cache_path: Path, schema: dict) -> tuple[bool, list[str], str]:
    """
    Read the CSV header, verify required canonical fields can map, and
    detect encoding. Returns (ok, missing_required, encoding).
    """
    encoding = "utf-8"
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            f.read(8192)
    except UnicodeDecodeError:
        encoding = "latin-1"

    with open(cache_path, "r", encoding=encoding, newline="") as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            return False, ["<empty file>"], encoding

    headers_set = set(headers)
    headers_lower = {h.lower() for h in headers}

    missing = []
    for canon_name in REQUIRED_PROBE:
        candidates = schema[canon_name]
        if not any(c in headers_set or c.lower() in headers_lower for c in candidates):
            missing.append(canon_name)

    return (len(missing) == 0), missing, encoding


def parse_file(spec: FileSpec, partial: bool, bmf_eins: set[str], encoding: str) -> Iterator[dict]:
    """
    Stream-parse one Core file, yielding rows shaped for the `filings` table.
    Filters to EINs in the BMF universe. Drops OUTNCCS-flagged rows.
    """
    schema = PF_FIELDS if spec.schema_key == "PF" else PZ_FIELDS

    with open(spec.cache_path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            # OUTNCCS filter — drop NCCS-flagged out-of-scope rows
            outnccs = find_field(raw, schema["outnccs"])
            if outnccs and str(outnccs).strip().upper() in ("OUT", "1", "TRUE", "Y"):
                continue

            # EIN filter — only keep rows for orgs in our BMF universe
            ein = normalize_ein(find_field(raw, schema["ein"]))
            if not ein or ein not in bmf_eins:
                continue

            # Tax year — use real form data, fall back through derivation chain
            tax_year_raw = find_field(raw, schema["tax_year"])
            period_end_raw = find_field(raw, schema["period_end"])
            tax_year = derive_tax_year(tax_year_raw, period_end_raw, spec.year)

            # Build row matching the filings table schema
            row = {
                "ein": ein,
                "tax_year": tax_year,
                "form_type": spec.form_type,
                "period_end": parse_period_end(period_end_raw),
                "total_revenue": safe_int(find_field(raw, schema["total_revenue"])),
                "total_expenses": safe_int(find_field(raw, schema["total_expenses"])),
                "total_assets": safe_int(find_field(raw, schema["total_assets"])),
                "total_liabilities": safe_int(find_field(raw, schema["total_liabilities"])),
                "net_assets_eoy": safe_int(find_field(raw, schema["net_assets_eoy"])),
                "contributions": safe_int(find_field(raw, schema["contributions"])),
                "source": spec.source_value,
                "partial_year": partial,
            }

            # PZ-only fields (PF doesn't have direct equivalents)
            if spec.schema_key == "PZ":
                row["program_revenue"] = safe_int(find_field(raw, schema["program_revenue"]))
                row["comp_employees"] = safe_int(find_field(raw, schema["comp_employees"]))

            yield row


def dedup_batch(batch: list[dict]) -> list[dict]:
    """
    Collapse same-(ein, tax_year, form_type) rows within a batch.
    Postgres upsert can't update the same row twice in one statement, and
    NCCS dumps occasionally include duplicate filings (amendments, snapshots).
    Tie-break: latest period_end wins; on tie, highest total_revenue wins
    (proxy for "most complete amendment").
    """
    by_key: dict[tuple, dict] = {}
    for row in batch:
        key = (row["ein"], row["tax_year"], row["form_type"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = row
            continue
        # Compare period_end (string YYYY-MM-01 sorts correctly)
        new_pe = row.get("period_end") or ""
        old_pe = existing.get("period_end") or ""
        if new_pe > old_pe:
            by_key[key] = row
        elif new_pe == old_pe:
            new_rev = row.get("total_revenue") or 0
            old_rev = existing.get("total_revenue") or 0
            if new_rev > old_rev:
                by_key[key] = row
    return list(by_key.values())


def upsert_batch(supabase: Client, batch: list[dict]) -> None:
    """Upsert filings, retrying once on transient failure."""
    deduped = dedup_batch(batch)
    for attempt in (1, 2):
        try:
            supabase.table("filings").upsert(
                deduped,
                on_conflict="ein,tax_year,form_type",
            ).execute()
            return
        except Exception as e:
            if attempt == 2:
                raise
            print(f"    ! batch failed ({type(e).__name__}), retrying in 3s...")
            time.sleep(3)

# --- Main -----------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Load NCCS Core Files into DEJ Intelligence")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count only; no DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N matched rows (testing)")
    parser.add_argument("--core-file-type", choices=list(FILE_TEMPLATES), default=None,
                        help="Load only one file family")
    parser.add_argument("--refresh-cache", action="store_true",
                        help="Re-download files even if cached")
    args = parser.parse_args()

    supabase = get_supabase()

    bmf_eins = load_bmf_eins(supabase)
    if not bmf_eins:
        sys.exit("No EINs in organizations table. Run load_bmf.py first.")

    types = [args.core_file_type] if args.core_file_type else None
    specs = build_specs(types)
    print(f"\nBuilt {len(specs)} file specs")

    print("\n=== Assessing partial years via HEAD ===")
    started = time.time()

    with httpx.Client(headers={"User-Agent": "DEJ-Intelligence-Loader/1.0"}) as http:
        partial_flags = assess_partial_years(http, specs)

        total_matched = 0
        total_loaded = 0
        files_processed = 0
        files_skipped = 0
        by_source: dict[str, int] = {}
        batch: list[dict] = []
        limit_hit = False

        for spec in specs:
            if limit_hit:
                break
            print(f"\n=== {spec.core_file_type} {spec.year} ===")
            partial = partial_flags.get((spec.core_file_type, spec.year), False)

            if not download_to_cache(http, spec, refresh=args.refresh_cache):
                files_skipped += 1
                continue

            schema = PF_FIELDS if spec.schema_key == "PF" else PZ_FIELDS
            ok, missing, encoding = probe_schema(spec.cache_path, schema)
            if not ok:
                print(f"    ! SCHEMA PROBE FAILED — missing canonical fields: {missing}")
                print(f"    skipping {spec.cache_path.name}")
                files_skipped += 1
                continue
            print(f"    ✓ schema probe passed (encoding={encoding})")

            files_processed += 1
            file_matched = 0

            for row in parse_file(spec, partial, bmf_eins, encoding):
                total_matched += 1
                file_matched += 1
                by_source[spec.source_value] = by_source.get(spec.source_value, 0) + 1
                batch.append(row)

                if args.limit and total_matched >= args.limit:
                    limit_hit = True
                    break

                if len(batch) >= BATCH_SIZE:
                    if not args.dry_run:
                        upsert_batch(supabase, batch)
                        total_loaded += len(batch)
                        print(f"    ✓ loaded {total_loaded:,} rows  (matched {total_matched:,})")
                    batch = []

            print(f"    file kept {file_matched:,} rows")

        # Final partial batch
        if batch:
            if not args.dry_run:
                upsert_batch(supabase, batch)
                total_loaded += len(batch)
            else:
                total_loaded = total_matched

    elapsed = time.time() - started

    print("\n" + "=" * 60)
    print("NCCS LOAD SUMMARY")
    print("=" * 60)
    print(f"  Files processed: {files_processed}")
    print(f"  Files skipped:   {files_skipped}")
    print(f"  Rows matched:    {total_matched:,}")
    print(f"  Rows loaded:     {total_loaded:,}{'  (DRY RUN)' if args.dry_run else ''}")
    print(f"  Elapsed:         {elapsed:.1f}s")
    print(f"\n  By source:")
    for src in sorted(by_source):
        print(f"    {src}: {by_source[src]:>7,}")
    print()


if __name__ == "__main__":
    main()