"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Nav } from "@/components/nav"
import { OrgTable } from "@/components/org-table"
import { FilterBar } from "@/components/filter-bar"

const PAGE_SIZE_OPTIONS = [25, 50, 100]

function buildParams(filters: Record<string, string>, page: number, pageSize: number) {
  const params = new URLSearchParams(filters)
  params.set("limit", String(pageSize))
  params.set("offset", String((page - 1) * pageSize))
  return params
}

function getPaginationRange(current: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | "...")[] = []
  const addPage = (p: number) => { if (!pages.includes(p)) pages.push(p) }
  addPage(1)
  if (current > 3) pages.push("...")
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) addPage(p)
  if (current < total - 2) pages.push("...")
  addPage(total)
  return pages
}

export default function MarketScanPage() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [filters, setFilters] = useState<Record<string, string>>({
    states: searchParams.get("states") ?? "DC,MD,VA,MN",
    ntee_major: searchParams.get("ntee_major") ?? "",
    rev_min: searchParams.get("rev_min") ?? "0",
    rev_max: searchParams.get("rev_max") ?? "999999999",
  })
  const [page, setPage] = useState(Number(searchParams.get("page") ?? 1))
  const [pageSize, setPageSize] = useState(Number(searchParams.get("pageSize") ?? 50))
  const [results, setResults] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const fetchResults = useCallback(async () => {
    setLoading(true)
    try {
      const params = buildParams(filters, page, pageSize)
      const res = await fetch(`/api/query/market-scan?${params}`)
      if (res.status === 402) {
        window.location.href = '/pricing'
        return
      }
      if (!res.ok) throw new Error("Query failed")
      const data = await res.json()
      setResults(data.results ?? [])
      setTotal(data.total ?? 0)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [filters, page, pageSize])

  useEffect(() => {
    const params = new URLSearchParams({
      ...filters,
      page: String(page),
      pageSize: String(pageSize),
    })
    router.replace(`?${params}`, { scroll: false })
  }, [filters, page, pageSize, router])

  useEffect(() => {
    fetchResults()
  }, [fetchResults])

  function handleFilterChange(newFilters: Record<string, string>) {
    setFilters(newFilters)
    setPage(1)
  }

  async function handleExport() {
    setExporting(true)
    try {
      const params = buildParams(filters, 1, 5000)
      const res = await fetch(`/api/export/market-scan?${params}`)
      if (!res.ok) throw new Error("Export failed")
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `dej-market-scan-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error(e)
    } finally {
      setExporting(false)
    }
  }

  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="font-serif text-3xl text-navy">Market Scan</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Scored nonprofit organizations ranked by transition signal strength
            </p>
          </div>
          <button
            onClick={handleExport}
            disabled={exporting || total === 0}
            className="inline-flex items-center gap-2 rounded-lg border border-gold bg-white px-4 py-2 text-sm font-medium text-navy transition hover:bg-gold/10 disabled:opacity-50"
          >
            {exporting ? "Exporting..." : "Export CSV"}
          </button>
        </div>

        <FilterBar initialValues={filters} onChange={handleFilterChange} />

        <div className="mt-6 mb-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {loading ? "Loading..." : total === 0 ? "No results" : (
              <>Showing <span className="font-medium text-foreground">{from}-{to}</span> of{" "}
              <span className="font-medium text-foreground">{total.toLocaleString()}</span> organizations</>
            )}
          </p>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Per page:</span>
            {PAGE_SIZE_OPTIONS.map((size) => (
              <button
                key={size}
                onClick={() => { setPageSize(size); setPage(1) }}
                className={`rounded px-2.5 py-1 font-medium transition ${
                  pageSize === size ? "bg-navy text-white" : "text-muted-foreground hover:text-navy"
                }`}
              >
                {size}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-navy border-t-transparent" />
          </div>
        ) : (
          <OrgTable rows={results} showSignal />
        )}

        {!loading && totalPages > 1 && (
          <div className="mt-6 flex items-center justify-between">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-navy transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <div className="flex items-center gap-1">
              {getPaginationRange(page, totalPages).map((p, i) =>
                p === "..." ? (
                  <span key={`e-${i}`} className="px-2 text-muted-foreground">...</span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(Number(p))}
                    className={`min-w-[36px] rounded px-2 py-1 text-sm font-medium transition ${
                      p === page ? "bg-navy text-white" : "text-muted-foreground hover:text-navy"
                    }`}
                  >
                    {p}
                  </button>
                )
              )}
            </div>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-navy transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </main>
    </>
  )
}