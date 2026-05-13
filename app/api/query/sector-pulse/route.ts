// app/api/query/sector-pulse/route.ts
// Q4 — Sector Pulse: year-by-year aggregate trends

import { NextRequest, NextResponse } from 'next/server'
import * as duckdb from 'duckdb-async'
import { z } from 'zod'

function serializeBigInts(obj: any): any {
  return JSON.parse(
    JSON.stringify(obj, (_, v) => (typeof v === "bigint" ? Number(v) : v))
  )
}

const Schema = z.object({
  states: z.string().transform(v => v.split(',').map(s => s.trim().toUpperCase())),
  ntee_major: z.string().min(1).transform(v => v.split(',').map(s => s.trim().toUpperCase())),
  start_year: z.coerce.number().int().min(2010).default(2018),
  end_year: z.coerce.number().int().max(2025).default(2023),
})

export async function GET(req: NextRequest) {
  const params = Object.fromEntries(req.nextUrl.searchParams)
  const parsed = Schema.safeParse(params)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const { states, ntee_major, start_year, end_year } = parsed.data
  const dbPath = process.env.DEJ_DB_PATH
  if (!dbPath) return NextResponse.json({ error: 'DEJ_DB_PATH not set' }, { status: 500 })

  const statePlaceholders = states.map(() => '?').join(', ')
  const nteePlaceholders = ntee_major.map(() => '?').join(', ')

  const SQL = `
    SELECT
      f.tax_year AS year,
      COUNT(DISTINCT f.ein) AS org_count,
      ROUND(AVG(f.total_revenue), 0) AS avg_revenue,
      ROUND(MEDIAN(f.total_revenue), 0) AS median_revenue,
      SUM(f.total_revenue) AS total_sector_revenue,
      COUNT(DISTINCT CASE WHEN f.total_revenue < f.total_expenses THEN f.ein END) AS deficit_org_count,
      ROUND(
        COUNT(DISTINCT CASE WHEN f.total_revenue < f.total_expenses THEN f.ein END)::FLOAT
        / NULLIF(COUNT(DISTINCT f.ein), 0) * 100, 1
      ) AS deficit_pct,
      COUNT(DISTINCT CASE WHEN ts.tier = 'imminent' THEN ts.ein END) AS critical_count,
      COUNT(DISTINCT CASE WHEN ts.tier = 'high' THEN ts.ein END) AS high_count,
      COUNT(DISTINCT CASE WHEN ts.tier = 'elevated' THEN ts.ein END) AS elevated_count,
      AVG(f.num_employees) AS avg_employees
    FROM filings f
    JOIN organizations o ON o.ein = f.ein
    LEFT JOIN transition_scores ts ON ts.ein = f.ein
    WHERE
      o.state IN (${statePlaceholders})
      AND LEFT(o.ntee_code, 1) IN (${nteePlaceholders})
      AND f.tax_year BETWEEN ? AND ?
    GROUP BY f.tax_year
    ORDER BY f.tax_year ASC
  `

  const db = await duckdb.Database.create(dbPath, { access_mode: 'READ_ONLY' })
  const conn = await db.connect()

  try {
    const rows = await conn.all(SQL, ...states, ...ntee_major, start_year, end_year)
    return NextResponse.json(serializeBigInts({ years: rows }))
  } finally {
    await conn.close()
    await db.close()
  }
}