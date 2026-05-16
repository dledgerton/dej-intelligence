import os
"""
DEJ Intelligence — Phase 2 Score Correction
============================================
Problem: XML filing coverage is sparse (meaningful data only 2019-2021).
Orgs appearing in only 1-2 XML years are getting high transition risk scores
based on artificially short tenure readings, not real leadership instability.

Fix:
1. Count XML years per EIN in officers table
2. Add coverage_years and tenure_confidence columns to transition_scores
3. Recalculate total_score_v2 discounting tenure points for low-coverage orgs
4. Set tier based on corrected score

Confidence tiers:
  HIGH   — 3+ XML years (tenure signal is reliable)
  MEDIUM — 2 XML years (tenure directionally useful, not definitive)
  LOW    — 1 XML year  (tenure signal is noise, discount heavily)

Run from project root:
  python3 scripts/phase2_score_correction.py
  python3 scripts/phase2_score_correction.py --dry-run
  python3 scripts/phase2_score_correction.py --report
"""

import argparse
import logging
import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DB_PATH = os.environ.get("DEJ_DB_PATH", "data/dej_intelligence.duckdb")

# Score tier thresholds (same as original scoring logic)
def score_to_tier(score: int) -> str:
    if score >= 80:
        return "imminent"
    elif score >= 60:
        return "elevated"
    elif score >= 40:
        return "watch"
    else:
        return "stable"

# Discount multipliers by confidence level
CONFIDENCE_MULTIPLIER = {
    "HIGH":   1.0,   # full tenure signal — 3+ years coverage
    "MEDIUM": 0.5,   # half weight — 2 years coverage
    "LOW":    0.0,   # zero tenure signal — 1 year coverage is noise
}

MIGRATION_SQL = """
-- Add coverage columns if they don't exist
ALTER TABLE transition_scores ADD COLUMN IF NOT EXISTS coverage_years SMALLINT DEFAULT 0;
ALTER TABLE transition_scores ADD COLUMN IF NOT EXISTS tenure_confidence VARCHAR DEFAULT 'LOW';
ALTER TABLE transition_scores ADD COLUMN IF NOT EXISTS score_corrected SMALLINT DEFAULT 0;
ALTER TABLE transition_scores ADD COLUMN IF NOT EXISTS tier_corrected VARCHAR DEFAULT 'stable';
ALTER TABLE transition_scores ADD COLUMN IF NOT EXISTS correction_applied BOOLEAN DEFAULT false;
"""

COVERAGE_QUERY = """
    SELECT ein, COUNT(DISTINCT tax_year) as xml_years
    FROM officers
    WHERE is_top_officer = true
    GROUP BY ein
"""

SCORES_QUERY = """
    SELECT ein, ceo_tenure_pts, ceo_comp_pts, total_score_v2,
           consecutive_deficit, score
    FROM transition_scores
    WHERE ceo_name IS NOT NULL
"""

def run_correction(con: duckdb.DuckDBPyConnection, dry_run: bool = False):
    log.info("Loading XML coverage per EIN...")
    coverage_rows = con.execute(COVERAGE_QUERY).fetchall()
    coverage = {row[0]: row[1] for row in coverage_rows}
    log.info(f"Coverage loaded for {len(coverage):,} EINs")

    log.info("Loading transition scores with officer data...")
    score_rows = con.execute(SCORES_QUERY).fetchall()
    log.info(f"Scores to evaluate: {len(score_rows):,}")

    updates = []
    confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    tier_changes = {"imminent->elevated": 0, "imminent->watch": 0,
                    "imminent->stable": 0, "elevated->watch": 0,
                    "elevated->stable": 0, "other": 0}

    for row in score_rows:
        ein, ceo_tenure_pts, ceo_comp_pts, total_score_v2, consec_deficit, score = row

        xml_years = coverage.get(ein, 0)

        # Assign confidence
        if xml_years >= 3:
            confidence = "HIGH"
        elif xml_years == 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        confidence_counts[confidence] += 1
        multiplier = CONFIDENCE_MULTIPLIER[confidence]

        # Recalculate score
        # tenure_pts and comp_pts are officer-derived — apply multiplier
        # consecutive_deficit and other financial signals are unaffected
        adjusted_tenure_pts = round((ceo_tenure_pts or 0) * multiplier)
        adjusted_comp_pts = round((ceo_comp_pts or 0) * multiplier)

        # Rebuild score: original score minus officer pts, plus adjusted officer pts
        original_officer_pts = (ceo_tenure_pts or 0) + (ceo_comp_pts or 0)
        adjusted_officer_pts = adjusted_tenure_pts + adjusted_comp_pts
        delta = adjusted_officer_pts - original_officer_pts

        corrected_score = max(0, min(99, (total_score_v2 or 0) + delta))
        corrected_tier = score_to_tier(corrected_score)
        original_tier = score_to_tier(total_score_v2 or 0)

        # Track tier changes
        if original_tier != corrected_tier:
            key = f"{original_tier}->{corrected_tier}"
            if key in tier_changes:
                tier_changes[key] += 1
            else:
                tier_changes["other"] += 1

        updates.append((
            xml_years,
            confidence,
            corrected_score,
            corrected_tier,
            True,
            ein
        ))

    log.info(f"\nConfidence distribution:")
    for k, v in confidence_counts.items():
        log.info(f"  {k}: {v:,} orgs")

    log.info(f"\nTier changes (original -> corrected):")
    for k, v in tier_changes.items():
        if v > 0:
            log.info(f"  {k}: {v:,}")

    if dry_run:
        log.info("\nDRY RUN — no changes written to database")
        return

    log.info(f"\nWriting {len(updates):,} corrections to transition_scores...")

    # Batch update using a temp table for performance
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _score_corrections ("
                "  ein VARCHAR, coverage_years SMALLINT, tenure_confidence VARCHAR,"
                "  score_corrected SMALLINT, tier_corrected VARCHAR, correction_applied BOOLEAN"
                ")")
    con.execute("DELETE FROM _score_corrections")
    con.executemany(
        "INSERT INTO _score_corrections VALUES (?, ?, ?, ?, ?, ?)",
        [(r[5], r[0], r[1], r[2], r[3], r[4]) for r in updates]
    )

    con.execute("""
        UPDATE transition_scores ts
        SET
            coverage_years      = c.coverage_years,
            tenure_confidence   = c.tenure_confidence,
            score_corrected     = c.score_corrected,
            tier_corrected      = c.tier_corrected,
            correction_applied  = c.correction_applied
        FROM _score_corrections c
        WHERE ts.ein = c.ein
    """)

    updated = con.execute(
        "SELECT count(*) FROM transition_scores WHERE correction_applied = true"
    ).fetchone()[0]
    log.info(f"Updated {updated:,} rows")


