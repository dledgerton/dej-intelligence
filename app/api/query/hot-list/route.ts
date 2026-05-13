// app/api/query/hot-list/route.ts
// Q2 — Hot List: imminent + high scored orgs with human-readable signal

import { NextRequest, NextResponse } from 'next/server'
import * as duckdb from 'duckdb-async'
import { z } from 'zod'

const VALID_TIERS = ['imminent', 'high', 'elevated', 'low'] as const

const Schema = z.object({
  states: z.string().transform(v => v.split(',').map(s => s.trim().toUpperCase())),
  score_tiers: z.string().default('imminent,high').transform(v =>
    v.split(',').map(s => s.trim().toLowerCase()).filter(t => VALID_TIERS.includes(t as any))
  ),
  ntee_major: z.string().default('').transform(v => v ? v.split(',') : []),
})

export async function GET(req: NextRequest) {
  const params = Object.fromEntries(req.nextUrl.searchParams)
  const parsed = Schema.safeParse(params)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const { states, score_tiers, ntee_major } = parsed.data
  const dbPath = process.env.DEJ_DB_PATH
  if (!dbPath) return NextResponse.json({ error: 'DEJ_DB_PATH not set' }, { status: 500 })

  const statePlaceholders = states.map(() => '?').join(', ')
  const tierPlaceholders = score_tiers.map(() => '?').join(', ')
  const nteeClause = ntee_major.length > 0
    ? `AND LEFT(o.ntee_code, 1) IN (${ntee_major.map(() => '?').join(', ')})`
    : ''

  const SQL = `
    SELECT
      o.ein,
      o.name,
      o.city,
      o.state,
      o.ntee_code,
      o.ntee_category,
      f.total_revenue,
      f.tax_year,
      ts.score,
      ts.total_score_v2,
      ts.tier,
      ts.consecutive_deficit,
      ts.ceo_tenure_years,
      ts.ceo_name,
      ts.ceo_comp,
      ts.signal_leadership,
      ts.factors,
      CASE
        WHEN ts.consecutive_deficit >= 2
          THEN 'Consecutive deficits (' || ts.consecutive_deficit::TEXT || ' yrs)'
        WHEN ts.consecutive_deficit = 1
          THEN 'Operating deficit'
        WHEN ts.ceo_tenure_years > 10
          THEN 'CEO tenure ' || ts.ceo_tenure_years::TEXT || ' yrs'
        WHEN ts.signal_leadership
          THEN 'Leadership transition signal'
        ELSE 'Composite signal'
      END AS primary_signal
    FROM organizations o
    JOIN (
      SELECT ein, MAX(tax_year) AS latest_year FROM filings GROUP BY ein
    ) latest ON o.ein = latest.ein
    JOIN filings f ON f.ein = o.ein AND f.tax_year = latest.latest_year
    JOIN transition_scores ts ON ts.ein = o.ein
    WHERE
      o.state IN (${statePlaceholders})
      AND ts.tier IN (${tierPlaceholders})
      ${nteeClause}
    ORDER BY ts.score DESC NULLS LAST, f.total_revenue DESC NULLS LAST
  `

  const db = await duckdb.Database.create(dbPath, { access_mode: 'READ_ONLY' })
  const conn = await db.connect()

  try {
    const args = [...states, ...score_tiers, ...ntee_major]
    const rows = await conn.all(SQL, ...args)
    return NextResponse.json({ total: rows.length, results: rows })
  } finally {
    await conn.close()
    await db.close()
  }
}
