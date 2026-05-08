-- =============================================================================
-- Migration 004: Extend organizations table for IRS BMF fields
-- =============================================================================
-- Phase 0 created `organizations` with the core columns. The IRS Business
-- Master File brings in additional fields we want to store. This migration
-- is purely additive — no destructive changes — so existing seed data
-- and any test rows survive.
-- =============================================================================

-- New columns from BMF
alter table organizations
  add column if not exists in_care_of           text,
  add column if not exists street               text,
  add column if not exists zip                  text,
  add column if not exists fiscal_year_end_month  smallint,
  add column if not exists ruling_date          text,            -- YYYYMM as string
  add column if not exists asset_code           smallint,
  add column if not exists income_code          smallint,
  add column if not exists asset_amount         bigint,
  add column if not exists income_amount        bigint,
  add column if not exists revenue_amount       bigint,
  add column if not exists source               text default 'manual',
  add column if not exists last_synced_at       timestamptz default now();

-- Indexes that the search and filter queries will need
create index if not exists organizations_state_idx       on organizations (state);
create index if not exists organizations_ntee_idx        on organizations (ntee_code);
create index if not exists organizations_subsection_idx  on organizations (subsection_code);
create index if not exists organizations_status_idx      on organizations (status);

-- Trigram index for fuzzy name search (we'll use this in Phase 2)
create extension if not exists pg_trgm;
create index if not exists organizations_name_trgm_idx
  on organizations using gin (name gin_trgm_ops);

-- Auto-update last_synced_at on any change
create or replace function set_last_synced_at()
returns trigger language plpgsql as $$
begin
  new.last_synced_at = now();
  return new;
end $$;

drop trigger if exists organizations_last_synced_at on organizations;
create trigger organizations_last_synced_at
  before update on organizations
  for each row execute function set_last_synced_at();
