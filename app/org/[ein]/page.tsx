"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { Nav } from "@/components/nav"
import { ScoreBadge } from "@/components/score-badge"
import { formatCurrency, formatEIN } from "@/lib/utils"

type OrgData = {
  org: any
  financials: any[]
  officers: any[]
}

export default function OrgProfilePage() {
  const { ein } = useParams<{ ein: string }>()
  const [data, setData] = useState<OrgData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!ein) return
    fetch(`/api/query/org/${ein}`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found")
        return r.json()
      })
      .then(setData)
      .catch(() => setError("Organization not found"))
      .finally(() => setLoading(false))
  }, [ein])

  if (loading) {
    return (
      <>
        <Nav />
        <main className="mx-auto max-w-7xl px-6 py-12">
          <p className="text-muted-foreground">Loading…</p>
        </main>
      </>
    )
  }

  if (error || !data) {
    return (
      <>
        <Nav />
        <main className="mx-auto max-w-7xl px-6 py-12">
          <p className="text-destructive">{error || "Something went wrong"}</p>
          <Link href="/" className="mt-4 text-sm text-navy underline">
            Back to search
          </Link>
        </main>
      </>
    )
  }

  const { org, financials, officers } = data

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        {/* Back link */}
        <Link
          href="/"
          className="mb-4 inline-block text-sm text-muted-foreground hover:text-navy"
        >
          ← Back to search
        </Link>

        {/* Header */}
        <div className="mb-8 rounded-lg border border-border bg-white p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="font-serif text-3xl text-navy">{org.name}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {org.city}, {org.state} {org.zip} · EIN {formatEIN(org.ein)}
              </p>
              <p className="mt-1 text-sm">
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">
                  {org.ntee_code}
                </span>
                {org.ntee_category && (
                  <span className="ml-2 text-muted-foreground">
                    {org.ntee_category}
                  </span>
                )}
              </p>
            </div>
            <div className="text-right">
              {org.tier && (
                <ScoreBadge tier={org.tier} score={org.score} className="text-sm" />
              )}
              {org.ceo_name && (
                <p className="mt-2 text-sm">
                  <span className="text-muted-foreground">CEO:</span>{" "}
                  {org.ceo_name}
                  {org.ceo_tenure_years != null && (
                    <span className="text-muted-foreground">
                      {" "}
                      · {org.ceo_tenure_years} yr tenure
                    </span>
                  )}
                </p>
              )}
              {org.ceo_comp != null && (
                <p className="text-sm text-muted-foreground">
                  Comp: {formatCurrency(org.ceo_comp, { style: "full" })}
                </p>
              )}
            </div>
          </div>

          {/* Signal factors */}
          {org.factors && (
            <p className="mt-4 text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">Signals:</span>{" "}
              {org.factors}
            </p>
          )}
        </div>

        {/* Financials */}
        <section className="mb-8">
          <h2 className="mb-3 font-serif text-xl text-navy">
            Financial History
          </h2>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2">Year</th>
                  <th className="px-4 py-2 text-right">Revenue</th>
                  <th className="px-4 py-2 text-right">Expenses</th>
                  <th className="px-4 py-2 text-right">Surplus</th>
                  <th className="px-4 py-2 text-right">Assets</th>
                  <th className="px-4 py-2 text-right">YoY %</th>
                </tr>
              </thead>
              <tbody>
                {financials.map((f: any) => {
                  const surplus = f.operating_surplus
                  return (
                    <tr
                      key={f.tax_year}
                      className="border-b border-border/50"
                    >
                      <td className="px-4 py-2 font-medium">{f.tax_year}</td>
                      <td className="px-4 py-2 text-right font-mono">
                        {formatCurrency(f.total_revenue)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono">
                        {formatCurrency(f.total_expenses)}
                      </td>
                      <td
                        className={`px-4 py-2 text-right font-mono ${
                          surplus != null && surplus < 0
                            ? "text-score-high"
                            : ""
                        }`}
                      >
                        {formatCurrency(surplus)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono">
                        {formatCurrency(f.total_assets)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-muted-foreground">
                        {f.revenue_yoy_pct != null
                          ? `${f.revenue_yoy_pct > 0 ? "+" : ""}${f.revenue_yoy_pct}%`
                          : "—"}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* Officers */}
        <section>
          <h2 className="mb-3 font-serif text-xl text-navy">
            Officers & Key Employees
          </h2>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2">Year</th>
                  <th className="px-4 py-2">Name</th>
                  <th className="px-4 py-2">Title</th>
                  <th className="px-4 py-2 text-right">Compensation</th>
                  <th className="px-4 py-2 text-right">Hours/Wk</th>
                </tr>
              </thead>
              <tbody>
                {officers.map((o: any, i: number) => (
                  <tr
                    key={`${o.tax_year}-${o.person_name}-${i}`}
                    className="border-b border-border/50"
                  >
                    <td className="px-4 py-2">{o.tax_year}</td>
                    <td className="px-4 py-2 font-medium">{o.person_name}</td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {o.title || "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {formatCurrency(o.compensation)}
                    </td>
                    <td className="px-4 py-2 text-right text-muted-foreground">
                      {o.hours_per_week ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  )
}