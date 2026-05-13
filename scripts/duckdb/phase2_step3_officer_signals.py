"""
DEJ Intelligence — Phase 2 Step 3: Signal Layer Update (Officer Signals)

Extends the existing transition_scores table with Phase 2 signals derived
from the officers table:
  - ceo_tenure_years:    How long the current CEO has been in the role
  - ceo_comp_percentile: Where the CEO's comp sits vs peers in same NTEE group
  - signal_leadership:   Boolean — leadership transition likely within 2 yrs
  - ceo_tenure_pts:      Score contribution (0-20)
  - ceo_comp_pts:        Score contribution (0-10)

After this script, transition_scores reaches the full 100-point model:
  Phase 1 max: 70 pts  (revenue_trend, comp_trajectory, deficit_years)
  Phase 2 adds: 30 pts (ceo_tenure, ceo_comp, board signals TBD)

Usage:
    # Preview scores without writing
    python scripts/duckdb/phase2_step3_officer_signals.py --dry-run

    # Compute and update all orgs
    python scripts/duckdb/phase2_step3_officer_signals.py

    # Single org
    python scripts/duckdb/phase2_step3_officer_signals.py --ein 521693895

    # Show distribution of results
    python scripts/duckdb/phase2_step3_officer_signals.py --report
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import duckdb

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dej.phase2.signals")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TENURE_SCORE_TABLE = [
    (0,   1,  20),
    (2,   2,  15),
    (3,   4,  10),
    (5,   6,   8),
    (7,  10,  12),
    (11,  14, 16),
    (15, 999, 20),
]


def tenure_to_points(years) -> int:
    if years is None:
        return 5
    try:
        years = float(years)
    except (TypeError, ValueError):
        return 5
    for min_y, max_y, pts in TENURE_SCORE_TABLE:
        if min_y <= years <= max_y:
            return pts
    return 5


def comp_pct_to_points(pct) -> int:
    if pct is None:
        return 3
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return 3
    if pct >= 90:  return 8
    if pct >= 75:  return 5
    if pct >= 25:  return 3
    if pct >= 10:  return 6
    return 9


def get_db_path() -> str:
    return os.environ.get(
        "DEJ_DB_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "dej_intelligence.duckdb"),
    )


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

MIGRATION_SQL = """
alter table transition_scores add column if not exists ceo_name           text;
alter table transition_scores add column if not exists ceo_tenure_years   float;
alter table transition_scores add column if not exists ceo_comp           integer;
alter table transition_scores add column if not exists ceo_comp_pct_ntee  float;
alter table transition_scores add column if not exists ceo_tenure_pts     smallint default 0;
alter table transition_scores add column if not exists ceo_comp_pts       smallint default 0;
alter table transition_scores add column if not exists officer_data_yrs   smallint default 0;
alter table transition_scores add column if not exists signal_leadership  boolean default false;
alter table transition_scores add column if not exists total_score_v2     smallint default 0;
"""

# ---------------------------------------------------------------------------
# Peer comp percentile table
# ---------------------------------------------------------------------------

PEER_COMP_SQL = """
create or replace table t_peer_comp as
with ceo_current as (
    select
        o.ein,
        o.ceo_comp        as comp,
        orgs.ntee_code,
        left(orgs.ntee_code, 1) as ntee_major
    from v_ceo_tenure o
    join organizations orgs using (ein)
    where o.is_current = true
      and o.ceo_comp > 0
      and orgs.ntee_code is not null
),
with_pct as (
    select
        ein, comp, ntee_major,
        round(
            percent_rank() over (
                partition by ntee_major
                order by comp
            ) * 100, 1
        ) as comp_pct
    from ceo_current
)
select ein, comp, ntee_major, comp_pct from with_pct
"""


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def run_signals(con: duckdb.DuckDBPyConnection,
                dry_run: bool = False,
                ein_filter: str | None = None) -> dict:

    stats = {
        "orgs_with_officer_data": 0,
        "orgs_scored": 0,
        "orgs_missing_officer_data": 0,
        "leadership_signals": 0,
    }

    # Build WHERE clause for optional single-EIN filter
    ein_where = f"and t.ein = '{ein_filter}'" if ein_filter else ""

    # Build peer comp percentiles
    log.info("Computing peer comp percentiles by NTEE major category...")
    con.execute(PEER_COMP_SQL)
    peer_count = con.execute("select count(*) from t_peer_comp").fetchone()[0]
    log.info(f"  Orgs with comp percentile: {peer_count:,}")

    # Pull CEO tenure for current year
    tenure_rows = con.execute(f"""
        select
            t.ein,
            t.ceo_name,
            t.ceo_tenure_years,
            t.ceo_comp,
            t.ceo_comp_total,
            p.comp_pct,
            count(*) over (partition by t.ein) as data_years
        from v_ceo_tenure t
        left join t_peer_comp p using (ein)
        where t.is_current = true
        {ein_where}
        order by t.ein
    """).fetchall()

    stats["orgs_with_officer_data"] = len(tenure_rows)
    log.info(f"Orgs with CEO tenure data: {len(tenure_rows):,}")

    if dry_run:
        log.info("\nDRY RUN — sample scores:")
        log.info(f"{'EIN':>12}  {'CEO Name':<30}  {'Tenure':>6}  {'Pts':>4}  {'CompPct':>7}  {'Leadership':>10}")
        log.info("-" * 80)
        for row in tenure_rows[:20]:
            ein, name, tenure, comp, comp_total, comp_pct, data_yrs = row
            tenure_pts = tenure_to_points(tenure)
            comp_pts   = comp_pct_to_points(comp_pct)
            is_lead    = tenure is not None and (float(tenure) <= 2 or float(tenure) >= 11)
            log.info(
                f"{ein:>12}  {(name or 'UNKNOWN'):<30}  "
                f"{(str(round(float(tenure), 1)) if tenure else 'N/A'):>6}  "
                f"{tenure_pts:>4}  "
                f"{(str(round(float(comp_pct), 0)) if comp_pct else 'N/A'):>7}  "
                f"{'YES' if is_lead else 'no':>10}"
            )
        return stats

    # Update transition_scores
    log.info("Updating transition_scores with Phase 2 signals...")

    updated = 0
    for row in tenure_rows:
        ein, ceo_name, tenure_yrs, ceo_comp, comp_total, comp_pct, data_yrs = row

        tenure_yrs_f = float(tenure_yrs) if tenure_yrs is not None else None
        comp_pct_f   = float(comp_pct) if comp_pct is not None else None

        tenure_pts = tenure_to_points(tenure_yrs_f)
        comp_pts   = comp_pct_to_points(comp_pct_f)

        is_leadership = (
            tenure_yrs_f is not None and (tenure_yrs_f <= 2 or tenure_yrs_f >= 11)
        )

        try:
            con.execute("""
                update transition_scores
                set
                    ceo_name           = ?,
                    ceo_tenure_years   = ?,
                    ceo_comp           = ?,
                    ceo_comp_pct_ntee  = ?,
                    ceo_tenure_pts     = ?,
                    ceo_comp_pts       = ?,
                    officer_data_yrs   = ?,
                    signal_leadership  = ?,
                    total_score_v2     = coalesce(score, 0) + ? + ?
                where ein = ?
            """, [
                ceo_name,
                tenure_yrs_f,
                int(ceo_comp) if ceo_comp else (int(comp_total) if comp_total else None),
                comp_pct_f,
                tenure_pts,
                comp_pts,
                int(data_yrs) if data_yrs else 0,
                is_leadership,
                tenure_pts,
                comp_pts,
                ein,
            ])
            updated += 1
            if is_leadership:
                stats["leadership_signals"] += 1
        except Exception as e:
            log.debug(f"Update error for {ein}: {e}")

    stats["orgs_scored"] = updated

    missing = con.execute("""
        select count(*) from transition_scores
        where officer_data_yrs = 0 or officer_data_yrs is null
    """).fetchone()[0]
    stats["orgs_missing_officer_data"] = missing

    log.info(f"\nSignal update complete:")
    log.info(f"  Orgs scored:              {stats['orgs_scored']:,}")
    log.info(f"  Leadership signals:       {stats['leadership_signals']:,}")
    log.info(f"  Missing officer data:     {stats['orgs_missing_officer_data']:,}")

    return stats


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(con: duckdb.DuckDBPyConnection) -> None:

    log.info("\n" + "="*60)
    log.info("PHASE 2 SIGNAL DISTRIBUTION REPORT")
    log.info("="*60)

    dist = con.execute("""
        select
            case
                when total_score_v2 >= 80 then 'CRITICAL   (80-100)'
                when total_score_v2 >= 60 then 'HIGH       (60-79)'
                when total_score_v2 >= 40 then 'ELEVATED   (40-59)'
                else                           'LOW        (0-39)'
            end as band,
            count(*) as orgs,
            round(count(*) * 100.0 / sum(count(*)) over (), 1) as pct
        from transition_scores
        where total_score_v2 > 0
        group by 1
        order by min(total_score_v2) desc
    """).fetchall()

    log.info("\nFull 100-pt Score Distribution:")
    for band, orgs, pct in dist:
        log.info(f"  {band}  {orgs:>6,} orgs  ({pct}%)")

    tenure_dist = con.execute("""
        select
            case
                when ceo_tenure_years is null then 'Unknown'
                when ceo_tenure_years <= 2    then '0-2 yrs (new)'
                when ceo_tenure_years <= 6    then '3-6 yrs (productive)'
                when ceo_tenure_years <= 10   then '7-10 yrs (mature)'
                when ceo_tenure_years <= 14   then '11-14 yrs (long)'
                else                               '15+ yrs (very long)'
            end as band,
            count(*) as orgs
        from transition_scores
        group by 1
        order by min(coalesce(ceo_tenure_years, 999))
    """).fetchall()

    log.info("\nCEO Tenure Distribution:")
    for band, orgs in tenure_dist:
        log.info(f"  {band:<25} {orgs:>6,} orgs")

    lead_count = con.execute(
        "select count(*) from transition_scores where signal_leadership = true"
    ).fetchone()[0]
    log.info(f"\nLeadership transition signals: {lead_count:,} orgs")

    top10 = con.execute("""
        select
            ts.ein,
            o.name,
            o.state,
            ts.total_score_v2,
            ts.ceo_name,
            ts.ceo_tenure_years,
            ts.ceo_tenure_pts,
            ts.ceo_comp_pts
        from transition_scores ts
        join organizations o using (ein)
        where ts.total_score_v2 > 0
        order by ts.total_score_v2 desc
        limit 10
    """).fetchall()

    log.info(f"\nTop 10 Highest-Scored Orgs (Full 100-pt Model):")
    log.info(f"{'EIN':>12}  {'Name':<40}  {'St':>2}  {'Score':>5}  {'CEO':<25}  {'Tenure':>6}")
    log.info("-" * 100)
    for row in top10:
        ein, name, state, score, ceo, tenure, t_pts, c_pts = row
        log.info(
            f"{ein:>12}  {(name or '')[:40]:<40}  {(state or ''):>2}  "
            f"{(score or 0):>5}  {(ceo or 'N/A')[:25]:<25}  "
            f"{(str(round(float(tenure), 1)) if tenure else 'N/A'):>6}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2 Step 3: Compute and apply officer signals"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview scores without writing")
    parser.add_argument("--ein", type=str,
                        help="Process only this EIN")
    parser.add_argument("--report", action="store_true",
                        help="Print distribution report after scoring")
    args = parser.parse_args()

    db_path = get_db_path()
    log.info(f"Database: {db_path}")

    if not Path(db_path).exists():
        log.error("DuckDB file not found.")
        sys.exit(1)

    con = duckdb.connect(db_path)

    tables = {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main'"
    ).fetchall()}
    views = {r[0] for r in con.execute(
        "select table_name from information_schema.views where table_schema='main'"
    ).fetchall()}

    if "officers" not in tables:
        log.error("Officers table not found. Run Phase 2 Steps 1 + 2 first.")
        sys.exit(1)
    if "transition_scores" not in tables:
        log.error("transition_scores not found. Run Phase 1 signal computation first.")
        sys.exit(1)
    if "v_ceo_tenure" not in views:
        log.error("v_ceo_tenure view not found. Run phase2_step1_schema.py first.")
        sys.exit(1)

    officer_count = con.execute("select count(*) from officers").fetchone()[0]
    if officer_count == 0:
        log.error("No officer data found. Run phase2_step2_load_990_xml.py first.")
        sys.exit(1)

    log.info(f"Officers in database: {officer_count:,}")

    if not args.dry_run:
        log.info("Applying Phase 2 schema migration to transition_scores...")
        con.execute(MIGRATION_SQL)

    stats = run_signals(con, dry_run=args.dry_run, ein_filter=args.ein)

    if args.report and not args.dry_run:
        print_report(con)

    con.close()
    log.info("\nPhase 2 Step 3 complete.")


if __name__ == "__main__":
    main()
