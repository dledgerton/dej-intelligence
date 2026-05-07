-- =============================================================================
-- Migration: 0002_filings_and_officers
-- Purpose:   Form 990 financial data and officer/board records.
--            Powers financial trends, tenure detection, and the score.
-- =============================================================================

-- =============================================================================
-- filings
-- =============================================================================
-- One row per Form 990 filing year per org.
-- Financial figures stored as numeric(14,2) - max ~999 trillion, plenty.
-- =============================================================================
create table filings (
  id                bigserial primary key,
  ein               char(9) not null references organizations(ein) on delete cascade,
  tax_year          smallint not null,
  form_type         text not null
                    check (form_type in ('990','990EZ','990PF','990N')),
  filing_date       date,
  period_end        date,

  -- Core financials (Part I summary)
  total_revenue     numeric(14,2),
  total_expenses    numeric(14,2),
  net_assets_eoy    numeric(14,2),
  net_assets_boy    numeric(14,2),
  total_assets      numeric(14,2),
  total_liabilities numeric(14,2),

  -- Revenue breakdown
  contributions     numeric(14,2),
  program_revenue   numeric(14,2),
  investment_income numeric(14,2),

  -- Compensation & staff
  comp_employees    numeric(14,2),
  num_employees     integer,
  num_volunteers    integer,

  -- Governance (Part VI)
  num_voting_board       smallint,
  num_independent_board  smallint,

  -- Source tracking
  source              text default 'irs_efile'
                      check (source in ('irs_efile','nccs','propublica','manual')),
  source_url          text,
  raw_xml_url         text,
  parsed_at           timestamptz default now() not null,

  -- Audit
  created_at          timestamptz default now() not null,
  updated_at          timestamptz default now() not null,

  unique(ein, tax_year, form_type)
);

create index idx_filings_ein_year  on filings(ein, tax_year desc);
create index idx_filings_year      on filings(tax_year desc);
create index idx_filings_filed     on filings(filing_date desc nulls last);

create trigger filings_updated_at
  before update on filings
  for each row execute function set_updated_at();

-- Keep organizations.last_filing_year / last_filing_date in sync
create or replace function update_org_last_filing()
returns trigger as $$
begin
  update organizations
     set last_filing_year = greatest(coalesce(last_filing_year, 0), new.tax_year),
         last_filing_date = case
           when new.filing_date is null then last_filing_date
           when last_filing_date is null then new.filing_date
           else greatest(last_filing_date, new.filing_date)
         end
   where ein = new.ein
     and (last_filing_year is null or new.tax_year >= last_filing_year);
  return new;
end;
$$ language plpgsql;

create trigger filings_update_org
  after insert or update on filings
  for each row execute function update_org_last_filing();

-- =============================================================================
-- officers
-- =============================================================================
-- Part VII of Form 990. Officers, directors, key employees, highest comp.
-- One row per person per filing year. Used to:
--   1. Detect CEO/ED tenure (count consecutive years a name appears with
--      "President", "CEO", or "Executive Director" in title)
--   2. Detect board chair changes (track who holds "Chair" or "Chairman" titles
--      over time)
--   3. Surface compensation context for top staff
--
-- Name normalization is non-trivial - "Jane Smith", "Jane R. Smith",
-- "Smith, Jane" can all be the same person. We use trigram similarity
-- in queries rather than trying to canonicalize on insert.
-- =============================================================================
create table officers (
  id              bigserial primary key,
  ein             char(9) not null references organizations(ein) on delete cascade,
  filing_id       bigint references filings(id) on delete cascade,
  tax_year        smallint not null,

  name            text not null,
  title           text,

  -- Role flags (a person can have more than one)
  is_officer      boolean default false,
  is_director     boolean default false,
  is_key_employee boolean default false,
  is_highest_comp boolean default false,
  is_former       boolean default false,

  hours_per_week         numeric(5,2),
  hours_per_week_related numeric(5,2),

  -- Compensation (USD)
  comp_reportable numeric(12,2),
  comp_other      numeric(12,2),
  comp_related    numeric(12,2),

  created_at      timestamptz default now() not null
);

create index idx_officers_ein_year   on officers(ein, tax_year desc);
create index idx_officers_filing     on officers(filing_id);
create index idx_officers_name_trgm  on officers using gin (name gin_trgm_ops);
create index idx_officers_title_trgm on officers using gin (title gin_trgm_ops);

-- =============================================================================
-- RLS
-- =============================================================================
alter table filings enable row level security;
alter table officers enable row level security;

create policy "authenticated users can read filings"
  on filings for select to authenticated using (true);

create policy "authenticated users can read officers"
  on officers for select to authenticated using (true);

comment on table filings  is 'Form 990 annual financial data. One row per org per tax year.';
comment on table officers is 'Officers, directors, key employees from Form 990 Part VII.';
