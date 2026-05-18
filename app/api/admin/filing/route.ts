import { NextRequest, NextResponse } from 'next/server'
import * as duckdb from 'duckdb-async'

export async function POST(req: NextRequest) {
  const secret = req.headers.get('x-admin-secret')
  if (secret !== process.env.ADMIN_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await req.json()
  const {
    ein, tax_year, total_revenue, total_expenses, total_assets,
    net_assets_eoy, net_assets_boy, total_liabilities,
    contributions, program_revenue, investment_income,
    num_employees, source_url,
  } = body

  if (!ein || !tax_year) {
    return NextResponse.json({ error: 'ein and tax_year are required' }, { status: 400 })
  }

  const cleanEin = String(ein).replace(/-/g, '')
  const token = process.env.MOTHERDUCK_TOKEN
  if (!token) {
    return NextResponse.json({ error: 'MotherDuck token not configured' }, { status: 500 })
  }

  const dbPath = `md:dej_intelligence?motherduck_token=${token}`
  const db = await duckdb.Database.create(dbPath)
  const conn = await db.connect()

  try {
    const existing = await conn.all(
      'SELECT id FROM filings WHERE ein = ? AND tax_year = ?',
      cleanEin, Number(tax_year)
    )

    if (existing.length > 0) {
      await conn.run(
        `UPDATE filings SET
          total_revenue = ?, total_expenses = ?, total_assets = ?,
          net_assets_eoy = ?, net_assets_boy = ?, total_liabilities = ?,
          contributions = ?, program_revenue = ?, investment_income = ?,
          num_employees = ?, source = 'manual', source_url = ?, updated_at = now()
        WHERE ein = ? AND tax_year = ?`,
        total_revenue ?? null, total_expenses ?? null, total_assets ?? null,
        net_assets_eoy ?? null, net_assets_boy ?? null, total_liabilities ?? null,
        contributions ?? null, program_revenue ?? null, investment_income ?? null,
        num_employees ?? null, source_url ?? null,
        cleanEin, Number(tax_year)
      )
      return NextResponse.json({ ok: true, action: 'updated' })
    } else {
      await conn.run(
        `INSERT INTO filings
          (ein, tax_year, total_revenue, total_expenses, total_assets,
           net_assets_eoy, net_assets_boy, total_liabilities,
           contributions, program_revenue, investment_income,
           num_employees, source, source_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?, now(), now())`,
        cleanEin, Number(tax_year),
        total_revenue ?? null, total_expenses ?? null, total_assets ?? null,
        net_assets_eoy ?? null, net_assets_boy ?? null, total_liabilities ?? null,
        contributions ?? null, program_revenue ?? null, investment_income ?? null,
        num_employees ?? null, source_url ?? null
      )
      return NextResponse.json({ ok: true, action: 'inserted' })
    }
  } catch (err: any) {
    console.error('Filing insert error:', err)
    return NextResponse.json({ error: err.message }, { status: 500 })
  } finally {
    await conn.close()
    await db.close()
  }
}
