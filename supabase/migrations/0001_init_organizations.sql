-- =============================================================================
-- Migration: 0001_init_organizations
-- Purpose:   Enable required extensions and create the organizations table.
--            One row per nonprofit. EIN is the universal key.
-- =============================================================================

-- Required extensions
create extension if not exists "pg_trgm";   -- fuzzy name search
create extension if not exists "uuid-ossp"; -- uuid generation (used by auth)

-- =============================================================================
-- organizations
-- =============================================================================
-- Source of truth for nonprofit metadata. Sourced from:
--   1. IRS Exempt Organization Business Master File (BMF) - org name, address,
--      NTEE code, ruling year, deductibility code
--   2. IRS Auto-Revocation List - status field
--   3. Filings table - last_filing_year, last_filing_date (denormalized
--      for query performance; updated when filings are inserted)
--
-- EIN is stored as char(9). DO NOT use integer - leading zeros are
-- meaningful and integer types will silently strip them.
-- =============================================================================
create table organizations (
  ein              char(9) primary key,
  name             text not null,
  dba              text,
  address_line1    text,
  address_line2    text,
  city             text,
  state            char(2),
  zip              text,
  country          char(2) default 'US',

  -- Classification
  ntee_code        text,           -- e.g. 'T20'
  ntee_category    text,           -- e.g. 'Private Grantmaking Foundations'
  subsection_code  smallint,       -- 501(c)(X)
  ruling_year      smallint,
  deductibility    text,           -- IRS deductibility code

  -- Status
  filing_required  boolean,
  status           text default 'active'
                   check (status in ('active','revoked','merged','terminated')),
  revoked_at       date,

  -- Denormalized from filings (kept fresh by trigger - see below)
  last_filing_year smallint,
  last_filing_date date,

  -- Audit
  created_at       timestamptz default now() not null,
  updated_at       timestamptz default now() not null
);

-- Indexes
create index idx_orgs_state         on organizations(state);
create index idx_orgs_ntee          on organizations(ntee_code);
create index idx_orgs_status        on organizations(status);
create index idx_orgs_last_filing   on organizations(last_filing_year desc nulls last);

-- Trigram index for fuzzy name search ("foundatn" finds "foundation")
create index idx_orgs_name_trgm     on organizations using gin (name gin_trgm_ops);

-- updated_at trigger
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger orgs_updated_at
  before update on organizations
  for each row execute function set_updated_at();

-- =============================================================================
-- Row Level Security
-- =============================================================================
-- organizations table is PUBLIC read for authenticated users.
-- Only service role can write.
alter table organizations enable row level security;

create policy "authenticated users can read organizations"
  on organizations for select
  to authenticated
  using (true);

-- Anonymous users get no access. They must authenticate.

comment on table organizations is
  'Source of truth for nonprofit metadata. EIN as primary key. Updated monthly from IRS BMF.';
