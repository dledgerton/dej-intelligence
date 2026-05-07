-- =============================================================================
-- Migration: 0003_users_and_scoring
-- Purpose:   User profiles (extends auth.users), Transition Signal Scores,
--            public signals from press/LinkedIn/news.
-- =============================================================================

-- =============================================================================
-- user_profiles
-- =============================================================================
-- Supabase auth.users handles authentication. user_profiles holds everything
-- else: subscription state, usage counters, preferences.
-- =============================================================================
create table user_profiles (
  id                  uuid primary key references auth.users(id) on delete cascade,
  full_name           text,
  firm_name           text,
  role                text check (role in ('consultant','principal','researcher','admin')),

  -- Practice focus (used to default the first watchlist)
  geography           text[],
  ntee_focus          text[],

  -- Subscription state (mirrors Stripe; Stripe is source of truth)
  stripe_customer_id  text unique,
  subscription_tier   text default 'trial'
                      check (subscription_tier in ('trial','solo','firm','enterprise')),
  subscription_status text default 'trialing',
  trial_ends_at       timestamptz,
  current_period_end  timestamptz,

  -- Monthly usage counters (reset by Inngest job at start of each month)
  briefs_used_month   integer default 0 not null,
  searches_used_today integer default 0 not null,
  searches_reset_at   date default current_date,

  -- API key (Enterprise tier only; stored as bcrypt hash)
  api_key_hash        text,
  api_key_prefix      text,    -- first 8 chars for display, e.g. "dej_live_a1b2c3d4..."

  created_at          timestamptz default now() not null,
  updated_at          timestamptz default now() not null
);

create index idx_profiles_stripe on user_profiles(stripe_customer_id);
create index idx_profiles_tier   on user_profiles(subscription_tier);

create trigger profiles_updated_at
  before update on user_profiles
  for each row execute function set_updated_at();

-- Auto-create profile when auth user signs up
create or replace function handle_new_user()
returns trigger as $$
begin
  insert into user_profiles (id, trial_ends_at)
  values (
    new.id,
    now() + interval '14 days'
  );
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- =============================================================================
-- transition_scores
-- =============================================================================
-- One row per org per month. Historical scores are retained so we can show
-- score-change deltas in the digest and on org detail pages.
--
-- factors jsonb stores the per-factor breakdown for transparency:
--   {
--     "ceo_tenure":          { "value": 8.4, "points": 18 },
--     "comp_trajectory":     { "value": "flat", "points": 6 },
--     "board_chair_change":  { "value": true, "points": 15 },
--     "deficit_years":       { "value": 2,  "points": 10 },
--     "revenue_trend":       { "value": -0.18, "points": 6 },
--     "signal_leadership":   { "value": null, "points": 0 },
--     "signal_search_rfp":   { "value": null, "points": 0 }
--   }
-- =============================================================================
create table transition_scores (
  id                  bigserial primary key,
  ein                 char(9) not null references organizations(ein) on delete cascade,
  scored_at           date not null,
  score               smallint not null check (score between 0 and 100),
  tier                text not null
                      check (tier in ('low','elevated','high','imminent')),
  factors             jsonb not null,

  -- Surfaced for fast queries without unpacking jsonb
  ceo_tenure_years    numeric(4,1),
  board_chair_change  boolean,
  consecutive_deficit smallint,

  created_at          timestamptz default now() not null,
  unique(ein, scored_at)
);

create index idx_scores_ein         on transition_scores(ein, scored_at desc);
create index idx_scores_recent_high on transition_scores(scored_at desc, score desc)
                                       where score >= 60;
create index idx_scores_tier        on transition_scores(tier, scored_at desc);

-- =============================================================================
-- public_signals
-- =============================================================================
-- Press releases, LinkedIn role changes, news mentions detected by daily
-- scrape jobs. confidence is 0.0-1.0; signals < 0.7 require human review
-- before they affect the score.
-- =============================================================================
create table public_signals (
  id           bigserial primary key,
  ein          char(9) references organizations(ein) on delete set null,

  signal_type  text not null
               check (signal_type in (
                 'leadership_change',
                 'search_announcement',
                 'financial_news',
                 'merger',
                 'strategic_plan',
                 'other'
               )),

  source_url   text,
  source_name  text,
  detected_at  timestamptz default now() not null,
  occurred_at  date,
  summary      text,
  confidence   numeric(3,2) check (confidence between 0 and 1),

  reviewed_by  uuid references auth.users(id),
  is_published boolean default false,

  created_at   timestamptz default now() not null
);

