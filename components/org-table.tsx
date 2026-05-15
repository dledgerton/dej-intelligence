"use client"
import Link from "next/link"
import { useState } from "react"
import { formatCurrency, formatEIN } from "@/lib/utils"
import { ScoreBadge } from "./score-badge"
import { SignalChips } from "./signal-chips"
import { SaveOrgButton } from "./save-org-button"

type OrgRow = {
  ein: string
  name: string
  city: string
  state: string
  ntee_code: string
  ntee_category: string
  total_revenue: number | null
  score: number | null
  tier: string | null
  ceo_name: string | null
  ceo_tenure_years: number | null
  consecutive_deficit: number | null
  primary_signal?: string | null
  factors?: string | null
}

function ScoreTooltip() {
  const [visible, setVisible] = useState(false)

  return (
    <span className="relative inline-flex items-center">
      <button
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onFocus={() => setVisible(true)}
        onBlur={() => setVisible(false)}
        className="ml-1 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-muted-foreground/30 text-[9px] font-bold text-muted-foreground hover:bg-navy hover:text-white transition"
        aria-label="How scoring works"
      >
        i
      </button>

      {visible && (
        <div className="absolute top-6 left-0 z-[9999] mt-1 w-64 normal-case tracking-normal font-normal text-foreground rounded-lg border border-border bg-white p-3 shadow-lg text-left">
          <p className="mb-2 text-xs font-semibold text-navy">How the score works</p>
          <p className="mb-2 text-xs text-muted-foreground leading-relaxed">
            Each organization is scored 0-100 across two signal layers from IRS 990 filings.
          </p>
          <div className="mb-2 space-y-1">
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Financial (0-70 pts):</span> revenue trend, operating deficits, compensation trajectory.
            </p>
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Leadership (0-30 pts):</span> CEO tenure and compensation relative to sector peers.
            </p>
          </div>
          <div className="space-y-1 border-t border-border pt-2">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-score-imminent shrink-0" />
              <span className="text-xs text-muted-foreground"><span className="font-medium text-foreground">Critical</span> — 80-100. Multiple factors firing.</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-score-high shrink-0" />
              <span className="text-xs text-muted-foreground"><span className="font-medium text-foreground">High</span> — 60-79. Strong signal.</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-score-elevated shrink-0" />
              <span className="text-xs text-muted-foreground"><span className="font-medium text-foreground">Elevated</span> — 40-59. Worth monitoring.</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-score-low shrink-0" />
              <span className="text-xs text-muted-foreground"><span className="font-medium text-foreground">Low</span> — 0-39. Minimal signal.</span>
            </div>
          </div>
          
        </div>
      )}
    </span>
  )
}

export function OrgTable({
  rows,
  showSignal = false,
}: {
  rows: OrgRow[]
  showSignal?: boolean
}) {
  if (!rows.length) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        No organizations match your filters.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <th className="px-4 py-3">Organization</th>
            <th className="px-4 py-3">Location</th>
            <th className="px-4 py-3">Sector</th>
            <th className="px-4 py-3 text-right">Revenue</th>
            <th className="px-4 py-3">
              <span className="inline-flex items-center">
                Score
                <ScoreTooltip />
              </span>
            </th>
            <th className="px-4 py-3">CEO</th>
            <th className="px-4 py-3">Signals</th>
            <th className="px-4 py-3" title="Save to watchlist" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.ein}
              className="border-b border-border/50 transition hover:bg-muted/30"
            >
              <td className="px-4 py-3">
                <Link
                  href={`/org/${row.ein}`}
                  className="font-medium text-navy hover:underline"
                >
                  {row.name}
                </Link>
                <p className="text-xs text-muted-foreground">
                  {formatEIN(row.ein)}
                </p>
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {row.city}, {row.state}
              </td>
              <td className="px-4 py-3">
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">
                  {row.ntee_code || "--"}
                </span>
              </td>
              <td className="px-4 py-3 text-right font-mono text-sm">
                {formatCurrency(row.total_revenue)}
              </td>
              <td className="px-4 py-3">
                {row.tier ? (
                  <ScoreBadge tier={row.tier} score={row.score} />
                ) : (
                  <span className="text-xs text-muted-foreground">--</span>
                )}
              </td>
              <td className="px-4 py-3">
                {row.ceo_name ? (
                  <div>
                    <p className="text-sm">{row.ceo_name}</p>
                    {row.ceo_tenure_years != null && (
                      <p className="text-xs text-muted-foreground">
                        {row.ceo_tenure_years} yr tenure
                      </p>
                    )}
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">--</span>
                )}
              </td>
              <td className="px-4 py-3 min-w-[200px]">
                <SignalChips factors={row.factors} max={2} />
              </td>
              <td className="px-4 py-3">
                <SaveOrgButton
                  ein={row.ein}
                  name={row.name}
                  city={row.city ?? ""}
                  state={row.state ?? ""}
                  tier={row.tier}
                  score={row.score}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
