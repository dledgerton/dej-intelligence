"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { Nav } from "@/components/nav"
import { ScoreBadge } from "@/components/score-badge"
import { SignalPanel } from "@/components/signal-chips"
import { formatCurrency, formatEIN } from "@/lib/utils"

type OrgData = {
  org: any
  financials: any[]
  officers: any[]
}

function RequestDataButton({ ein, orgName }: { ein: string; orgName: string }) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle")

  async function handleRequest() {
    setStatus("loading")
    try {
      const res = await fetch("/api/user/request-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ein, orgName }),
      })
      if (!res.ok) throw new Error("Request failed")
      setStatus("done")
    } catch {
      setStatus("error")
    }
  }

  if (status === "done") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-lg border border-gold/40 bg-gold/10 px-3 py-1.5 text-xs font-medium text-navy">
        <svg className="h-3.5 w-3.5 text-gold" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
        Request received — we'll update this within 24 hours
      </span>
    )
  }

  return (
    <button
      onClick={handleRequest}
      disabled={status === "loading"}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition hover:border-navy/40 hover:text-navy disabled:opacity-50"
    >
      {status === "loading" ? (
        <>
          <span className="h-3 w-3 animate-spin rounded-full border border-navy border-t-transparent" />
          Requesting...
        </>
      ) : (
        <>
        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
          {status === "error" ? "Try again" : "Request Latest Data"}
        </>
      )}
    </button>
  )
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
          <div className="flex items-center gap-3 text-muted-foreground">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-navy border-t-transparent" />
            Loading...
          </div>
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
  const latestFinancialYear = financials.length > 0 ? Math.max(...financials.map((f: any) => f.tax_year)) : null

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Link href="/" className="mb-4 inline-block text-sm text-muted-foreground hover:text-navy">
          Back to search
        </Link>

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
                  <span className="ml-2 text-muted-foreground">{org.ntee_category}</span>
                )}
              </p>
            </div>
            <div className="text-right">
              {org.tier && (
                <ScoreBadge tier={org.tier} score={org.score} className="tet-sm" />
              )}
              {org.ceo_name && (
                <p className="mt-2 text-sm">
                  <span className="text-muted-foreground">CEO:</span> {org.ceo_name}
                  {org.ceo_tenure_years != null && (
                    <span className="text-muted-foreground"> · {org.ceo_tenure_years} yr tenure</span>
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

          <div className="mt-5 border-t border-border pt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Transition Signals
            </p>
            <SignalPanel factors={org.factors} />
          </div>
        </div>

        <section className="mb-8">
          <div className="mb-3 fle items-center justify-between gap-4">
            <div>
              <h2 className="font-serif text-xl text-navy">Financial History</h2>
              {latestFinancialYear && (
                <p className="mt-0.5 text-xs text-muted-foreground">
                  IRS 990 data · through {latestFinancialYear} · typically 12-18 months behind filing date
                </p>
              )}
            </div>
            <RequestDataButton ein={org.ein} orgName={org.name} />
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2">Year</th>
                  <th className="px-4 py-2 text-right">Revenue</th>
                  <th className="px-4 py-2 text-right">Expenses</th>
                  <th className="px-4 py-2 text-right">Splus</th>
                  <th className="px-4 py-2 text-right">Assets</th>
                  <th className="px-4 py-2 text-right">YoY %</th>
                </tr>
              </thead>
              <tbody>
                {financials.map((f: any) => {
                  const surplus = f.operating_surplus
                  return (
                    <tr key={f.tax_year} className="border-b border-border/50">
                      <td className="px-4 py-2 font-medium">{f.tax_year}</td>
                      <td className="px-4 py-2 text-right font-mono">{formatCurrency(f.total_revenue)}</td>
                      <td className="px-4 py-2 text-right font-mono">{formatCurrency(f.total_expenses)}</td>
                      <td className={`px-4 py-2 text-right font-mono ${surplus != null && surplus < 0 ? "text-red-600" : ""}`}>
                        {formatCurrency(surplus)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono">{formatCurrency(f.total_assets)}</td>
                      <td className="px-4 py-2 text-right font-mono text-muted-foreground">
                        {f.revenue_yoy_pct != null
                          ? `${f.revenue_yoy_pct > 0 ? "+" : ""}${f.revenue_yoy_pct}%`
                          : "--"}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="mb-3 font-serif text-xl text-navy">Officers & Key Employees</h2>
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
                  <tr key={`${o.tax_year}-${o.person_name}-${i}`} className="border-b border-border/50">
                    <td className="px-4 py-2">{o.tax_year}</td>
                    <td className="px-4 py-2 font-medium">{o.person_name}</td>
                    <td className="px-4 py-2 text-muted-foreground">{o.title || "--"}</td>
                    <td className="px-4 py-2 text-right font-mono">{formatCurrency(o.compensation)}</td>
                    <td className="px-4 py-2 text-right text-muted-foreground">{o.hours_per_week ?? "--"}</td>
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
