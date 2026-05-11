"""
DEJ Intelligence — Phase 1 Step 3: Transition Signal Layer

Builds the signal layer on top of BMF (organizations) + NCCS Core (filings)
in DuckDB. Three DuckDB views compute the financial signals; a materialization
function writes scored rows to the transition_scores table.

Computable from NCCS Core data (Phase 1):
  - revenue_trend:       3-year CAGR on total_revenue
  - comp_trajectory:     3-year % change on comp_employees
  - deficit_years:       consecutive years where expenses > revenue

Deferred until Phase 2 (requires 990 XML officer data):
  - ceo_tenure_years, board_chair_change, signal_leadership, signal_search_rfp

Scoring model (100-point scale, Phase 1 factors only):
  - revenue_trend_points:   0-25
  - comp_trajectory_points: 0-15
  - deficit_years_points:   0-30
  Phase 1 max: 70 pts. Remaining 30 reserved for Phase 2.
  Tier thresholds (Phase 1): low 0-19 / elevated 20-39 / high 40-54 / imminent 55+

Run:
    python scripts/duckdb/compute_signals.py                   # score all orgs
    python scripts/duckdb/compute_signals.py --dry-run         # compute, no DB writes
    python scripts/duckdb/compute_signals.py --ein 410706172   # single org
    python scripts/duckdb/compute_signals.py --validate-only   # known_orgs check only
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

import duckdb
from dotenv import load_dotenv

DEFAULT_DB_PATH = "data/dej_intelligence.duckdb"

# ---------------------------------------------------------------------------
# Scoring model
# ---------------------------------------------------------------------------

TIER_THRESHOLDS = [
    ("imminent", 55),
    ("high",     40),
    ("elevated", 20),
    ("low",      0),
]


def assign_tier(score: int) -> str:
    for tier, threshold in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "low"


def score_revenue_trend(cagr: float | None) -> tuple[int, str]:
    if cagr is None:
        return 0, "unknown"
    if cagr <= -0.30:
        return 25, "steep_decline"
    elif cagr <= -0.15:
        return 20, "decline"
    elif cagr <= -0.05:
        return 12, "soft_decline"
    elif cagr <= 0.05:
        return 5, "flat"
    elif cagr <= 0.15:
        return 2, "growth"
    else:
        return 0, "strong_growth"


def score_comp_trajectory(pct: float | None) -> tuple[int, str]:
    if pct is None:
        return 0, "unknown"
    if pct <= -0.20:
        return 15, "declining"
    elif pct <= -0.05:
        return 10, "softening"
    elif pct <= 0.05:
        return 8, "flat"
    elif pct <= 0.20:
        return 3, "growing"
    else:
        return 0, "strong_growth"


def score_deficit_years(consecutive: int) -> int:
    if consecutive >= 3:
        return 30
    elif consecutive == 2:
        return 20
    elif consecutive == 1:
        return 10
    return 0


# ---------------------------------------------------------------------------
# SQL views
# ---------------------------------------------------------------------------

VIEWS_SQL = """
drop view if exists v_org_signals;
drop view if exists v_consecutive_deficits;
drop view if exists v_filing_trends;