create index idx_signals_ein_date   on public_signals(ein, occurred_at desc nulls last);
create index idx_signals_type       on public_signals(signal_type, occurred_at desc nulls last);
create index idx_signals_unreviewed on public_signals(detected_at desc)
                                      where is_published = false;

-- =============================================================================
-- watchlists + watchlist_orgs
-- =============================================================================
create table watchlists (
  id                  bigserial primary key,
  user_id             uuid not null references auth.users(id) on delete cascade,
  name                text not null,

  -- Filter criteria
  filter_state        text[],
  filter_ntee         text[],
  filter_min_revenue  numeric(14,2),
  filter_max_revenue  numeric(14,2),
  filter_min_score    smallint,

  digest_enabled      boolean default true,
  created_at          timestamptz default now() not null,
  updated_at          timestamptz default now() not null
);

create index idx_watchlists_user on watchlists(user_id);

create trigger watchlists_updated_at
  before update on watchlists
  for each row execute function set_updated_at();

create table watchlist_orgs (
  watchlist_id  bigint not null references watchlists(id) on delete cascade,
  ein           char(9) not null references organizations(ein) on delete cascade,
  added_at      timestamptz default now() not null,
  primary key (watchlist_id, ein)
);

create index idx_watchlist_orgs_ein on watchlist_orgs(ein);

-- =============================================================================
-- briefs
-- =============================================================================
-- AI-generated org briefs. Cached for 7 days unless the underlying filing
-- changes. Counts against monthly quota.
-- =============================================================================
create table briefs (
  id            bigserial primary key,
  ein           char(9) not null references organizations(ein) on delete cascade,
  user_id       uuid not null references auth.users(id) on delete cascade,
  brief_type    text default 'standard'
                check (brief_type in ('standard','custom','rfp_prep')),
  content       jsonb not null,
  markdown      text,
  generated_at  timestamptz default now() not null,
  expires_at    timestamptz default (now() + interval '7 days') not null,
  prompt_tokens integer,
  output_tokens integer
);

create index idx_briefs_ein_recent on briefs(ein, generated_at desc);
create index idx_briefs_user       on briefs(user_id, generated_at desc);
create index idx_briefs_active     on briefs(ein, expires_at);

-- =============================================================================
-- audit_log
-- =============================================================================
create table audit_log (
  id          bigserial primary key,
  user_id     uuid references auth.users(id) on delete set null,
  action      text not null,
  target_ein  char(9),
  metadata    jsonb,
  created_at  timestamptz default now() not null
);

create index idx_audit_user_recent on audit_log(user_id, created_at desc);
create index idx_audit_action      on audit_log(action, created_at desc);

-- =============================================================================
-- RLS
-- =============================================================================
alter table user_profiles      enable row level security;
alter table transition_scores  enable row level security;
alter table public_signals     enable row level security;
alter table watchlists         enable row level security;
alter table watchlist_orgs     enable row level security;
alter table briefs             enable row level security;
alter table audit_log          enable row level security;

-- Profiles: users can read/update their own
create policy "users read own profile"
  on user_profiles for select to authenticated
  using (auth.uid() = id);

create policy "users update own profile"
  on user_profiles for update to authenticated
  using (auth.uid() = id);

-- Scores: all authenticated users can read
create policy "authenticated read scores"
  on transition_scores for select to authenticated using (true);

-- Public signals: all authenticated users can read PUBLISHED signals only
create policy "authenticated read published signals"
  on public_signals for select to authenticated
  using (is_published = true);

-- Watchlists: users can only see their own
create policy "users manage own watchlists"
  on watchlists for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "users manage own watchlist_orgs"
  on watchlist_orgs for all to authenticated
  using (
    exists (
      select 1 from watchlists w
      where w.id = watchlist_orgs.watchlist_id and w.user_id = auth.uid()
    )
  );

-- Briefs: users can only see their own
create policy "users read own briefs"
  on briefs for select to authenticated
  using (auth.uid() = user_id);

-- Audit log: users can only see their own
create policy "users read own audit"
  on audit_log for select to authenticated
  using (auth.uid() = user_id);

comment on table user_profiles     is 'Extends auth.users with subscription state and usage counters.';
comment on table transition_scores is 'Monthly score per org. Historical retained for trend display.';
comment on table public_signals    is 'External signals (press, LinkedIn, news) feeding the score.';
comment on table watchlists        is 'User-saved org watchlists with filter rules.';
comment on table briefs            is 'AI-generated org briefs. Cached 7 days unless filings change.';
