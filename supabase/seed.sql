-- =============================================================================
-- DEV SEED - run after migrations to populate a few known orgs for testing.
-- These are real EINs of public nonprofits. Data is illustrative only;
-- real values will be replaced by the IRS BMF backfill.
-- =============================================================================

insert into organizations (ein, name, city, state, ntee_code, ntee_category, subsection_code, status)
values
  ('530242652', 'American Red Cross', 'Washington', 'DC', 'M20', 'Disaster Preparedness', 3, 'active'),
  ('131623888', 'NAACP Legal Defense and Educational Fund', 'New York', 'NY', 'R20', 'Civil Rights', 3, 'active'),
  ('521693387', 'DC Central Kitchen', 'Washington', 'DC', 'K30', 'Food Programs', 3, 'active'),
  ('411768072', 'Twin Cities Habitat for Humanity', 'St Paul', 'MN', 'L20', 'Housing Development', 3, 'active'),
  ('411978617', 'Greater Twin Cities United Way', 'Minneapolis', 'MN', 'T70', 'Federated Giving', 3, 'active')
on conflict (ein) do nothing;

-- Sample filings for the seed orgs (illustrative numbers)
insert into filings (ein, tax_year, form_type, total_revenue, total_expenses, net_assets_eoy, source)
values
  ('530242652', 2023, '990', 3200000000, 3150000000, 1800000000, 'manual'),
  ('530242652', 2022, '990', 3050000000, 3100000000, 1750000000, 'manual'),
  ('521693387', 2023, '990', 18500000, 17200000, 12400000, 'manual'),
  ('521693387', 2022, '990', 16800000, 16200000, 11100000, 'manual'),
  ('411768072', 2023, '990',  42000000, 39500000, 38200000, 'manual'),
  ('411978617', 2023, '990',  85000000, 79000000, 52000000, 'manual')
on conflict (ein, tax_year, form_type) do nothing;
