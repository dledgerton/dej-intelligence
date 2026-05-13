// app/api/query/org/[ein]/route.ts
// Q3 — Org Deep Dive: header + financials + officer history

import { NextRequest, NextResponse } from 'next/server'
import * as duckdb from 'duckdb-async'
import { z } from 'zod'

function serializeBigInts(obj: any): any {
  return JSON.parse(
    JSON.stringify(obj, (_, v) => (typeof v === "bigint" ? Number(v) : v))
  )
}

const EinSchema = z.string().regex(/^\d{9}$/, 'EIN must be 9 digits')

const HEADER_SQL = `
SELECT
  o.ein, o.name, o.city, o.state, o.zip,
  o.ntee_code, o.ntee_category, o.ruling_date,
  o.last_filing_year, o.asset_amount, o.income_amount,
  ts.score,
  ts.total_score_v2,
  ts.tier,
  ts.consecutive_deficit,
  ts.ceo_tenure_years,
  ts.ceo_name,
  ts.ceo_comp,
  ts.ceo_comp_pct_ntee,
  ts.ceo_tenure_pts,
  ts.ceo_comp_pts,
  ts.signal_leadership,
  ts.board_chair_change,
  ts.factors,
  ts.scored_at
FROM organizations o
LEFT JOIN transition_scores ts ON ts.ein = o.ein
WHERE o.ein = ?
`

const FINANCIALS_SQL = `
SELECT
  tax_year,
  total_revenue,
  total_expenses,
  (total_revenue - total_expenses) AS operating_surplus,
  total_assets,
  total_liabilities,
  net_assets_eoy,
  contributions,
  program_revenue,
  investment_income,
  num_employees,
  LAG(total_revenue) OVER (PARTITION BY ein ORDER BY tax_year) AS prev_revenue,
  CASE
    WHEN LAG(total_revenue) OVER (PARTITION BY ein ORDER BY tax_year) > 0
    THEN ROUND(
      (total_revenue - LAG(total_revenue) OVER (PARTITION BY ein ORDER BY tax_year))
      / LAG(total_revenue) OVER (PARTITION BY ein ORDER BY tax_year) * 100,
      1
    )
    ELSE NULL
  END AS revenue_yoy_pct
FROM filings
WHERE ein = ?
ORDER BY tax_year DESC
`

const OFFICERS_SQL = `
SELECT
  tax_year,
  person_name,
  title_normalized AS title,
  comp_total AS compensation,
  hours_per_week,
  is_top_officer,
  is_officer,
  is_key_employee,
  is_former,
  ROW_NUMBER() OVER (
    PARTITION BY ein, person_name ORDER BY tax_year
  ) AS appearance_number
FROM officers
WHERE ein = ?
ORDER BY tax_year DESC, comp_total DESC NULLS LAST
`

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ ein: string }> }
) {
  const { ein: rawEin } = await context.params
  const einResult = EinSchema.safeParse(rawEin)
  if (!einResult.success) {
    return NextResponse.json({ error: 'Invalid EIN' }, { status: 400 })
  }

  const ein = einResult.data
  const dbPath = process.env.DEJ_DB_PATH
  if (!dbPath) return NextResponse.json({ error: 'DEJ_DB_PATH not set' }, { status: 500 })

  const db = await duckdb.Database.create(dbPath, { access_mode: 'READ_ONLY' })
  const conn = await db.connect()

  try {
    const [headerRows, financials, officers] = await Promise.all([
      conn.all(HEADER_SQL, ein),
      conn.all(FINANCIALS_SQL, ein),
      conn.all(OFFICERS_SQL, ein),
    ])

    if (!headerRows.length) {
      return NextResponse.json({ error: 'Organization not found' }, { status: 404 })
    }

    return NextResponse.json(serializeBigInts({
      org: headerRows[0],
      financials,
      officers,
    }))
  } finally {
    await conn.close()
    await db.close()
  }
}