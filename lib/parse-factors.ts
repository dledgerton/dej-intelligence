// lib/parse-factors.ts
export type FactorSignal = {
  key: string
  label: string
  icon: string
  variant: "danger" | "warning" | "positive" | "neutral"
  detail: string | null
}

type FactorEntry = { value: number | null; label?: string; points: number }

type FactorsShape = {
  revenue_trend?: FactorEntry
  comp_trajectory?: FactorEntry
  deficit_years?: FactorEntry
  ceo_tenure?: FactorEntry
  board_chair_change?: FactorEntry
  signal_leadership?: FactorEntry
  signal_search_rfp?: FactorEntry
}

const REVENUE_MAP: Record<string, { icon: string; variant: FactorSignal["variant"]; display: string }> = {
  strong_growth: { icon: "++", variant: "positive", display: "Strong Revenue Growth" },
  growth:        { icon: "+",  variant: "positive", display: "Revenue Growth" },
  flat:          { icon: "~",  variant: "neutral",  display: "Revenue Flat" },
  stable:        { icon: "~",  variant: "neutral",  display: "Revenue Stable" },
  soft_decline:  { icon: "-",  variant: "warning",  display: "Soft Revenue Decline" },
  decline:       { icon: "--", variant: "danger",   display: "Revenue Decline" },
  steep_decline: { icon: "--", variant: "danger",   display: "Steep Revenue Decline" },
  unknown:       { icon: "?",  variant: "neutral",  display: "Revenue Trend Unknown" },
}

const COMP_MAP: Record<string, { icon: string; variant: FactorSignal["variant"]; display: string }> = {
  strong_growth: { icon: "++", variant: "warning",  display: "Comp Rising Fast" },
  growing:       { icon: "+",  variant: "neutral",  display: "Comp Rising" },
  flat:          { icon: "~",  variant: "positive", display: "Comp Flat" },
  softening:     { icon: "-",  variant: "neutral",  display: "Comp Softening" },
  declining:     { icon: "--", variant: "positive", display: "Comp Declining" },
  unknown:       { icon: "?",  variant: "neutral",  display: "Comp Unknown" },
}

function pct(value: number | null): string | null {
  if (value == null) return null
  const sign = value >= 0 ? "+" : ""
  return `${sign}${(value * 100).toFixed(1)}%`
}

export function parseFactors(raw: string | null | undefined): FactorSignal[] {
  if (!raw) return []
  let factors: FactorsShape
  try { factors = JSON.parse(raw) as FactorsShape } catch { return [] }
  const signals: FactorSignal[] = []

  const rev = factors.revenue_trend
  if (rev) {
    const map = REVENUE_MAP[rev.label ?? "unknown"] ?? REVENUE_MAP.unknown
    signals.push({ key: "revenue_trend", label: map.display, icon: map.icon, variant: map.variant, detail: pct(rev.value) })
  }

  const def = factors.deficit_years
  if (def && def.value != null && def.value > 0) {
    const v = def.value
    signals.push({ key: "deficit_years", label: `${v} Deficit Year${v === 1 ? "" : "s"}`, icon: "!", variant: v >= 4 ? "danger" : v >= 2 ? "warning" : "neutral", detail: null })
  }

  const tenure = factors.ceo_tenure
  if (tenure && tenure.value != null) {
    const yrs = tenure.value
    signals.push({ key: "ceo_tenure", label: `CEO ${yrs.toFixed(1)} yr tenure`, icon: yrs <= 2 ? "*" : "ok", variant: yrs <= 2 ? "warning" : "positive", detail: null })
  }

  const comp = factors.comp_trajectory
  if (comp && comp.label && comp.label !== "unknown") {
    const map = COMP_MAP[comp.label] ?? COMP_MAP.unknown
    signals.push({ key: "comp_trajectory", label: map.display, icon: map.icon, variant: map.variant, detail: pct(comp.value) })
  }

  const board = factors.board_chair_change
  if (board && board.value != null && board.value > 0) {
    signals.push({ key: "board_chair_change", label: "Board Chair Change", icon: "*", variant: "warning", detail: null })
  }

  const lead = factors.signal_leadership
  if (lead && lead.value != null && lead.value > 0) {
    signals.push({ key: "signal_leadership", label: "Leadership Signal", icon: "!", variant: "danger", detail: null })
  }

  const rfp = factors.signal_search_rfp
  if (rfp && rfp.value != null && rfp.value > 0) {
    signals.push({ key: "signal_search_rfp", label: "Active Search", icon: ">>", variant: "danger", detail: null })
  }

  return signals
}

export const VARIANT_CLASSES: Record<FactorSignal["variant"], string> = {
  danger:   "bg-red-50 text-red-700 border border-red-200",
  warning:  "bg-amber-50 text-amber-700 border border-amber-200",
  positive: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  neutral:  "bg-muted text-muted-foreground border border-border",
}