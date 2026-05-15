"use client"

import { useState } from "react"
import { Nav } from "@/components/nav"
import { formatCurrency } from "@/lib/utils"
import { SaveSearchButton } from "@/components/save-search-button"

const STATE_OPTIONS = ["DC", "MD", "VA", "MN", "NY"]
const NTEE_OPTIONS = [
  "A","B","C","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","W","X","Y",
]

export default function SectorPulsePage() {
  const [states, setStates] = useState<string[]>(["DC", "MD", "VA"])
  const [ntee, setNtee] = useState<string[]>(["P"])
  const [years, setYears] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  const toggle = (arr: string[], v: string, set: (a: string[]) => void) =>
    set(arr.includes(v) ? arr.filter((s) => s !== v) : [...arr, v])

  const handleSearch = async () => {
    if (!states.length || !ntee.length) return
    setLoading(true)
    try {
      const params = new URLSearchParams({
        states: states.join(","),
        ntee_major: ntee.join(","),
      })
      const res = await fetch(`/api/query/sector-pulse?${params}`)
      const data = await res.json()
      setYears(data.years ?? [])
      setSearched(true)
    } catch (err) {
      console.error("Sector pulse failed:", err)
    } finally {
      setLoading(false)
    }
  }

  const searchParams = { states: states.join(","), ntee_major: ntee.join(",") }
  const searchName = `Sector Pulse: ${ntee.join(", ")} · ${states.join(", ")}`

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="font-serif text-3xl text-navy">Sector Pulse</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Year-by-year aggregate trends for a sector in your geography. Use
              this to pitch sector expertise.
            </p>
          </div>
          {searched && years.length > 0 && (
            <SaveSearchButton
              name={searchName}
              route="/sector-pulse"
              params={searchParams}
              resultCount={years.length}
            />
          )}
        </div>

        <div className="mb-6 space-y-3 rounded-lg border border-border bg-white p-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Geography
            </p>
            <div className="flex flex-wrap gap-2">
              {STATE_OPTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => toggle(states, s, setStates)}
                  className={`rounded-md border px-3 py-1 text-sm font-medium transition ${
                    states.includes(s)
                      ? "border-navy bg-navy text-white"
                      : "border-border text-muted-foreground hover:border-navy/40"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Sector (select at least one)
            </p>
            <div className="flex flex-wrap gap-1.5">
              {NTEE_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => toggle(ntee, n, setNtee)}
                  className={`rounded border px-2 py-0.5 text-xs font-medium transition ${
                    ntee.includes(n)
                      ? "border-gold bg-gold/10 text-gold-900"
                      : "border-border text-muted-foreground hover:border-gold/40"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={handleSearch}
            disabled={loading || !states.length || !ntee.length}
            className="rounded-md bg-navy px-5 py-2 text-sm font-semibold text-white transition hover:bg-navy/90 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Run Sector Pulse"}
          </button>
        </div>

        {searched && years.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2">Year</th>
                  <th className="px-4 py-2 text-right">Orgs</th>
                  <th className="px-4 py-2 text-right">Avg Revenue</th>
                  <th className="px-4 py-2 text-right">Median Revenue</th>
                  <th className="px-4 py-2 text-right">Deficit %</th>
                  <th className="px-4 py-2 text-right">Critical</th>
                  <th className="px-4 py-2 text-right">High</th>
                </tr>
              </thead>
              <tbody>
                {years.map((y: any) => (
                  <tr key={y.year} className="border-b border-border/50">
                    <td className="px-4 py-2 font-medium">{y.year}</td>
                    <td className="px-4 py-2 text-right">
                      {y.org_count?.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {formatCurrency(y.avg_revenue)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {formatCurrency(y.median_revenue)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {y.deficit_pct != null ? `${Number(y.deficit_pct).toFixed(1)}%` : "—"}
                    </td>
                    <td className="px-4 py-2 text-right text-score-imminent font-semibold">
                      {y.critical_count}
                    </td>
                    <td className="px-4 py-2 text-right text-score-high font-semibold">
                      {y.high_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {searched && years.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No data found for this sector/geography combination.
          </p>
        )}
      </main>
    </>
  )
}
