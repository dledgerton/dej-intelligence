"""
DEJ Intelligence — Phase 2 Step 2: IRS Form 990 Part VII XML Loader

Downloads IRS TEOS annual index CSVs, filters to 4-state market orgs already
in our organizations table, probes and downloads monthly ZIP batches for the
requested year, extracts XMLs to local cache, parses Part VII Section A
officer/compensation data, writes to the officers table in DuckDB.

Data source: https://apps.irs.gov/pub/epostcard/990/xml/
  - Index CSVs:  {base}/{year}/index_{year}.csv
  - ZIP batches: {base}/{year}/{year}_TEOS_XML_{MM}{suffix}.zip
                 e.g. 2022_TEOS_XML_01A.zip, 2022_TEOS_XML_01B.zip

Note: The index CSV has no column mapping filings to ZIPs (that column only
exists in 2024+). Strategy: probe all ZIPs for a year upfront, download and
extract all of them, then parse only our target EINs from local cache.

Usage:
    # Dry run — probe ZIP manifest, show counts, no downloads or writes
    python scripts/duckdb/phase2_step2_load_990_xml.py --dry-run --year 2022

    # Smoke test — download ZIPs, parse first 50 target filings
    python scripts/duckdb/phase2_step2_load_990_xml.py --year 2022 --limit 50

    # Single year full load
    python scripts/duckdb/phase2_step2_load_990_xml.py --year 2022

    # All years (2017-2023)
    python scripts/duckdb/phase2_step2_load_990_xml.py --all-years

    # Resume interrupted run (skips already-logged object IDs)
    python scripts/duckdb/phase2_step2_load_990_xml.py --year 2022 --resume

    # Single EIN for testing
    python scripts/duckdb/phase2_step2_load_990_xml.py --year 2022 --ein 521693895

Environment variables:
    DEJ_DB_PATH      Override default DuckDB path
    DEJ_CACHE_DIR    Override default cache dir (data/xml_cache/)
    DEJ_WORKERS      Parallel parse workers (default: 4)
"""

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

import duckdb


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dej.phase2")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

IRS_TEOS_BASE   = "https://apps.irs.gov/pub/epostcard/990/xml"
INDEX_YEARS     = list(range(2017, 2025))   # 2017-2023 inclusive
ZIP_MONTHS      = [f"{m:02d}" for m in range(1, 13)]
ZIP_SUFFIXES    = ["A", "B", "C", "D"]     # probe until 404

TOP_OFFICER_TITLES = {
    "CEO",
    "CHIEF EXECUTIVE OFFICER",
    "EXECUTIVE DIRECTOR",
    "EXEC DIRECTOR",
    "EXEC. DIRECTOR",
    "EXECUTIVE DIR",
    "EXECUTIVE DIR.",
    "ED",
    "PRESIDENT",
    "PRESIDENT & CEO",
    "PRESIDENT AND CEO",
    "PRESIDENT/CEO",
    "PRES & CEO",
    "PRES/CEO",
    "PRESIDENT/EXECUTIVE DIRECTOR",
    "EXECUTIVE DIRECTOR/CEO",
    "MANAGING DIRECTOR",
    "SUPERINTENDENT",
    "HEADMASTER",
    "HEAD OF SCHOOL",
}

# XML namespace stripping
NS_RE  = re.compile(r'\s+xmlns[^=]*="[^"]*"')
TAG_RE = re.compile(r'\{[^}]+\}')

# Part VII Section A XML tags
PART7_TAG      = "Form990PartVIISectionAGrp"
PERSON_NM_TAG  = "PersonNm"
TITLE_TAG      = "TitleTxt"
HOURS_TAG      = "AverageHoursPerWeekRt"
HOURS_REL_TAG  = "AverageHoursPerWeekRltdOrgRt"
COMP_ORG_TAG   = "ReportableCompFromOrgAmt"
COMP_REL_TAG   = "ReportableCompFromRltdOrgAmt"
COMP_OTHER_TAG = "OtherCompensationAmt"
OFFICER_IND    = "OfficerInd"
KEY_EMP_IND    = "KeyEmployeeInd"
HIGH_COMP_IND  = "HighestCompensatedEmployeeInd"
FORMER_IND     = "FormerOfcrDirectorTrusteeInd"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_db_path() -> str:
    return os.environ.get(
        "DEJ_DB_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "dej_intelligence.duckdb"),
    )