-- ── v_filing_trends ────────────────────────────────────────────────────────
-- Most-recent non-partial filing row per org, with 3-year trend metrics.
-- Requires at least 2 years of data.
-- ─────────────────────────────────────────────────────────────────────────
create view v_filing_trends as
with
deduped as (
    -- When same (ein, tax_year) appears in multiple sources, keep one row:
    -- prefer latest period_end, then highest revenue.
    select *,
           row_number() over (
               partition by ein, tax_year
               order by period_end desc nulls last, total_revenue desc nulls last
           ) as rn
    from filings
    where partial_year = false
      and total_revenue is not null
),
clean as (
    select ein, tax_year, total_revenue, total_expenses, comp_employees, period_end
    from deduped
    where rn = 1
),
windowed as (
    select
        ein,
        tax_year,
        total_revenue,
        total_expenses,
        comp_employees,
        -- prior year values
        lag(total_revenue)  over w as prev_revenue,
        lag(comp_employees) over w as prev_comp,
        -- 3-year-ago anchor (offset 2 = 3 data points back from current)
        lag(total_revenue, 2)  over w as revenue_2yr_ago,
        lag(comp_employees, 2) over w as comp_2yr_ago,
        count(*)     over (partition by ein)      as years_of_data,
        max(tax_year) over (partition by ein)     as most_recent_year
    from clean
    window w as (partition by ein order by tax_year)
)
select
    ein,
    tax_year,
    total_revenue,
    total_expenses,
    comp_employees,
    years_of_data,
    most_recent_year,
    -- YoY revenue
    case when prev_revenue > 0
         then (total_revenue - prev_revenue) / prev_revenue
    end as revenue_yoy_pct,
    -- 3-year CAGR: (most_recent / 2yr_ago)^(1/2) - 1
    -- We use 2 lags (3 data points = 2 intervals) → ^(1/2)
    case when revenue_2yr_ago > 0 and total_revenue is not null
         then power(total_revenue / revenue_2yr_ago, 0.5) - 1.0
    end as revenue_cagr_3yr,
    -- 3-year comp change (simple %)
    case when comp_2yr_ago > 0 and comp_employees is not null
         then (comp_employees - comp_2yr_ago) / comp_2yr_ago
    end as comp_pct_change_3yr,
    -- Deficit flag
    case when total_expenses > total_revenue then true else false end as is_deficit_year
from windowed
where tax_year = most_recent_year
  and years_of_data >= 2
;

-- ── v_consecutive_deficits ────────────────────────────────────────────────
-- Consecutive deficit years at the trailing edge (ending at most recent year).
-- Avoids nested window-in-aggregate by computing the streak in Python.
-- This view provides the raw per-org per-year deficit flags; streak counting
-- happens in compute_deficit_streaks() below.
-- ─────────────────────────────────────────────────────────────────────────
create view v_consecutive_deficits as
with
deduped as (
    select *,
           row_number() over (
               partition by ein, tax_year
               order by period_end desc nulls last, total_revenue desc nulls last
           ) as rn
    from filings
    where partial_year = false
      and total_revenue is not null
      and total_expenses is not null
),
clean as (
    select ein, tax_year, total_revenue, total_expenses
    from deduped
    where rn = 1
),
flags as (
    select
        ein,
        tax_year,
        case when total_expenses > total_revenue then 1 else 0 end as is_deficit,
        max(tax_year) over (partition by ein) as most_recent_year
    from clean
)
select ein, tax_year, is_deficit, most_recent_year
from flags
where tax_year >= most_recent_year - 4   -- look back max 5 years
order by ein, tax_year desc
;

-- ── v_org_signals ─────────────────────────────────────────────────────────
-- Joins org metadata + filing trends. Deficit streak added in Python.
-- ─────────────────────────────────────────────────────────────────────────
create view v_org_signals as
select
    o.ein,
    o.name,
    o.state,
    o.city,
    o.subsection_code,
    o.ntee_code,
    o.ntee_category,
    o.status,
    t.tax_year                as most_recent_tax_year,
    t.total_revenue           as most_recent_revenue,
    t.total_expenses          as most_recent_expenses,
    t.comp_employees          as most_recent_comp,
    t.years_of_data,
    t.revenue_yoy_pct,
    t.revenue_cagr_3yr,
    t.comp_pct_change_3yr,
    t.is_deficit_year         as most_recent_is_deficit
from organizations o
join v_filing_trends t on t.ein = o.ein
where o.status = 'active'
;
"""

TRANSITION_SCORES_TABLE = """
create sequence if not exists transition_scores_id_seq start 1;

create table if not exists transition_scores (
  id                  bigint primary key default nextval('transition_scores_id_seq'),
  ein                 varchar(9) not null references organizations(ein),
  scored_at           date not null,
  score               smallint not null check (score between 0 and 100),
  tier                text not null
                      check (tier in ('low','elevated','high','imminent')),
  factors             json not null,
  consecutive_deficit smallint,
  ceo_tenure_years    numeric(4,1),
  board_chair_change  boolean,
  created_at          timestamp default now(),
  unique(ein, scored_at)
);

