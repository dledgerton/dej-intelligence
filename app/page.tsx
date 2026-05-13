"use client"

import { useState } from "react"
import { Nav } from "@/components/nav"
import { FilterBar, FilterValues } from "@/components/filter-bar"
import { OrgTable } from "@/components/org-table"

export default function MarketScanPage() {
  const [results, setResults] = useState<any[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSearch = async (filters: FilterValues) => {
    setLoading(true)
    const params = new URLSearchParams({
      states: filters.states.join(","),
      rev_min: String(filters.rev_min),
      rev_max: String(filters.rev_max),
      limit: "100",
    })
    if (filters.ntee_major.length > 0) {
      params.set("ntee_major", filters.ntee_major.join(","))
    }

    try {
      const res = await fetch(`/api/query/market-scan?${params}`)
      const data = await res.json()
      setResults(data.results ?? [])
      setTotal(data.total ?? 0)
    } catch (err) {
      console.error("Search failed:", err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6">
          <h1 className="font-serif text-3xl text-navy">Market Scan</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Search scored nonprofit organizations by geography, sector, and
            revenue. Click any org for a full profile.
          </p>
        </div>

        <FilterBar onApply={handleSearch} loading={loading} />

        {total !== null && (
          <p className="mt-6 text-sm text-muted-foreground">
            {total.toLocaleString()} organizations found
            {results.length < total && ` · showing first ${results.length}`}
          </p>
        )}

        <div className="mt-4">
          <OrgTable rows={results} />
        </div>
      </main>
    </>
  )
}