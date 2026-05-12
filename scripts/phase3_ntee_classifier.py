"""
DEJ Intelligence — Phase 3 NTEE Classifier
===========================================
Classifies nonprofit organizations into NTEE major categories using Claude.
Processes orgs in batches of 50 to minimize API calls.

Targets orgs with null/empty NTEE codes first, then optionally re-classifies all.

NTEE Major Categories:
  A - Arts, Culture & Humanities
  B - Education
  C - Environment
  D - Animal-Related
  E - Health Care
  F - Mental Health & Crisis Intervention
  G - Disease, Disorders & Medical Disciplines
  H - Medical Research
  I - Crime & Legal-Related
  J - Employment
  K - Food, Agriculture & Nutrition
  L - Housing & Shelter
  M - Public Safety, Disaster Preparedness
  N - Recreation & Sports
  O - Youth Development
  P - Human Services
  Q - International, Foreign Affairs
  R - Civil Rights, Social Action & Advocacy
  S - Community Improvement & Capacity Building
  T - Philanthropy, Voluntarism & Grantmaking
  U - Science & Technology
  V - Social Science
  W - Public & Societal Benefit
  X - Religion-Related
  Y - Mutual & Membership Benefit
  Z - Unknown

Run from project root:
  python3 scripts/phase3_ntee_classifier.py --dry-run
  python3 scripts/phase3_ntee_classifier.py --null-only
  python3 scripts/phase3_ntee_classifier.py --null-only --limit 500
  python3 scripts/phase3_ntee_classifier.py --all
"""

import argparse
import json
import logging
import os
import time

import anthropic
import duckdb
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DB_PATH = "data/dej_intelligence.duckdb"
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 2.0  # seconds — avoid rate limiting
MAX_RETRIES = 6
RETRY_BASE_SLEEP = 5.0  # seconds — exponential backoff base for 529s

NTEE_CATEGORIES = {
    "A": "Arts, Culture & Humanities",
    "B": "Education",
    "C": "Environment",
    "D": "Animal-Related",
    "E": "Health Care",
    "F": "Mental Health & Crisis Intervention",
    "G": "Disease, Disorders & Medical Disciplines",
    "H": "Medical Research",
    "I": "Crime & Legal-Related",
    "J": "Employment",
    "K": "Food, Agriculture & Nutrition",
    "L": "Housing & Shelter",
    "M": "Public Safety & Disaster Preparedness",
    "N": "Recreation & Sports",
    "O": "Youth Development",
    "P": "Human Services",
    "Q": "International & Foreign Affairs",
    "R": "Civil Rights, Social Action & Advocacy",
    "S": "Community Improvement & Capacity Building",
    "T": "Philanthropy, Voluntarism & Grantmaking",
    "U": "Science & Technology",
    "V": "Social Science",
    "W": "Public & Societal Benefit",
    "X": "Religion-Related",
    "Y": "Mutual & Membership Benefit",
    "Z": "Unknown",
}

SYSTEM_PROMPT = """You are an expert nonprofit sector classifier. Your job is to assign NTEE major category codes to nonprofit organizations based on their names.

NTEE Major Categories:
A=Arts/Culture/Humanities, B=Education, C=Environment, D=Animal-Related,
E=Health Care, F=Mental Health, G=Disease/Medical Disciplines, H=Medical Research,
I=Crime/Legal, J=Employment, K=Food/Agriculture/Nutrition, L=Housing/Shelter,
M=Public Safety/Disaster, N=Recreation/Sports, O=Youth Development,
P=Human Services, Q=International/Foreign Affairs, R=Civil Rights/Advocacy,
S=Community Improvement, T=Philanthropy/Grantmaking, U=Science/Technology,
V=Social Science, W=Public/Societal Benefit, X=Religion-Related,
Y=Mutual/Membership Benefit, Z=Unknown

Rules:
- Return ONLY a JSON array, no preamble, no markdown, no explanation
- One object per org in the same order as input
- Each object: {"ein": "...", "code": "A", "confidence": "high|medium|low", "reason": "brief reason"}
- confidence=high when name clearly indicates category
- confidence=medium when name suggests but is ambiguous
- confidence=low when name gives minimal signal
- Use Z only when truly unclassifiable
- Foundations and family foundations → T (Philanthropy)
- Churches, ministries, congregations → X (Religion)
- Alumni associations → B (Education) if school-affiliated, S otherwise
- YMCAs, boys/girls clubs → O (Youth Development)
- Chambers of commerce → S (Community Improvement)"""