def print_report(con: duckdb.DuckDBPyConnection):
    print("\n" + "="*60)
    print("SCORE CORRECTION REPORT")
    print("="*60)

    print("\n--- Confidence distribution ---")
    rows = con.execute("""
        SELECT tenure_confidence, count(*) as orgs
        FROM transition_scores
        WHERE correction_applied = true
        GROUP BY tenure_confidence
        ORDER BY orgs DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<8} {r[1]:>8,} orgs")

    print("\n--- Tier: original vs corrected ---")
    rows = con.execute("""
        SELECT
            tier_corrected,
            count(*) as orgs_corrected
        FROM transition_scores
        WHERE correction_applied = true
        GROUP BY tier_corrected
        ORDER BY orgs_corrected DESC
    """).fetchall()
    print("  Corrected tiers:")
    for r in rows:
        print(f"    {r[0]:<12} {r[1]:>8,}")

    print("\n--- Sample HIGH confidence imminent orgs (reliable signal) ---")
    rows = con.execute("""
        SELECT o.name, ts.ceo_name, ts.ceo_tenure_years,
               ts.coverage_years, ts.score_corrected, ts.tier_corrected
        FROM transition_scores ts
        JOIN organizations o ON ts.ein = o.ein
        WHERE ts.tenure_confidence = 'HIGH'
          AND ts.tier_corrected = 'imminent'
        ORDER BY ts.score_corrected DESC
        LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"  {r[0][:40]:<40} | CEO: {str(r[1])[:25]:<25} | "
              f"tenure: {r[2]} yrs | xml_yrs: {r[3]} | score: {r[4]} | {r[5]}")

    print("\n--- Sample LOW confidence that were flagged imminent (now corrected) ---")
    rows = con.execute("""
        SELECT o.name, ts.ceo_name, ts.ceo_tenure_years,
               ts.coverage_years, ts.total_score_v2, ts.score_corrected, ts.tier_corrected
        FROM transition_scores ts
        JOIN organizations o ON ts.ein = o.ein
        WHERE ts.tenure_confidence = 'LOW'
          AND ts.total_score_v2 >= 80
        ORDER BY ts.total_score_v2 DESC
        LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"  {r[0][:40]:<40} | CEO: {str(r[1])[:20]:<20} | "
              f"xml_yrs: {r[3]} | was: {r[4]} -> now: {r[5]} ({r[6]})")


def main():
    parser = argparse.ArgumentParser(description="DEJ Intelligence Phase 2 Score Correction")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calculate corrections without writing to DB")
    parser.add_argument("--report", action="store_true",
                        help="Print summary report after correction")
    args = parser.parse_args()

    log.info("DEJ Intelligence — Phase 2 Score Correction")
    log.info(f"Database: {DB_PATH}")
    if args.dry_run:
        log.info("Mode: DRY RUN")

    con = duckdb.connect(DB_PATH)

    # Check prerequisites
    tables = {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main'"
    ).fetchall()}

    for required in ("officers", "transition_scores", "organizations"):
        if required not in tables:
            log.error(f"Required table '{required}' not found. Cannot proceed.")
            con.close()
            return

    if not args.dry_run:
        log.info("Applying schema migration...")
        con.execute(MIGRATION_SQL)

    run_correction(con, dry_run=args.dry_run)

    if args.report and not args.dry_run:
        print_report(con)

    con.close()
    log.info("\nDone.")


if __name__ == "__main__":
    main()
