// app/api/export/market-scan/route.ts
import { NextRequest, NextResponse } from 'next/server'
import * as duckdb from 'duckdb-async'
import { z } from 'zod'
import { getDbPath } from '@/lib/db'


const Schema = z.object({
  states: z.string().transform(v => v.split(',').map(s => s.trim().toUpperCase())),
  ntee_major: z.string().default('').transform(v => v ? v.split(',').map(s => s.trim().toUpperCase()) : []),
  rev_min: z.coerce.number().int().min(0).default(0),
  rev_max: z.coerce.number().int().max(999_999_999).default(999_999_999),
})

const CSV_LIMIT = 5000

function escapeCSV(val: unknown): string {
  if (val == null) return ''
  const str = String(val)
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

function rowToCSV(row: Record<string, unknown>): string {
  return Object.values(row).map(escapeCSV).join(',')
}

export async function GET(req: NextRequest) {
  const params = Object.fromEntries(req.nextUrl.searchParams)
  const parsed = Schema.safeParse(params)
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 })
  }

  const { states, ntee_major, rev_min, rev_max } = parsed.data
  const dbPath = getDbPath()

  const statePlaceholders = states.map(() => '?').join(', ')
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
      f.tax_year,
      f.total_revenue,
      f.total_expenses,
      (f.total_revenue - f.total_expenses) AS operating_surplus,
      f.total_assets,
      ts.score,
      ts.tier,
      ts.consecutive_deficit,
      ts.ceo_tenure_years,
      ts.ceo_name,
      ts.ceo_comp
    FROM organizations o
    JOIN (
      SELECT ein, MAX(tax_year) AS latest_year
      FROM filings GROUP BY ein
    ) latest ON o.ein = latest.ein
    JOIN filings f ON f.ein = o.ein AND f.tax_year = latest.latest_year
    LEFT JOIN transition_scores ts ON ts.ein = o.ein
    WHERE
      o.state IN (${statePlaceholders})
      ${nteeClause}
      AND COALESCE(f.total_revenue, 0) BETWEEN ? AND ?
    ORDER BY ts.score DESC NULLS LAST, f.total_revenue DESC NULLS LAST
    LIMIT ${CSV_LIMIT}
  `

  const db = await duckdb.Database.create(dbPath, { access_mode: 'READ_ONLY' })
  const conn = await db.connect()

  try {
    const baseArgs = [...states, ...ntee_major]
    const rows = await conn.all(SQL, ...baseArgs, rev_min, rev_max) as Record<string, unknown>[]

    if (!rows.length) {
      return new NextResponse('No data', { status: 204 })
    }

    const headers = Object.keys(rows[0])
    const csvLines = [headers.join(','), ...rows.map(rowToCSV)]
    const csv = csvLines.join('\n')

    return new NextResponse(csv, {
      status: 200,
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': `attachment; filename="dej-market-scan-${new Date().toISOString().slice(0, 10)}.csv"`,
        'Cache-Control': 'no-store',
      },
    })
  } finally {
    await conn.close()
    await db.close()
  }
}