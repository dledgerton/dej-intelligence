"use client"

import Link from "next/link"
import { formatCurrency, formatEIN } from "@/lib/utils"
import { ScoreBadge } from "./score-badge"

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
            <th className="px-4 py-3">Score</th>
            <th className="px-4 py-3">CEO</th>
            {showSignal && <th className="px-4 py-3">Signal</th>}
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
                  {row.ntee_code || "—"}
                </span>
              </td>
              <td className="px-4 py-3 text-right font-mono text-sm">
                {formatCurrency(row.total_revenue)}
              </td>
              <td className="px-4 py-3">
                {row.tier ? (
                  <ScoreBadge tier={row.tier} score={row.score} />
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
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
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </td>
              {showSignal && (
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {row.primary_signal || "—"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}