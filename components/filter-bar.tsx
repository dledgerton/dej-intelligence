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
  "A","B","C","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U","W","X","Y",
]

const REVENUE_OPTIONS = [
  { value: "0-999999999", label: "All Revenue" },
  { value: "0-1000000", label: "Under $1M" },
  { value: "1000000-5000000", label: "$1M – $5M" },
  { value: "5000000-25000000", label: "$5M – $25M" },
  { value: "25000000-100000000", label: "$25M – $100M" },
  { value: "100000000-999999999", label: "$100M+" },
]

export function FilterBar({
  initialValues,
  onChange,
}: {
  initialValues: Record<string, string>
  onChange: (filters: Record<string, string>) => void
}) {
  const [states, setStates] = useState<string[]>(
    initialValues.states ? initialValues.states.split(",") : ["DC", "MD", "VA", "MN"]
  )
  const [ntee, setNtee] = useState<string[]>(
    initialValues.ntee_major ? initialValues.ntee_major.split(",").filter(Boolean) : []
  )
  const [revenue, setRevenue] = useState(
    `${initialValues.rev_min ?? "0"}-${initialValues.rev_max ?? "999999999"}`
  )

  const toggleState = (v: string) =>
    setStates((prev) => prev.includes(v) ? prev.filter((s) => s !== v) : [...prev, v])

  const toggleNtee = (v: string) =>
    setNtee((prev) => prev.includes(v) ? prev.filter((s) => s !== v) : [...prev, v])

  const handleApply = () => {
    const [rev_min, rev_max] = revenue.split("-")
    onChange({
      states: states.join(","),
      ntee_major: ntee.join(","),
      rev_min,
      rev_max,
    })
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-white p-4">
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

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Sector (NTEE)
        </p>
        <div className="flex flex-wrap gap-1.5">
          {NTEE_OPTIONS.map((n) => (
            <button
              key={n}
              onClick={() => toggleNtee(n)}
              className={`rounded border px-2 py-0.5 text-xs font-medium transition ${
                ntee.includes(n)
                  ? "border-gold bg-gold/10 text-navy"
                  : "border-border text-muted-foreground hover:border-gold/40"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Revenue Band
        </p>
        <select
          value={revenue}
          onChange={(e) => setRevenue(e.target.value)}
          className="rounded-md border border-border bg-white px-3 py-1.5 text-sm text-foreground"
        >
          {REVENUE_OPTIONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </div>

      <button
        onClick={handleApply}
        disabled={states.length === 0}
        className="rounded-md bg-navy px-5 py-2 text-sm font-semibold text-white transition hover:bg-navy/90 disabled:opacity-50"
      >
        Search
      </button>
    </div>
  )
}