def get_cache_dir() -> Path:
    p = Path(os.environ.get(
        "DEJ_CACHE_DIR",
        str(Path(__file__).resolve().parents[2] / "data" / "xml_cache"),
    ))
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def fetch_url(url: str, retries: int = 3, timeout: int = 60) -> Optional[bytes]:
    """Fetch a URL with retries. Returns raw bytes or None on failure."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "DEJ-Intelligence/2.0 (nonprofit data research)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log.debug(f"404: {url}")
                return None
            log.warning(f"HTTP {e.code} attempt {attempt+1}: {url}")
        except Exception as e:
            log.warning(f"Fetch error attempt {attempt+1}: {e}")
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    return None


def head_exists(url: str, timeout: int = 15) -> bool:
    """Return True if URL responds 200 to a HEAD request."""
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "DEJ-Intelligence/2.0 (nonprofit data research)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ZIP manifest
# ---------------------------------------------------------------------------

# Known alternate ZIP patterns for years that predate the TEOS_XML naming convention
YEAR_ALT_ZIPS = {
    2020: [
        "2020_TEOS_XML_CT1",
        "download990xml_2020_1",
        "download990xml_2020_2",
        "download990xml_2020_3",
        "download990xml_2020_4",
        "download990xml_2020_5",
        "download990xml_2020_6",
    ],
    2019: [
        "download990xml_2019_1",
        "download990xml_2019_2",
        "download990xml_2019_3",
        "download990xml_2019_4",
        "download990xml_2019_5",
        "download990xml_2019_6",
    ],
    2018: [
        "download990xml_2018_1",
        "download990xml_2018_2",
        "download990xml_2018_3",
        "download990xml_2018_4",
    ],
    2017: [
        "download990xml_2017_1",
        "download990xml_2017_2",
        "download990xml_2017_3",
        "download990xml_2017_4",
    ],
}


def get_zip_manifest(year: int, cache_dir: Path) -> list[str]:
    """
    Return all valid ZIP batch names for a given year.
    For 2020 and earlier, uses known alternate naming patterns.
    For 2021+, probes via HEAD requests.
    Caches result to avoid re-probing.
    """
    manifest_cache = cache_dir / f"zip_manifest_{year}.json"
    if manifest_cache.exists():
        with open(manifest_cache) as f:
            result = json.load(f)
        log.info(f"  ZIP manifest {year}: {len(result)} ZIPs (from cache)")
        return result

    # Years with known alternate naming — probe to confirm which exist
    if year in YEAR_ALT_ZIPS:
        log.info(f"  Probing alternate ZIP manifest for {year} ...")
        found = []
        for name in YEAR_ALT_ZIPS[year]:
            url = f"{IRS_TEOS_BASE}/{year}/{name}.zip"
            if head_exists(url):
                found.append(name)
                log.info(f"    Found: {name}.zip")
            else:
                log.debug(f"    Not found: {name}.zip")
        with open(manifest_cache, "w") as f:
            json.dump(found, f)
        log.info(f"  ZIP manifest {year}: {len(found)} ZIPs found")
        return found

    # 2021+ — probe by month/suffix
    log.info(f"  Probing ZIP manifest for {year} ...")
    found = []
    for month in ZIP_MONTHS:
        for suffix in ZIP_SUFFIXES:
            name = f"{year}_TEOS_XML_{month}{suffix}"
            url  = f"{IRS_TEOS_BASE}/{year}/{name}.zip"
            if head_exists(url):
                found.append(name)
                log.info(f"    Found: {name}.zip")
            else:
                break

    with open(manifest_cache, "w") as f:
        json.dump(found, f)
    log.info(f"  ZIP manifest {year}: {len(found)} ZIPs found")
    return found


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def fetch_index(year: int, cache_dir: Path) -> Optional[list[dict]]:
    """
    Download (or load from cache) the IRS TEOS annual CSV index.

    CSV columns: RETURN_ID, FILING_TYPE, EIN, TAX_PERIOD, SUB_DATE,
                 TAXPAYER_NAME, RETURN_TYPE, DLN, OBJECT_ID
    (XML_BATCH_ID only present in 2024+ index files)
    """
    cache_file = cache_dir / f"index_{year}.json"

    if cache_file.exists():
        log.info(f"  Index {year}: loading from cache")
        with open(cache_file) as f:
            return json.load(f)

    url = f"{IRS_TEOS_BASE}/{year}/index_{year}.csv"
    log.info(f"  Index {year}: downloading {url}")
    raw = fetch_url(url, timeout=120)
    if raw is None:
        log.error(f"  Failed to download index_{year}.csv")
        return None

    reader = csv.DictReader(io.StringIO(raw.decode("utf-8", errors="replace")))
    filings = []
    for row in reader:
        filings.append({
            "EIN":         row.get("EIN", "").strip(),
            "OrgName":     row.get("TAXPAYER_NAME", "").strip(),
            "TaxPeriod":   row.get("TAX_PERIOD", "").strip(),
            "FormType":    row.get("RETURN_TYPE", "").strip(),
            "ObjectId":    row.get("OBJECT_ID", "").strip(),
            "SubmittedOn": row.get("SUB_DATE", "").strip(),
        })

    with open(cache_file, "w") as f:
        json.dump(filings, f)

    log.info(f"  Index {year}: {len(filings):,} filings cached")
    return filings


# ---------------------------------------------------------------------------
# ZIP batch fetch + extract
# ---------------------------------------------------------------------------

def fetch_and_extract_zip(zip_name: str, year: int, cache_dir: Path) -> int:
    """
    Download a TEOS ZIP and extract individual XML files to cache_dir.
    Idempotent — skips download if ZIP cached, skips files already extracted.
    Returns count of newly extracted XML files.
    """
    zip_cache = cache_dir / f"{zip_name}.zip"

    if not zip_cache.exists():
        url = f"{IRS_TEOS_BASE}/{year}/{zip_name}.zip"
        log.info(f"    Downloading {zip_name}.zip ...")
        raw = fetch_url(url, timeout=600)
        if raw is None:
            log.error(f"    Failed to download {zip_name}.zip")
            return 0
        zip_cache.write_bytes(raw)
        log.info(f"    {zip_name}.zip cached ({len(raw)/1024/1024:.1f} MB)")

    extracted = 0
    try:
        with zipfile.ZipFile(str(zip_cache), "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".xml"):
                    continue
                basename  = name.split("/")[-1]
                obj_id    = basename.replace("_public.xml", "")
                xml_cache = cache_dir / f"{obj_id}.xml"
                if not xml_cache.exists():
                    xml_cache.write_bytes(zf.read(name))
                    extracted += 1
    except NotImplementedError:
        log.info(f"    {zip_name}: unsupported compression, using system unzip ...")
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["unzip", "-q", "-o", str(zip_cache), "*.xml", "-d", tmp],
                capture_output=True
            )
            if result.returncode not in (0, 1):
                log.error(f"    unzip failed for {zip_name}: {result.stderr.decode()}")
                return 0
            for xml_file in Path(tmp).rglob("*.xml"):
                obj_id = xml_file.stem.replace("_public", "")
                dest = cache_dir / f"{obj_id}.xml"
                if not dest.exists():
                    dest.write_bytes(xml_file.read_bytes())
                    extracted += 1
    except zipfile.BadZipFile as e:
        log.error(f"    Bad ZIP {zip_name}: {e} — deleting, will retry next run")
        zip_cache.unlink(missing_ok=True)
        return 0

    if extracted:
        log.info(f"    {zip_name}: {extracted} new XML files extracted")
    return extracted


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def strip_namespaces(xml_bytes: bytes) -> str:
    text = xml_bytes.decode("utf-8", errors="replace")
    # Remove xmlns declarations (both default and prefixed)
    text = re.sub(r'\s+xmlns(?::[a-zA-Z0-9_]+)?="[^"]*"', "", text)
    # Remove namespace prefixes from tags: <irs:Tag> -> <Tag>, </irs:Tag> -> </Tag>
    text = re.sub(r'<(/?)([a-zA-Z0-9_]+):', r'<\1', text)
    # Remove namespace prefixes from attributes: irs:attr= -> attr=
    text = re.sub(r'\b[a-zA-Z0-9_]+:([a-zA-Z0-9_]+)=', r'\1=', text)
    return text


def find_text(root: ET.Element, *tag_names: str) -> Optional[str]:
    for tag in tag_names:
        el = root.find(".//" + tag)
        if el is not None and el.text:
            return el.text.strip()
        if "/" in tag:
            node = root
            for part in tag.split("/"):
                node = node.find(part) if node is not None else None
            if node is not None and node.text:
                return node.text.strip()
    return None


def parse_bool(root: ET.Element, tag: str) -> bool:
    el = root.find(".//" + tag)
    if el is None:
        return False
    return (el.text or "").strip().upper() in {"X", "1", "TRUE", "YES"}


def parse_int(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    try:
        return int(float(val.replace(",", "").strip()))
    except (ValueError, AttributeError):
        return None


def parse_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    try:
        return float(val.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def normalize_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = re.sub(r"[^A-Z0-9 ]", "", name.upper())
    return re.sub(r"\s+", " ", n).strip() or None


def normalize_title(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    t = re.sub(r"[^A-Z0-9 /&]", "", title.upper())
    return re.sub(r"\s+", " ", t).strip() or None


def is_top_officer_title(title_norm: Optional[str]) -> bool:
    if not title_norm:
        return False
    if title_norm in TOP_OFFICER_TITLES:
        return True
    for pattern in ["EXECUTIVE DIRECTOR", "CHIEF EXECUTIVE", "EXECUTIVE DIR"]:
        if pattern in title_norm:
            return True
    if "PRESIDENT" in title_norm and "VICE" not in title_norm and "FORMER" not in title_norm:
        return True
    return False


def parse_990_xml(xml_bytes: bytes, object_id: str) -> dict:
    """
    Parse a Form 990 XML file. Returns:
      {
        'header':  {ein, tax_year, state_cd, form_type},
        'officers': [...],
        'error':   None | 'no_part7' | 'xml_parse_error: ...'
      }
    """
    result = {"header": {}, "officers": [], "error": None}

    try:
        root = ET.fromstring(strip_namespaces(xml_bytes))
    except ET.ParseError as e:
        result["error"] = f"xml_parse_error: {e}"
        return result

    ein       = find_text(root, "EIN", "Filer/EIN")
    tax_end   = find_text(root, "TaxPeriodEndDt")
    state_cd  = find_text(root, "StateAbbreviationCd", "Filer/USAddress/StateAbbreviationCd")
    form_type = find_text(root, "ReturnTypeCd")

    tax_year = None
    if tax_end:
        try:
            if "-" in tax_end:
                yr, mo = int(tax_end[:4]), int(tax_end[5:7])
            else:
                yr, mo = int(tax_end[:4]), int(tax_end[4:6])
            # Fiscal year ending Jan-May belongs to prior calendar year
            tax_year = yr if mo >= 6 else yr - 1
        except (ValueError, IndexError):
            pass

    result["header"] = {
        "ein":       ein,
        "tax_year":  tax_year,
        "state_cd":  state_cd,
        "form_type": form_type or "990",
    }

    officer_rows = root.findall(f".//{PART7_TAG}")
    if not officer_rows:
        result["error"] = "no_part7"
        return result

    for row in officer_rows:
        person_name = find_text(row, PERSON_NM_TAG)
        if not person_name:
            continue

        title_raw    = find_text(row, TITLE_TAG)
        comp_org     = parse_int(find_text(row, COMP_ORG_TAG))
        comp_related = parse_int(find_text(row, COMP_REL_TAG))
        comp_other   = parse_int(find_text(row, COMP_OTHER_TAG))
        is_former    = parse_bool(row, FORMER_IND)
        title_norm   = normalize_title(title_raw)

        comp_total = None
        if any(x is not None for x in [comp_org, comp_related, comp_other]):
            comp_total = (comp_org or 0) + (comp_related or 0) + (comp_other or 0)

        result["officers"].append({
            "ein":                     ein,
            "tax_year":                tax_year,
            "object_id":               object_id,
            "form_type":               form_type or "990",
            "person_name":             person_name,
            "person_name_normalized":  normalize_name(person_name),
            "title_raw":               title_raw,
            "title_normalized":        title_norm,
            "is_officer":              parse_bool(row, OFFICER_IND),
            "is_key_employee":         parse_bool(row, KEY_EMP_IND),
            "is_highest_comp":         parse_bool(row, HIGH_COMP_IND),
            "is_former":               is_former,
            "is_top_officer":          is_top_officer_title(title_norm) and not is_former,
            "hours_per_week":          parse_float(find_text(row, HOURS_TAG)),
            "average_hours_related":   parse_float(find_text(row, HOURS_REL_TAG)),
            "comp_reportable_org":     comp_org,
            "comp_reportable_related": comp_related,
            "comp_other":              comp_other,
            "comp_total":              comp_total,
        })

    return result


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def load_target_eins(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute("select ein from organizations").fetchall()
    eins = set()
    for (ein,) in rows:
        eins.add(ein)
        eins.add(ein.lstrip("0"))
    return eins


def load_processed_object_ids(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute("select object_id from xml_filing_log").fetchall()
    return {r[0] for r in rows}


def insert_officers(con: duckdb.DuckDBPyConnection, officers: list[dict]) -> int:
    inserted = 0
    for o in officers:
        try:
            con.execute("""
                insert or ignore into officers (
                    ein, tax_year, object_id, form_type,
                    person_name, person_name_normalized,
                    title_raw, title_normalized,
                    is_officer, is_key_employee, is_highest_comp,
                    is_former, is_top_officer,
                    hours_per_week, average_hours_related,
                    comp_reportable_org, comp_reportable_related,
                    comp_other, comp_total
                ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                o["ein"], o["tax_year"], o["object_id"], o["form_type"],
                o["person_name"], o["person_name_normalized"],
                o["title_raw"], o["title_normalized"],
                o["is_officer"], o["is_key_employee"], o["is_highest_comp"],
                o["is_former"], o["is_top_officer"],
                o["hours_per_week"], o["average_hours_related"],
                o["comp_reportable_org"], o["comp_reportable_related"],
                o["comp_other"], o["comp_total"],
            ])
            inserted += 1
        except Exception as e:
            log.debug(f"Insert skip: {e}")
    return inserted


