# Phase 1 Runbook — Data Foundation

This runbook walks through loading the IRS Business Master File into your `organizations` table. After this, you'll have ~150,000 real nonprofits in your database, filtered to your DMV + Minnesota + NY practice areas.

**Time:** ~30 minutes the first time, ~5 minutes for re-runs.

---

## Step 1 — Apply the new migration

The BMF brings in fields the Phase 0 schema doesn't have yet (in_care_of, fiscal_year_end_month, ruling_date, asset/income/revenue amounts). Migration 004 adds them.

In your Supabase dashboard:

1. Go to **SQL Editor** → **New query**
2. Open `supabase/migrations/004_extend_organizations.sql` from the repo
3. Paste and click **Run**

You should see "Success. No rows returned." If you see "extension pg_trgm already exists," that's fine — it's idempotent.

**Verify:** in **Table Editor** → `organizations`, confirm the new columns exist (`source`, `last_synced_at`, `asset_amount`, etc.).

---

## Step 2 — Set up the Python environment

The loaders are Python (faster CSV streaming and easier batch handling than Node for this kind of work).

From the repo root:

```bash
cd ~/path/to/dej-intelligence

# Create a venv so this doesn't pollute your system Python
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r scripts/requirements.txt
```

If `python3 -m venv` fails, run `xcode-select --install` first — macOS sometimes needs the command-line tools.

---

## Step 3 — Confirm your `.env.local` has the service-role key

The loader needs the **service-role key**, not the anon key, because it writes to the database directly.

Open `.env.local` and confirm it has all three:

```
NEXT_PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...   ← this one is required for the loader
```

Find the service-role key in Supabase: **Project Settings → API → service_role secret**.

**Important:** the service-role key bypasses Row Level Security. Keep it out of any client code — it's only used by these Python scripts and any Next.js server actions.

---

## Step 4 — Dry run

Before writing anything to the DB, run the loader in dry-run mode to confirm the IRS files are reachable and the parser works.

```bash
python scripts/loaders/load_bmf.py --dry-run --limit 5000
```

Expected output:

```
=== Region: eo1 ===
  → fetching eo1 from https://www.irs.gov/pub/irs-soi/eo1.csv
=== Region: eo2 ===
  → fetching eo2 from https://www.irs.gov/pub/irs-soi/eo2.csv
...

============================================================
BMF LOAD SUMMARY
============================================================
  Rows seen:    250,000+
  Rows matched: 5,000
  Rows loaded:  5,000  (DRY RUN)
  Elapsed:      45-90s

  By state:
    DC:     ...
    MD:     ...
    MN:     ...
    NY:     ...
    VA:     ...
```

If you see rows by state and the run finishes clean, the loader works. If you see errors fetching from irs.gov, your network is blocked or the IRS site is down — try again in 10 minutes.

---

## Step 5 — Full load

Drop the `--dry-run` and `--limit` flags:

```bash
python scripts/loaders/load_bmf.py
```

Expected:

- ~5–10 minutes total runtime
- ~150,000 rows loaded across DC/MD/VA/MN/NY
- Progress prints every 1,000 rows

If it crashes mid-run, just rerun it. The loader uses `upsert` on EIN, so re-running is safe — it'll update existing rows and add new ones.

---

## Step 6 — Sanity check in Supabase

In Supabase **Table Editor → organizations**:

- Total row count should be in the 140k–160k range
- Filter by `state = 'DC'` — should see thousands of orgs, including American Red Cross (EIN 530242652) and DC Central Kitchen (EIN 521693387)
- Filter by `state = 'MN'` and `ntee_code starts with 'L'` — should see Twin Cities Habitat for Humanity and similar

---

## Step 7 — Validate against your 10 known orgs

This is the QA gate. Open `scripts/validation/known_orgs.json` and replace the placeholder with your 10 validation orgs. Format:

```json
{
  "orgs": [
    {
      "ein": "521693387",
      "name": "DC Central Kitchen",
      "expected_state": "DC",
      "expected_subsection": 3,
      "expected_ntee_major": "K",
      "size_bucket": "mid",
      "notes": "Past engagement — financials I know cold"
    },
    ... 9 more
  ]
}
```

Then run:

```bash
python scripts/validation/validate_load.py
```

You want all 10 to come back with checkmarks. If any are missing or have mismatched state/subsection/NTEE, that's a bug in the loader and we need to fix it before moving on.

---

## What "done" looks like for Step 7

- All 10 validation orgs found in DB
- All 10 have correct state, subsection, and NTEE major category
- No mismatches printed

If validation passes, Phase 1 step 1 of 4 is complete. We'll move on to:

- **NCCS bulk loader** for 5 years of financial history
- **Inngest function** for monthly incremental updates
- **Officers table backfill** from Form 990 Schedule O

Ping me when you've run through this and either: (a) it all worked, in which case we ship NCCS, or (b) you hit an error, in which case paste the traceback and we fix it.