create index if not exists idx_scores_ein       on transition_scores(ein, scored_at desc);
create index if not exists idx_scores_high      on transition_scores(scored_at desc, score desc);
create index if not exists idx_scores_tier      on transition_scores(tier, scored_at desc);
"""

# ---------------------------------------------------------------------------
# Deficit streak computation (Python, avoids DuckDB window-in-aggregate limit)
# ---------------------------------------------------------------------------

def compute_deficit_streaks(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """
    For each org, count consecutive deficit years ending at the most recent year.
    Walks the deficit flag list from most-recent backward and stops at the first
    non-deficit year.
    Returns {ein: consecutive_deficit_count}.
    """
    rows = con.execute(
        "select ein, tax_year, is_deficit from v_consecutive_deficits order by ein, tax_year desc"
    ).fetchall()

    streaks: dict[str, int] = {}
    current_ein = None
    streak = 0
    streak_broken = False

    for ein, _yr, is_deficit in rows:
        if ein != current_ein:
            # Save previous org
            if current_ein is not None:
                streaks[current_ein] = streak
            # Start new org
            current_ein = ein
            streak = 0
            streak_broken = False

        if not streak_broken:
            if is_deficit:
                streak += 1
            else:
                streak_broken = True  # stop counting; non-deficit year breaks the run

    # Save last org
    if current_ein is not None:
        streaks[current_ein] = streak

    return streaks


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def setup(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(VIEWS_SQL)
    con.execute(TRANSITION_SCORES_TABLE)


def score_row(row: dict, deficit_streak: int) -> dict:
    rev_pts, rev_label = score_revenue_trend(row["revenue_cagr_3yr"])
    comp_pts, comp_label = score_comp_trajectory(row["comp_pct_change_3yr"])
    def_pts = score_deficit_years(deficit_streak)

    total = min(100, rev_pts + comp_pts + def_pts)
    tier = assign_tier(total)

    factors = {
        "revenue_trend": {
            "value": round(float(row["revenue_cagr_3yr"]), 4)
                     if row["revenue_cagr_3yr"] is not None else None,
            "label": rev_label,
            "points": rev_pts,
        },
        "comp_trajectory": {
            "value": round(float(row["comp_pct_change_3yr"]), 4)
                     if row["comp_pct_change_3yr"] is not None else None,
            "label": comp_label,
            "points": comp_pts,
        },
        "deficit_years": {
            "value": deficit_streak,
            "points": def_pts,
        },
        "ceo_tenure":         {"value": None, "points": 0},
        "board_chair_change": {"value": None, "points": 0},
        "signal_leadership":  {"value": None, "points": 0},
        "signal_search_rfp":  {"value": None, "points": 0},
    }

    return {
        "ein":                row["ein"],
        "scored_at":          date.today().isoformat(),
        "score":              total,
        "tier":               tier,
        "factors":            json.dumps(factors),
        "consecutive_deficit": deficit_streak,
        "ceo_tenure_years":   None,
        "board_chair_change": None,
    }


def score_all(
    con: duckdb.DuckDBPyConnection,
    dry_run: bool = False,
    ein_filter: str | None = None,
) -> list[dict]:
    where = f"where ein = '{ein_filter}'" if ein_filter else ""
    rows = con.execute(f"select * from v_org_signals {where}").fetchall()
    cols = [d[0] for d in con.description]

    print(f"  Computing deficit streaks...")
    streaks = compute_deficit_streaks(con)

    scored = []
    for raw in rows:
        row = dict(zip(cols, raw))
        streak = streaks.get(row["ein"], 0)
        scored.append(score_row(row, streak))

    if not dry_run and scored:
        insert_cols = [
            "ein", "scored_at", "score", "tier", "factors",
            "consecutive_deficit", "ceo_tenure_years", "board_chair_change"
        ]
        placeholders = ", ".join(["?"] * len(insert_cols))
        col_list = ", ".join(insert_cols)
        update_set = ", ".join(
            f"{c} = excluded.{c}"
            for c in insert_cols
            if c not in ("ein", "scored_at")
        )
        sql = (
            f"insert into transition_scores ({col_list}) "
            f"values ({placeholders}) "
            f"on conflict (ein, scored_at) do update set {update_set}"
        )
        batch = [tuple(s.get(c) for c in insert_cols) for s in scored]
        con.executemany(sql, batch)

    return scored


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary(scored: list[dict]) -> None:
    from collections import Counter
    tier_counts = Counter(s["tier"] for s in scored)
    total = len(scored)

    print(f"\n{'='*60}")
    print("TRANSITION SIGNAL SCORE SUMMARY")
    print(f"{'='*60}")
    print(f"  Orgs scored: {total:,}")
    print(f"\n  By tier:")
    for tier in ["imminent", "high", "elevated", "low"]:
        n = tier_counts.get(tier, 0)
        pct = n / total * 100 if total else 0
        bar = "█" * max(1, int(pct / 2))
        print(f"    {tier:10s}: {n:6,}  ({pct:5.1f}%)  {bar}")
    print()


def validate_known_orgs(con: duckdb.DuckDBPyConnection, scored: list[dict]) -> None:
    known_path = Path("scripts/validation/known_orgs.json")
    if not known_path.exists():
        print("known_orgs.json not found — skipping validation")
        return

    with open(known_path) as f:
        known = json.load(f)

    scored_by_ein = {s["ein"]: s for s in scored}

    print(f"{'='*60}")
    print("KNOWN ORGS VALIDATION")
    print(f"{'='*60}")

    for org in known["orgs"]:
        ein = org["ein"]
        name = org["name"]
        state = org.get("expected_state", "?")
        size = org.get("size_bucket", "?")

        filings = con.execute(
            "select tax_year, total_revenue, total_expenses "
            "from filings where ein = ? and partial_year = false "
            "order by tax_year",
            [ein]
        ).fetchall()

        s = scored_by_ein.get(ein)
        print(f"\n  {name} ({ein})  [{state}, {size}]")

        if not filings:
            print(f"    ⚠  No filings found in NCCS data")
            continue

        for yr, rev, exp in filings:
            deficit_flag = " ← deficit" if exp and rev and exp > rev else ""
            rev_str = f"${rev:>12,.0f}" if rev is not None else "          null"
            print(f"    {yr}  rev {rev_str}{deficit_flag}")

        if not s:
            print(f"    ⚠  Not scored (need ≥2 full years)")
            continue

        f = json.loads(s["factors"])
        print(f"\n    Score: {s['score']}/100  →  {s['tier'].upper()}")
        print(f"    Revenue CAGR (3yr) : {f['revenue_trend']['label']}  "
              f"({f['revenue_trend']['value'] or 'n/a'})  "
              f"+{f['revenue_trend']['points']}pts")
        print(f"    Comp trajectory    : {f['comp_trajectory']['label']}  "
              f"({f['comp_trajectory']['value'] or 'n/a'})  "
              f"+{f['comp_trajectory']['points']}pts")
        print(f"    Deficit streak     : {f['deficit_years']['value']} yrs  "
              f"+{f['deficit_years']['points']}pts")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="DEJ Intelligence — compute transition signal scores")
    p.add_argument("--dry-run",       action="store_true", help="Compute but don't write to DB")
    p.add_argument("--ein",           default=None,        help="Score a single EIN")
    p.add_argument("--validate-only", action="store_true", help="Re-run known_orgs check only")
    args = p.parse_args()

    load_dotenv(".env.local")
    db_path = os.environ.get("DEJ_DUCKDB_PATH") or DEFAULT_DB_PATH
    print(f"Database: {db_path}")
    con = duckdb.connect(db_path)

    setup(con)

    if args.validate_only:
        existing = con.execute("select * from transition_scores").fetchall()
        if not existing:
            print("No scores in DB — run without --validate-only first")
            con.close()
            return
        cols = [d[0] for d in con.description]
        scored = [dict(zip(cols, r)) for r in existing]
        validate_known_orgs(con, scored)
        con.close()
        return

    print("Scoring orgs from v_org_signals...")
    scored = score_all(con, dry_run=args.dry_run, ein_filter=args.ein)

    print_summary(scored)
    validate_known_orgs(con, scored)

    if not args.dry_run and not args.ein:
        n = con.execute("select count(*) from transition_scores").fetchone()[0]
        print(f"transition_scores table: {n:,} rows written")
    elif args.dry_run:
        print("  DRY RUN — nothing written to transition_scores\n")

    con.close()


if __name__ == "__main__":
    main()
