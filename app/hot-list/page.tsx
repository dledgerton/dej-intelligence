"use client"

import { useState } from "react"
import { Nav } from "@/components/nav"
import { OrgTable } from "@/components/org-table"

const STATE_OPTIONS = ["DC", "MD", "VA", "MN", "NY"]

export default function HotListPage() {
  const [states, setStates] = useState<string[]>(["DC", "MD", "VA"])
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  const toggleState = (v: string) =>
    setStates((prev) =>
      prev.includes(v) ? prev.filter((s) => s !== v) : [...prev, v]
    )

  const handleSearch = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        states: states.join(","),
        score_tiers: "imminent,high",
      })
      const res = await fetch(`/api/query/hot-list?${params}`)
      const data = await res.json()
      setResults(data.results ?? [])
      setSearched(true)
    } catch (err) {
      console.error("Hot list fetch failed:", err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6">
          <h1 className="font-serif text-3xl text-navy">Hot List</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Organizations with the highest transition signal — imminent and high
            tiers. These are your BD targets this week.
          </p>
        </div>

        <div className="mb-6 flex flex-wrap items-center gap-3">
          {STATE_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => toggleState(s)}
              className={`rounded-md border px-3 py-1 text-sm font-medium transition ${
                states.includes(s)
                  ? "border-navy bg-navy text-white"
                  : "border-border text-muted-foreground hover:border-navy/40"
              }`}
            >
              {s}
            </button>
          ))}
          <button
            onClick={handleSearch}
            disabled={loading || states.length === 0}
            className="ml-2 rounded-md bg-gold px-5 py-1.5 text-sm font-semibold text-navy transition hover:bg-gold/90 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Pull Hot List"}
          </button>
        </div>

        {searched && (
          <p className="mb-4 text-sm text-muted-foreground">
            {results.length.toLocaleString()} organizations on the hot list
          </p>
        )}

        <OrgTable rows={results} showSignal />
      </main>
    </>
  )
}