def log_filing(con, ein, tax_year, object_id, form_type,
               state_cd, status, officer_count, error_msg):
    try:
        con.execute("""
            insert or ignore into xml_filing_log
                (ein, tax_year, object_id, form_type,
                 state_cd, parse_status, officer_rows, error_msg)
            values (?,?,?,?,?,?,?,?)
        """, [ein, tax_year, object_id, form_type,
               state_cd, status, officer_count, error_msg])
    except Exception as e:
        log.debug(f"Log filing error: {e}")


# ---------------------------------------------------------------------------
# Worker: parse one filing from local XML cache
# ---------------------------------------------------------------------------

def process_filing(filing: dict, cache_dir: Path) -> dict:
    """
    Read a cached XML file and parse Part VII.
    All ZIPs must have been extracted before this is called.
    """
    object_id = filing.get("ObjectId", "")

    result = {
        "object_id": object_id,
        "ein":       filing.get("EIN", ""),
        "tax_year":  None,
        "state_cd":  None,
        "form_type": filing.get("FormType", "990"),
        "status":    "ok",
        "officers":  [],
        "error_msg": None,
    }

    cache_file = cache_dir / f"{object_id}.xml"
    if not cache_file.exists():
        result["status"]    = "parse_error"
        result["error_msg"] = "xml_not_in_cache"
        return result

    parsed = parse_990_xml(cache_file.read_bytes(), object_id)
    result["tax_year"] = parsed["header"].get("tax_year")
    result["state_cd"] = parsed["header"].get("state_cd")

    if parsed["error"] == "no_part7":
        result["status"] = "no_part7"
    elif parsed["error"]:
        result["status"]    = "parse_error"
        result["error_msg"] = parsed["error"]
    else:
        result["officers"] = parsed["officers"]

    return result