def classify_batch(client: anthropic.Anthropic, batch: list[tuple]) -> list[dict]:
    """
    Send a batch of (ein, name) tuples to Claude for NTEE classification.
    Returns list of dicts with ein, code, confidence, reason.
    Retries on 529 overload errors with exponential backoff.
    """
    org_list = "\n".join(
        f'{i+1}. EIN:{ein} NAME:{name}' for i, (ein, name) in enumerate(batch)
    )

    prompt = f"Classify these {len(batch)} nonprofits into NTEE major categories:\n\n{org_list}"

    raw = ""
    for attempt in range(MAX_RETRIES):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = message.content[0].text.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            results = json.loads(raw)
            return results

        except json.JSONDecodeError as e:
            log.error(f"JSON parse error on batch: {e}")
            log.error(f"Raw response: {raw[:500]}")
            return [{"ein": ein, "code": "Z", "confidence": "low", "reason": "parse error"} for ein, _ in batch]

        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                sleep_time = RETRY_BASE_SLEEP * (2 ** attempt)
                log.warning(f"API overloaded (529) — attempt {attempt+1}/{MAX_RETRIES}, sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
                continue
            else:
                log.error(f"API error on batch: {e}")
                return [{"ein": ein, "code": "Z", "confidence": "low", "reason": f"api error: {str(e)}"} for ein, _ in batch]

        except Exception as e:
            log.error(f"Unexpected error on batch: {e}")
            return [{"ein": ein, "code": "Z", "confidence": "low", "reason": f"api error: {str(e)}"} for ein, _ in batch]

    # All retries exhausted
    log.error(f"Batch failed after {MAX_RETRIES} attempts — marking as api error")
    return [{"ein": ein, "code": "Z", "confidence": "low", "reason": "api error: max retries exceeded"} for ein, _ in batch]


MIGRATION_SQL = """
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ntee_code_classified VARCHAR;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ntee_category_classified VARCHAR;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ntee_confidence VARCHAR;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ntee_reason VARCHAR;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ntee_classified_at TIMESTAMP;
"""


def run_classifier(
    con: duckdb.DuckDBPyConnection,
    client: anthropic.Anthropic,
    null_only: bool = True,
    limit: int = None,
    dry_run: bool = False,
):
    # Fetch orgs to classify
    if null_only:
        query = """
            SELECT ein, name FROM organizations
            WHERE (ntee_code IS NULL OR ntee_code = '')
              AND (ntee_code_classified IS NULL
                   OR (ntee_code_classified = 'Z' AND ntee_reason LIKE '%api error%'))
            ORDER BY income_amount DESC NULLS LAST
        """
        log.info("Mode: null NTEE only (including error Z cleanup)")
    else:
        query = """
            SELECT ein, name FROM organizations
            WHERE ntee_code_classified IS NULL
            ORDER BY income_amount DESC NULLS LAST
        """
        log.info("Mode: all unclassified orgs")

    if limit:
        query += f" LIMIT {limit}"

    orgs = con.execute(query).fetchall()
    total = len(orgs)
    log.info(f"Orgs to classify: {total:,}")

    if dry_run:
        log.info("DRY RUN — showing first batch only, no writes")
        sample = orgs[:5]
        log.info("Sample orgs that would be classified:")
        for ein, name in sample:
            log.info(f"  {ein} | {name}")
        return

    # Process in batches
    batches = [orgs[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    log.info(f"Total batches: {len(batches):,}")

    total_classified = 0
    errors = 0

    for batch_num, batch in enumerate(batches, 1):
        if batch_num % 10 == 0 or batch_num == 1:
            log.info(f"Batch {batch_num}/{len(batches)} — classified so far: {total_classified:,}")

        results = classify_batch(client, batch)

        # Write results to DB
        rows = []
        for r in results:
            ein = r.get("ein", "")
            code = r.get("code", "Z").upper()
            confidence = r.get("confidence", "low")
            reason = r.get("reason", "")
            category = NTEE_CATEGORIES.get(code, "Unknown")

            if not ein:
                errors += 1
                continue

            rows.append((code, category, confidence, reason, ein))

        if rows:
            con.executemany("""
                UPDATE organizations
                SET ntee_code_classified = ?,
                    ntee_category_classified = ?,
                    ntee_confidence = ?,
                    ntee_reason = ?,
                    ntee_classified_at = current_timestamp
                WHERE ein = ?
            """, rows)
            total_classified += len(rows)

        time.sleep(SLEEP_BETWEEN_BATCHES)

    log.info(f"\nClassification complete: {total_classified:,} orgs classified, {errors} errors")


def print_report(con: duckdb.DuckDBPyConnection):
    print("\n" + "="*60)
    print("PHASE 3 NTEE CLASSIFICATION REPORT")
    print("="*60)

    print("\n--- Classification coverage ---")
    row = con.execute("""
        SELECT
            count(*) as total,
            count(ntee_code_classified) as classified,
            count(*) filter (where ntee_confidence = 'high') as high_conf,
            count(*) filter (where ntee_confidence = 'medium') as med_conf,
            count(*) filter (where ntee_confidence = 'low') as low_conf
        FROM organizations
    """).fetchone()
    print(f"  Total orgs:        {row[0]:>8,}")
    print(f"  Classified:        {row[1]:>8,}")
    print(f"  High confidence:   {row[2]:>8,}")
    print(f"  Medium confidence: {row[3]:>8,}")
    print(f"  Low confidence:    {row[4]:>8,}")

    print("\n--- Top classified categories ---")
    rows = con.execute("""
        SELECT ntee_code_classified, ntee_category_classified, count(*) as orgs
        FROM organizations
        WHERE ntee_code_classified IS NOT NULL
        GROUP BY ntee_code_classified, ntee_category_classified
        ORDER BY orgs DESC
        LIMIT 15
    """).fetchall()
    for r in rows:
        print(f"  {str(r[0]):<4} {str(r[1]):<45} {r[2]:>7,}")

    print("\n--- IRS vs Claude disagreements (sample) ---")
    rows = con.execute("""
        SELECT name, ntee_code, ntee_code_classified, ntee_reason
        FROM organizations
        WHERE ntee_code IS NOT NULL
          AND ntee_code_classified IS NOT NULL
          AND LEFT(ntee_code, 1) != ntee_code_classified
          AND ntee_confidence = 'high'
        LIMIT 15
    """).fetchall()
    for r in rows:
        print(f"  {str(r[0])[:45]:<45} | IRS:{r[1]} -> Claude:{r[2]} | {r[3]}")


def main():
    parser = argparse.ArgumentParser(description="DEJ Intelligence Phase 3 NTEE Classifier")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls or DB writes")
    parser.add_argument("--null-only", action="store_true", default=True, help="Only classify orgs with null NTEE (default)")
    parser.add_argument("--all", action="store_true", help="Classify all orgs including those with existing NTEE")
    parser.add_argument("--limit", type=int, help="Limit number of orgs to classify (for testing)")
    parser.add_argument("--report", action="store_true", help="Print report after classification")
    args = parser.parse_args()

    null_only = not args.all

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not found in environment. Check .env file.")
        return

    log.info("DEJ Intelligence — Phase 3 NTEE Classifier")
    log.info(f"Database: {DB_PATH}")
    if args.dry_run:
        log.info("Mode: DRY RUN")

    con = duckdb.connect(DB_PATH)

    if not args.dry_run:
        log.info("Applying schema migration...")
        con.execute(MIGRATION_SQL)

    client = anthropic.Anthropic(api_key=api_key)

    run_classifier(
        con=con,
        client=client,
        null_only=null_only,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    if args.report and not args.dry_run:
        print_report(con)

    con.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
