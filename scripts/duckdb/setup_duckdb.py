"""
DuckDB schema setup for DEJ Intelligence PoC.
Mirrors Supabase schema (organizations + filings) for clean migration back later.
SaaS tables (user_profiles, watchlists, briefs, etc.) stay in Supabase.
"""

from __future__ import annotations
import argparse, os
from pathlib import Path
import duckdb
from dotenv import load_dotenv

DEFAULT_DB_PATH = "data/dej_intelligence.duckdb"


def get_db_path() -> str:
    load_dotenv(".env.local")
    return os.environ.get("DEJ_DUCKDB_PATH") or DEFAULT_DB_PATH


SCHEMA_SQL = """
create table if not exists organizations (
  ein              varchar(9) primary key,
  name             text not null,
  dba              text,
  address_line1    text,
  address_line2    text,
  city             text,
  state            varchar(2),
  zip              text,
  country          varchar(2) default 'US',
  ntee_code        text,
  ntee_category    text,
  subsection_code  smallint,
  ruling_year      smallint,
  deductibility    text,
  filing_required  boolean,
  status           text default 'active'
                   check (status in ('active','revoked','merged','terminated')),
  revoked_at       date,
  last_filing_year smallint,
  last_filing_date date,
  in_care_of            text,
  street                text,
  fiscal_year_end_month smallint,
  ruling_date           text,
  asset_code            smallint,
  income_code           smallint,
  asset_amount          bigint,
  income_amount         bigint,
  revenue_amount        bigint,
  source                text default 'manual',
  last_synced_at        timestamp default current_timestamp,
  created_at            timestamp default current_timestamp,
  updated_at            timestamp default current_timestamp
);

create index if not exists idx_orgs_state       on organizations(state);
create index if not exists idx_orgs_ntee        on organizations(ntee_code);
create index if not exists idx_orgs_subsection  on organizations(subsection_code);
create index if not exists idx_orgs_status      on organizations(status);
create index if not exists idx_orgs_last_filing on organizations(last_filing_year);

create sequence if not exists filings_id_seq start 1;

create table if not exists filings (
  id                bigint primary key default nextval('filings_id_seq'),
  ein               varchar(9) not null references organizations(ein),
  tax_year          smallint not null,
  form_type         text not null
                    check (form_type in ('990','990EZ','990PF','990N')),
  filing_date       date,
  period_end        date,
  total_revenue     decimal(14,2),
  total_expenses    decimal(14,2),
  net_assets_eoy    decimal(14,2),
  net_assets_boy    decimal(14,2),
  total_assets      decimal(14,2),
  total_liabilities decimal(14,2),
  contributions     decimal(14,2),
  program_revenue   decimal(14,2),
  investment_income decimal(14,2),
  comp_employees    decimal(14,2),
  num_employees     integer,
  num_volunteers    integer,
  num_voting_board       smallint,
  num_independent_board  smallint,
  source            text default 'irs_efile'
                    check (source in (
                      'irs_efile','nccs','nccs_pz_charities','nccs_pz_501ce',
                      'nccs_pf','propublica','manual'
                    )),
  source_url        text,
  raw_xml_url       text,
  partial_year      boolean not null default false,
  parsed_at         timestamp default current_timestamp,
  created_at        timestamp default current_timestamp,
  updated_at        timestamp default current_timestamp,
  unique(ein, tax_year, form_type)
);

create index if not exists idx_filings_ein_year     on filings(ein, tax_year);
create index if not exists idx_filings_year         on filings(tax_year);
create index if not exists idx_filings_source       on filings(source);
create index if not exists idx_filings_partial_year on filings(partial_year);
"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true", help="Drop tables before recreating")
    args = p.parse_args()

    db_path = Path(get_db_path()).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Database: {db_path}")

    con = duckdb.connect(str(db_path))
    if args.reset:
        print("Resetting schema...")
        con.execute("drop table if exists filings")
        con.execute("drop sequence if exists filings_id_seq")
        con.execute("drop table if exists organizations")

    print("Creating schema...")
    con.execute(SCHEMA_SQL)

    tables = con.execute(
        "select table_name from information_schema.tables "
        "where table_schema='main' order by table_name"
    ).fetchall()
    print(f"Tables: {[t[0] for t in tables]}")
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()