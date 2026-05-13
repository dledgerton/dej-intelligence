"""
DEJ Intelligence — Phase 2 Step 1: Officers Table Schema Migration

Adds the officers table and supporting indexes to the existing DuckDB database.
Run this once before the Part VII XML loader.

Usage:
    python scripts/duckdb/phase2_step1_schema.py
    python scripts/duckdb/phase2_step1_schema.py --reset   # drops + recreates officers table only

Tables added:
    officers            — one row per person per filing
    xml_index_cache     — tracks which IRS index files have been downloaded/processed
"""

import argparse
import os
import sys
from pathlib import Path

import duckdb


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_db_path() -> str:
    return os.environ.get(
        "DEJ_DB_PATH",
        str(Path(__file__).resolve().parents[2] / "data" / "dej_intelligence.duckdb"),
    )


# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

OFFICERS_SCHEMA = """
-- Tracks downloaded/processed IRS annual index files
create table if not exists xml_index_cache (
    id               integer primary key,
    index_year       smallint not null,
    downloaded_at    timestamp default current_timestamp,
    total_filings    integer,
    state_filings    integer,   -- count matching our 4-state filter
    status           text default 'complete'
                     check (status in ('complete','partial','error')),
    unique(index_year)
);

create sequence if not exists xml_index_cache_id_seq start 1;
alter table xml_index_cache alter column id set default nextval('xml_index_cache_id_seq');

-- Tracks which 990 XML files have been fetched and parsed
create table if not exists xml_filing_log (
    id               integer primary key,
    ein              text not null,
    tax_year         smallint not null,
    object_id        text not null,      -- IRS S3 ObjectId
    form_type        text not null,      -- 990, 990EZ, 990PF
    state_cd         text,
    fetched_at       timestamp default current_timestamp,
    parse_status     text default 'ok'
                     check (parse_status in ('ok','no_part7','parse_error','skip')),
    officer_rows     smallint default 0,
    error_msg        text,
    unique(object_id)
);

create sequence if not exists xml_filing_log_id_seq start 1;
alter table xml_filing_log alter column id set default nextval('xml_filing_log_id_seq');

-- One row per officer/director per filing
create table if not exists officers (
    id                       integer primary key,

    -- Filing identity
    ein                      text not null,
    tax_year                 smallint not null,
    object_id                text not null,       -- FK to xml_filing_log
    form_type                text not null,

    -- Person identity
    person_name              text not null,
    person_name_normalized   text,                -- uppercase, stripped punctuation
    title_raw                text,
    title_normalized         text,                -- uppercase, stripped

    -- Classification flags
    is_officer               boolean default false,
    is_key_employee          boolean default false,
    is_highest_comp          boolean default false,
    is_former                boolean default false,
    is_top_officer           boolean default false,  -- CEO/ED/President detection

    -- Time/hours
    hours_per_week           float,
    average_hours_related    float,

    -- Compensation (all integer cents stored as whole dollars)
    comp_reportable_org      integer,    -- Part VII col D
    comp_reportable_related  integer,    -- Part VII col E
    comp_other               integer,    -- Part VII col F
    comp_total               integer,    -- computed: D + E + F

    -- Metadata
    parsed_at                timestamp default current_timestamp,

    unique(object_id, person_name_normalized, title_normalized)
);

create sequence if not exists officers_id_seq start 1;
alter table officers alter column id set default nextval('officers_id_seq');

create index if not exists idx_officers_ein            on officers(ein);
create index if not exists idx_officers_ein_year       on officers(ein, tax_year);
create index if not exists idx_officers_top            on officers(ein, tax_year, is_top_officer);
create index if not exists idx_officers_name_norm      on officers(person_name_normalized);
create index if not exists idx_officers_object_id      on officers(object_id);
"""

# ---------------------------------------------------------------------------
# CEO tenure view — computed across filing years
# ---------------------------------------------------------------------------

