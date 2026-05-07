# DEJ Intelligence

The intelligence layer for nonprofit executive search. Built by a search consultant, for search consultants.

**Status:** Phase 0 — scaffolding complete. Data foundation next.

---

## What's in this repo (Phase 0)

- Next.js 15 + TypeScript + Tailwind + shadcn/ui-ready setup
- Supabase client wiring (browser, server, service-role)
- Three database migrations covering the full Phase 1–6 schema
- Brand-styled landing page placeholder
- Tier configuration matching the pricing in the build plan
- Utility functions for currency/EIN formatting and score tiers

What's NOT here yet (by design — coming in later phases):

- Actual 990 data (Phase 1)
- Search and org pages (Phase 2)
- The Transition Signal Score algorithm (Phase 3)
- AI brief generation (Phase 4)
- Watchlists and digests (Phase 5)
- Stripe billing (Phase 6)

---

## First-time setup (David — do this once)

You need three things: this repo on GitHub, a Supabase project, and a working dev server. Total time: ~30 minutes.

### 1. Push to GitHub

```bash
cd ~/path/to/dej-intelligence
git init
git add .
git commit -m "Phase 0 scaffold"

# Create the private repo on github.com/dledgerton (UI is fine)
git branch -M main
git remote add origin git@github.com:dledgerton/dej-intelligence.git
git push -u origin main
```

### 2. Create the Supabase project

1. Go to https://supabase.com/dashboard, sign in with GitHub
2. New project → name: `dej-intelligence-prod`, region: US East (closest to most users), strong database password (save in 1Password)
3. Wait ~2 minutes for provisioning
4. From the project home page, copy:
   - **Project URL** → `NEXT_PUBLIC_SUPABASE_URL`
   - **anon public key** → `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - **service_role key** (under Settings → API) → `SUPABASE_SERVICE_ROLE_KEY`

### 3. Configure local environment

```bash
cp .env.example .env.local
# Open .env.local and paste the three Supabase values from step 2
```

### 4. Install dependencies

```bash
npm install
```

### 5. Run the migrations

You have two options:

**Option A (recommended) — via Supabase Dashboard:**

1. In your Supabase project, go to SQL Editor
2. Open `supabase/migrations/0001_init_organizations.sql`, paste, run
3. Repeat for `0002_filings_and_officers.sql`, then `0003_users_and_scoring.sql`
4. Optional: paste `supabase/seed.sql` to load 5 test orgs

**Option B — via Supabase CLI:**

```bash
npx supabase login
npx supabase link --project-ref YOUR_PROJECT_REF
npx supabase db push
```

### 6. Generate types

After the migrations are live, regenerate the TypeScript types so the rest of the app compiles correctly:

```bash
npx supabase gen types typescript --project-id YOUR_PROJECT_REF > lib/supabase/database.types.ts
```

### 7. Run dev server

```bash
npm run dev
```

Open http://localhost:3000 — you should see the landing page placeholder.

### 8. Sanity-check the database

In Supabase SQL Editor:

```sql
select count(*) from organizations;
-- if you ran seed.sql: 5
-- otherwise: 0

select tablename, hastriggers
from pg_tables
where schemaname = 'public'
order by tablename;
-- you should see 9 tables: audit_log, briefs, filings, officers,
-- organizations, public_signals, transition_scores, user_profiles,
-- watchlist_orgs, watchlists
```

If counts and table list match, Phase 0 is done.

---

## Schema overview

| Table              | Purpose                                                          |
| ------------------ | ---------------------------------------------------------------- |
| organizations      | One row per nonprofit, keyed by EIN                              |
| filings            | Form 990 financial data, one row per (org, tax year)             |
| officers           | Officers/directors/key employees from Form 990 Part VII          |
| transition_scores  | Monthly Transition Signal Score per org with factor breakdown    |
| public_signals     | Press/LinkedIn/news signals feeding the score                    |
| user_profiles      | Subscription state and usage counters (extends auth.users)       |
| watchlists         | User-saved org watchlists with filter rules                      |
| watchlist_orgs     | Many-to-many org pinning                                         |
| briefs             | AI-generated briefs, cached 7 days                               |
| audit_log          | All user actions for analytics and billing reconciliation        |

Full table-by-table detail with column comments is in `supabase/migrations/`.

---

## Next phase

Phase 1: Data foundation. We'll write the IRS BMF parser, do the historical NCCS backfill, set up the monthly Inngest job for incremental IRS XML updates, and validate against a list of known orgs (DEJ Search past clients).

Estimated 20 hours across 2–3 sessions.

---

## Stack

- **Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui
- **Database:** Supabase (Postgres + Auth + RLS)
- **AI:** Anthropic Claude Sonnet 4.6 (with prompt caching)
- **Billing:** Stripe (Checkout + Customer Portal)
- **Email:** Resend (transactional) + Beehiiv (marketing)
- **Background jobs:** Inngest
- **Hosting:** Vercel

---

## License

Proprietary. All rights reserved. © 2026 David Edgerton Jr.