# ---------------------------------------------------------------------------
# Year runner
# ---------------------------------------------------------------------------

def run_year(year: int, args: argparse.Namespace,
             con: duckdb.DuckDBPyConnection,
             target_eins: set[str],
             processed_ids: set[str],
             cache_dir: Path) -> dict:

    stats = {
        "year": year, "index_total": 0, "state_matches": 0,
        "fetched": 0, "officers_inserted": 0, "errors": 0, "no_part7": 0,
    }

    log.info(f"\n{'='*60}\nYear {year}\n{'='*60}")

    # Step 1: load index
    filings = fetch_index(year, cache_dir)
    if filings is None:
        return stats
    stats["index_total"] = len(filings)

    # Step 2: filter candidates
    candidates = []
    for f in filings:
        if f.get("FormType") != "990":
            continue
        ein = f.get("EIN", "")
        if ein not in target_eins and ein.lstrip("0") not in target_eins:
            continue
        stats["state_matches"] += 1
        if args.resume and f.get("ObjectId") in processed_ids:
            continue
        if args.ein and f.get("EIN", "").lstrip("0") != args.ein.lstrip("0"):
            continue
        candidates.append(f)

    if args.limit:
        candidates = candidates[:args.limit]

    log.info(f"  State-matched 990 filings: {stats['state_matches']:,}")
    log.info(f"  To process this run:       {len(candidates):,}")

    # Step 3: probe ZIP manifest
    zip_names = get_zip_manifest(year, cache_dir)

    if args.dry_run:
        log.info("  DRY RUN — no downloads or writes")
        if candidates:
            s = candidates[0]
            log.info(f"  Sample: {s.get('OrgName')} ({s.get('EIN')})")
        log.info(f"  ZIPs that would be downloaded: {zip_names}")
        return stats

    # Step 4: download and extract all ZIPs for this year
    log.info(f"  Downloading {len(zip_names)} ZIP batch(es) ...")
    for zip_name in zip_names:
        fetch_and_extract_zip(zip_name, year, cache_dir)

    # Step 5: parse target filings from local cache
    batch_results: list[dict] = []
    batch_size = 50
    workers    = int(os.environ.get("DEJ_WORKERS", 4))

    def flush_batch():
        nonlocal batch_results
        for res in batch_results:
            log_filing(con, res["ein"], res["tax_year"], res["object_id"],
                       res["form_type"], res["state_cd"], res["status"],
                       len(res["officers"]), res["error_msg"])
            if res["officers"]:
                stats["officers_inserted"] += insert_officers(con, res["officers"])
            if res["status"] == "parse_error":
                stats["errors"] += 1
            elif res["status"] == "no_part7":
                stats["no_part7"] += 1
            elif res["status"] == "ok":
                stats["fetched"] += 1
        batch_results = []

    done_count = 0
    worker_fn  = partial(process_filing, cache_dir=cache_dir)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker_fn, f): f for f in candidates}
        for future in as_completed(futures):
            try:
                res = future.result()
            except Exception as e:
                log.error(f"Worker error: {e}")
                stats["errors"] += 1
                continue

            batch_results.append(res)
            done_count += 1

            if len(batch_results) >= batch_size:
                flush_batch()
                log.info(f"  Progress: {done_count}/{len(candidates)} | "
                         f"officers: {stats['officers_inserted']:,} | "
                         f"errors: {stats['errors']}")

    flush_batch()

    try:
        con.execute("""
            insert or replace into xml_index_cache
                (index_year, total_filings, state_filings, status)
            values (?, ?, ?, 'complete')
        """, [year, stats["index_total"], stats["state_matches"]])
    except Exception:
        pass

    log.info(f"\n  Year {year} complete:")
    log.info(f"    Fetched:           {stats['fetched']:,}")
    log.info(f"    Officers inserted: {stats['officers_inserted']:,}")
    log.info(f"    No Part VII:       {stats['no_part7']:,}")
    log.info(f"    Errors:            {stats['errors']:,}")

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2 Step 2: Load IRS 990 Part VII officer/comp data"
    )
    parser.add_argument("--year", type=int, help="Single year (2017-2023)")
    parser.add_argument("--all-years", action="store_true", help="Load all years 2017-2023")
    parser.add_argument("--resume", action="store_true", help="Skip already-processed filings")
    parser.add_argument("--dry-run", action="store_true", help="Preview without downloading or writing")
    parser.add_argument("--ein", type=str, help="Process only this EIN (testing)")
    parser.add_argument("--limit", type=int, help="Max filings per year (smoke test)")
    args = parser.parse_args()

    if not args.year and not args.all_years and not args.dry_run:
        parser.error("Specify --year YYYY, --all-years, or --dry-run --year YYYY")

    db_path   = get_db_path()
    cache_dir = get_cache_dir()
    log.info(f"Database:  {db_path}")
    log.info(f"XML cache: {cache_dir}")

    if not Path(db_path).exists():
        log.error("DuckDB file not found. Run Phase 1 + phase2_step1_schema.py first.")
        sys.exit(1)

    con = duckdb.connect(db_path)

    tables = {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main'"
    ).fetchall()}
    if "officers" not in tables:
        log.error("Officers table not found. Run phase2_step1_schema.py first.")
        sys.exit(1)

    target_eins   = load_target_eins(con)
    processed_ids = load_processed_object_ids(con) if args.resume else set()

    log.info(f"Target EINs (4-state): {len(target_eins):,}")
    if args.resume:
        log.info(f"Already processed:     {len(processed_ids):,}")

    years     = INDEX_YEARS if args.all_years else ([args.year] if args.year else INDEX_YEARS)
    all_stats = []

    for year in years:
        s = run_year(year, args, con, target_eins, processed_ids, cache_dir)
        all_stats.append(s)

    if len(all_stats) > 1:
        log.info(f"\n{'='*60}\nTOTAL SUMMARY\n{'='*60}")
        log.info(f"Years:             {len(all_stats)}")
        log.info(f"Total fetched:     {sum(s['fetched'] for s in all_stats):,}")
        log.info(f"Officers inserted: {sum(s['officers_inserted'] for s in all_stats):,}")
        log.info(f"Total errors:      {sum(s['errors'] for s in all_stats):,}")

    if not args.dry_run:
        count     = con.execute("select count(*) from officers").fetchone()[0]
        top_count = con.execute(
            "select count(*) from officers where is_top_officer = true"
        ).fetchone()[0]
        log.info(f"\nDatabase totals:")
        log.info(f"  officers:     {count:,}")
        log.info(f"  top officers: {top_count:,}")

    con.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