TENURE_VIEW = """
create or replace view v_ceo_tenure as
with top_officers as (
    select
        ein,
        tax_year,
        person_name_normalized,
        title_normalized,
        comp_reportable_org,
        comp_total,
        row_number() over (
            partition by ein, tax_year
            order by comp_reportable_org desc nulls last
        ) as comp_rank
    from officers
    where is_top_officer = true
),
ranked as (
    select
        ein,
        tax_year,
        person_name_normalized as ceo_name,
        title_normalized       as ceo_title,
        comp_reportable_org    as ceo_comp,
        comp_total             as ceo_comp_total
    from top_officers
    where comp_rank = 1
),
with_lag as (
    select
        ein,
        tax_year,
        ceo_name,
        ceo_title,
        ceo_comp,
        ceo_comp_total,
        lag(ceo_name) over (partition by ein order by tax_year) as prev_ceo_name,
        lag(tax_year) over (partition by ein order by tax_year) as prev_tax_year
    from ranked
),
-- Mark year as "same CEO" = 1, "new CEO" = 0, gap = null
continuity as (
    select
        ein,
        tax_year,
        ceo_name,
        ceo_title,
        ceo_comp,
        ceo_comp_total,
        case
            when prev_ceo_name is null then 1                           -- first year in data
            when ceo_name = prev_ceo_name
                 and tax_year = prev_tax_year + 1 then 1                -- same CEO, consecutive year
            when tax_year = prev_tax_year + 1     then 0                -- new CEO, consecutive year
            else null                                                   -- gap year — skip
        end as same_ceo
    from with_lag
),
-- Assign tenure group: every leadership change resets the group
groups as (
    select
        ein,
        tax_year,
        ceo_name,
        ceo_title,
        ceo_comp,
        ceo_comp_total,
        same_ceo,
        sum(case when same_ceo = 0 or same_ceo is null then 1 else 0 end)
            over (partition by ein order by tax_year
                  rows between unbounded preceding and current row) as tenure_group
    from continuity
),
tenure_calc as (
    select
        ein,
        tax_year,
        ceo_name,
        ceo_title,
        ceo_comp,
        ceo_comp_total,
        tenure_group,
        -- count consecutive years in this tenure group up to this row
        count(*) over (
            partition by ein, tenure_group
            order by tax_year
            rows between unbounded preceding and current row
        ) as ceo_tenure_years,
        -- most recent year in our data for this org
        max(tax_year) over (partition by ein) as latest_year
    from groups
    where same_ceo is not null
)
select
    ein,
    tax_year,
    ceo_name,
    ceo_title,
    ceo_comp,
    ceo_comp_total,
    ceo_tenure_years,
    -- is this the most recent filing row for this org?
    (tax_year = latest_year) as is_current
from tenure_calc;
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 schema migration — officers table")
    parser.add_argument("--reset", action="store_true",
                        help="Drop officers tables before recreating (keeps organizations + filings intact)")
    args = parser.parse_args()

    db_path = get_db_path()
    print(f"Database: {db_path}")

    if not Path(db_path).exists():
        print("ERROR: DuckDB file not found. Run Phase 1 setup first.", file=sys.stderr)
        sys.exit(1)

    con = duckdb.connect(db_path)

    # Confirm Phase 1 tables exist
    tables = {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main'"
    ).fetchall()}

    if "organizations" not in tables or "filings" not in tables:
        print("ERROR: Phase 1 tables (organizations, filings) not found.", file=sys.stderr)
        sys.exit(1)

    if args.reset:
        print("Dropping Phase 2 tables...")
        for t in ["officers", "xml_filing_log", "xml_index_cache"]:
            con.execute(f"drop table if exists {t}")
        for seq in ["officers_id_seq", "xml_filing_log_id_seq", "xml_index_cache_id_seq"]:
            con.execute(f"drop sequence if exists {seq}")
        con.execute("drop view if exists v_ceo_tenure")
        print("  Dropped.")

    print("Creating Phase 2 schema...")
    con.execute(OFFICERS_SCHEMA)
    print("Creating CEO tenure view...")
    con.execute(TENURE_VIEW)

    # Report final state
    all_tables = sorted(r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main'"
    ).fetchall())
    all_views = sorted(r[0] for r in con.execute(
        "select table_name from information_schema.views where table_schema='main'"
    ).fetchall())

    print(f"\nTables:  {all_tables}")
    print(f"Views:   {all_views}")

    # Show row counts for existing Phase 1 data
    org_count = con.execute("select count(*) from organizations").fetchone()[0]
    fil_count  = con.execute("select count(*) from filings").fetchone()[0]
    print(f"\nPhase 1 data intact:")
    print(f"  organizations: {org_count:,}")
    print(f"  filings:       {fil_count:,}")

    con.close()
    print("\nPhase 2 schema migration complete.")


if __name__ == "__main__":
    main()
