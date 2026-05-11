"""
NCCS Core Files loader → DuckDB for DEJ Intelligence PoC.

Adapted from scripts/loaders/nccs_loader.py. Reads cached NCCS files,
filters to EINs in the DuckDB organizations table, writes filings rows.

All yesterday's fixes preserved: EIN normalization (EIN-XX-XXXXXXX → 9 digits),
F9_00_TAX_YEAR field mapping, period_end derivation, in-loader dedup.

Run:
    python scripts/duckdb/nccs_loader_duckdb.py
    python scripts/duckdb/nccs_loader_duckdb.py --dry-run --limit 100
    python scripts/duckdb/nccs_loader_duckdb.py --core-file-type PZ_CHARITIES
    python scripts/duckdb/nccs_loader_duckdb.py --refresh-cache
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import duckdb
import httpx
from dotenv import load_dotenv

NCCS_S3_BASE = "https://nccsdata.s3.amazonaws.com/harmonized/core"

FILE_TEMPLATES = {
    "PZ_CHARITIES": (
        f"{NCCS_S3_BASE}/501c3-pz/CORE-{{year}}-501C3-CHARITIES-PZ-HRMN.csv",
        "501C3-CHARITIES-PZ", "nccs_pz_charities", "990",
    ),
    "PZ_501CE": (
        f"{NCCS_S3_BASE}/501ce-pz/CORE-{{year}}-501CE-NONPROFIT-PZ-HRMN.csv",
        "501CE-NONPROFIT-PZ", "nccs_pz_501ce", "990",
    ),
    "PF": (
        f"{NCCS_S3_BASE}/501c3-pf/marts/CORE-{{year}}-501C3-PRIVFOUND-PF-HRMN-V0.csv",
        "501C3-PRIVFOUND-PF", "nccs_pf", "990PF",
    ),
}

YEAR_RANGES = {
    "PZ_CHARITIES": list(range(2016, 2023)),
    "PZ_501CE":     list(range(2016, 2023)),
    "PF":           list(range(2019, 2024)),
}

CACHE_DIR = Path("./data/nccs/_cache")
BATCH_SIZE = 5000   # DuckDB handles big batches fine; no IO budget worry
PARTIAL_THRESHOLD = 0.5
DEFAULT_DB_PATH = "data/dej_intelligence.duckdb"

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
}

REQUIRED_PROBE = ["ein", "total_revenue"]


def get_db_path() -> str:
    load_dotenv(".env.local")
    return os.environ.get("DEJ_DUCKDB_PATH") or DEFAULT_DB_PATH


def load_bmf_eins(con: duckdb.DuckDBPyConnection) -> set[str]:
    print("Loading BMF EIN set from organizations table...")
    rows = con.execute("select ein from organizations").fetchall()
    eins = {r[0] for r in rows if r[0]}
    print(f"  ✓ loaded {len(eins):,} BMF EINs")
    return eins


def safe_int(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.upper() in ("NA", "N/A", "NULL", "NONE", ".", "-"):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def find_field(row: dict, candidates: list):
    for cand in candidates:
        if cand in row:
            return row[cand]
        lower = cand.lower()
        for k in row:
            if k.lower() == lower:
                return row[k]
    return None


def normalize_ein(value):
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
    ty = safe_int(tax_year_raw)
    if ty and 2000 <= ty <= 2030:
        return ty
    if period_end_raw:
        s = str(period_end_raw).strip()
        if len(s) >= 4 and s[:4].isdigit():
            year = int(s[:4])
            if 2000 <= year <= 2030:
                return year
    return fallback_year


def parse_period_end(value):
    if not value:
        return None
    s = str(value).strip()
    if len(s) < 6 or not s[:6].isdigit():
        return None
    year, month = s[:4], s[4:6]
    if not (1 <= int(month) <= 12):
        return None
    return f"{year}-{month}-01"


@dataclass
class FileSpec:
    core_file_type: str
    schema_key: str
    year: int
    url: str
    label: str
    source_value: str
    form_type: str

    @property
    def cache_path(self) -> Path:
        return CACHE_DIR / f"CORE-{self.year}-{self.label}-HRMN.csv"


def build_specs(types: list = None) -> list:
    selected = types or list(FILE_TEMPLATES.keys())
    specs = []
    for cft in selected:
        url_tmpl, label, source_value, form_type = FILE_TEMPLATES[cft]
        schema_key = "PF" if cft == "PF" else "PZ"
        for year in YEAR_RANGES[cft]:
            specs.append(FileSpec(
                core_file_type=cft, schema_key=schema_key, year=year,
                url=url_tmpl.format(year=year), label=label,
                source_value=source_value, form_type=form_type,
            ))
    return specs


def head_size(client: httpx.Client, url: str):
    try:
        r = client.head(url, timeout=30.0, follow_redirects=True)
        if r.status_code == 200:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except httpx.HTTPError:
        return None
    return None


def assess_partial_years(client: httpx.Client, specs: list) -> dict:
    sizes = {}
    for spec in specs:
        size = head_size(client, spec.url)
        if size is None:
            continue
        sizes.setdefault(spec.core_file_type, {})[spec.year] = size
        print(f"  HEAD {spec.core_file_type} {spec.year}: {size/1024/1024:.1f} MB")
    flags = {}
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
                print(f"  ⚠ PARTIAL: {cft} {year}")
    return flags


def download_to_cache(client: httpx.Client, spec: FileSpec, refresh: bool = False) -> bool:
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


def probe_schema(cache_path: Path, schema: dict):
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


def parse_file(spec: FileSpec, partial: bool, bmf_eins: set, encoding: str) -> Iterator[dict]:
    schema = PF_FIELDS if spec.schema_key == "PF" else PZ_FIELDS
    with open(spec.cache_path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            outnccs = find_field(raw, schema["outnccs"])
            if outnccs and str(outnccs).strip().upper() in ("OUT", "1", "TRUE", "Y"):
                continue
            ein = normalize_ein(find_field(raw, schema["ein"]))
            if not ein or ein not in bmf_eins:
                continue
            tax_year_raw = find_field(raw, schema["tax_year"])
            period_end_raw = find_field(raw, schema["period_end"])
            tax_year = derive_tax_year(tax_year_raw, period_end_raw, spec.year)
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
                "program_revenue": None,
                "comp_employees": None,
            }
            if spec.schema_key == "PZ":
                row["program_revenue"] = safe_int(find_field(raw, schema["program_revenue"]))
                row["comp_employees"] = safe_int(find_field(raw, schema["comp_employees"]))
            yield row


def dedup_batch(batch: list) -> list:
    by_key = {}
    for row in batch:
        key = (row["ein"], row["tax_year"], row["form_type"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = row
            continue
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


def upsert_batch(con: duckdb.DuckDBPyConnection, batch: list) -> None:
    deduped = dedup_batch(batch)
    if not deduped:
        return
    cols = [
        "ein", "tax_year", "form_type", "period_end",
        "total_revenue", "total_expenses", "total_assets", "total_liabilities",
        "net_assets_eoy", "contributions", "program_revenue", "comp_employees",
        "source", "partial_year",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    update_set = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("ein", "tax_year", "form_type"))
    sql = (
        f"insert into filings ({col_list}) values ({placeholders}) "
        f"on conflict (ein, tax_year, form_type) do update set {update_set}, updated_at = now()"
    )
    rows_as_tuples = [tuple(r.get(c) for c in cols) for r in deduped]
    con.executemany(sql, rows_as_tuples)


def main() -> None:
    p = argparse.ArgumentParser(description="Load NCCS Core Files into DEJ Intelligence DuckDB")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--core-file-type", choices=list(FILE_TEMPLATES), default=None)
    p.add_argument("--refresh-cache", action="store_true")
    args = p.parse_args()

    db_path = get_db_path()
    print(f"Database: {db_path}")
    con = duckdb.connect(db_path)

    bmf_eins = load_bmf_eins(con)
    if not bmf_eins:
        print("No EINs in organizations table. Run load_bmf_duckdb.py first.")
        return

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
        by_source = {}
        batch = []
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
                print(f"    ! SCHEMA PROBE FAILED — missing: {missing}")
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
                        upsert_batch(con, batch)
                        total_loaded += len(dedup_batch(batch))
                        print(f"    ✓ loaded {total_loaded:,} rows  (matched {total_matched:,})")
                    batch = []
            print(f"    file kept {file_matched:,} rows")

        if batch:
            if not args.dry_run:
                upsert_batch(con, batch)
                total_loaded += len(dedup_batch(batch))
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
    con.close()


if __name__ == "__main__":
    main()