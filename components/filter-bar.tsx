"use client"

import { useState } from "react"

const STATE_OPTIONS = [
  { value: "DC", label: "DC" },
  { value: "MD", label: "Maryland" },
  { value: "VA", label: "Virginia" },
  { value: "MN", label: "Minnesota" },
  { value: "NY", label: "New York" },
]

const NTEE_OPTIONS = [
  { value: "A", label: "A — Arts & Culture" },
  { value: "B", label: "B — Education" },
  { value: "C", label: "C — Environment" },
  { value: "E", label: "E — Health" },
  { value: "F", label: "F — Mental Health" },
  { value: "G", label: "G — Disease/Disorder" },
  { value: "H", label: "H — Medical Research" },
  { value: "I", label: "I — Crime/Legal" },
  { value: "J", label: "J — Employment" },
  { value: "K", label: "K — Food/Nutrition" },
  { value: "L", label: "L — Housing" },
  { value: "M", label: "M — Public Safety" },
  { value: "N", label: "N — Recreation" },
  { value: "O", label: "O — Youth Development" },
  { value: "P", label: "P — Human Services" },
  { value: "Q", label: "Q — International" },
  { value: "R", label: "R — Civil Rights" },
  { value: "S", label: "S — Community" },
  { value: "T", label: "T — Philanthropy" },
  { value: "U", label: "U — Science" },
  { value: "W", label: "W — Public Policy" },
  { value: "X", label: "X — Religion" },
  { value: "Y", label: "Y — Mutual Benefit" },
]

const REVENUE_OPTIONS = [
  { value: "0-1000000", label: "Under $1M" },
  { value: "1000000-5000000", label: "$1M – $5M" },
  { value: "5000000-25000000", label: "$5M – $25M" },
  { value: "25000000-100000000", label: "$25M – $100M" },
  { value: "100000000-999999999", label: "$100M+" },
]

export type FilterValues = {
  states: string[]
  ntee_major: string[]
  rev_min: number
  rev_max: number
}

export function FilterBar({
  onApply,
  loading,
}: {
  onApply: (filters: FilterValues) => void
  loading?: boolean
}) {
  const [states, setStates] = useState<string[]>(["DC", "MD", "VA"])
  const [ntee, setNtee] = useState<string[]>([])
  const [revenue, setRevenue] = useState("0-999999999")

  const toggleState = (v: string) =>
    setStates((prev) =>
      prev.includes(v) ? prev.filter((s) => s !== v) : [...prev, v]
    )

  const toggleNtee = (v: string) =>
    setNtee((prev) =>
      prev.includes(v) ? prev.filter((s) => s !== v) : [...prev, v]
    )

  const handleApply = () => {
    const [revMin, revMax] = revenue.split("-").map(Number)
    onApply({ states, ntee_major: ntee, rev_min: revMin, rev_max: revMax })
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-white p-4">
      {/* States */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Geography
        </p>
        <div className="flex flex-wrap gap-2">
          {STATE_OPTIONS.map((s) => (
            <button
              key={s.value}
              onClick={() => toggleState(s.value)}
              className={`rounded-md border px-3 py-1 text-sm font-medium transition ${
                states.includes(s.value)
                  ? "border-navy bg-navy text-white"
                  : "border-border text-muted-foreground hover:border-navy/40"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* NTEE */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Sector (NTEE)
        </p>
        <div className="flex flex-wrap gap-1.5">
          {NTEE_OPTIONS.map((n) => (
            <button
              key={n.value}
              onClick={() => toggleNtee(n.value)}
              className={`rounded border px-2 py-0.5 text-xs font-medium transition ${
                ntee.includes(n.value)
                  ? "border-gold bg-gold/10 text-gold-900"
                  : "border-border text-muted-foreground hover:border-gold/40"
              }`}
            >
              {n.value}
            </button>
          ))}
        </div>
      </div>

      {/* Revenue */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Revenue Band
        </p>
        <select
          value={revenue}
          onChange={(e) => setRevenue(e.target.value)}
          className="rounded-md border border-border bg-white px-3 py-1.5 text-sm text-foreground"
        >
          <option value="0-999999999">All Revenue</option>
          {REVENUE_OPTIONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      {/* Apply */}
      <button
        onClick={handleApply}
        disabled={loading || states.length === 0}
        className="rounded-md bg-navy px-5 py-2 text-sm font-semibold text-white transition hover:bg-navy/90 disabled:opacity-50"
      >
        {loading ? "Searching…" : "Search"}
      </button>
    </div>
  )
}