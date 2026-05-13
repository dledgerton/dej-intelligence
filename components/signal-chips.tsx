// components/signal-chips.tsx
import { parseFactors, VARIANT_CLASSES, type FactorSignal } from "@/lib/parse-factors"

export function SignalChips({
  factors,
  max,
}: {
  factors: string | null | undefined
  max?: number
}) {
  const signals = parseFactors(factors)
  if (!signals.length) return <span className="text-xs text-muted-foreground">--</span>

  const visible = max ? signals.slice(0, max) : signals
  const hidden = max ? signals.length - max : 0

  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((s) => (
        <SignalChip key={s.key} signal={s} />
      ))}
      {hidden > 0 && (
        <span className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground border border-border">
          +{hidden} more
        </span>
      )}
    </div>
  )
}

export function SignalChip({ signal }: { signal: FactorSignal }) {
  const classes = VARIANT_CLASSES[signal.variant]
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${classes}`}
      title={signal.detail ?? undefined}
    >
      <span>{signal.icon}</span>
      <span>{signal.label}</span>
      {signal.detail && (
        <span className="opacity-70">{signal.detail}</span>
      )}
    </span>
  )
}

export function SignalPanel({ factors }: { factors: string | null | undefined }) {
  const signals = parseFactors(factors)
  if (!signals.length) {
    return <p className="text-sm text-muted-foreground">No signals computed for this organization.</p>
  }

  const order: FactorSignal["variant"][] = ["danger", "warning", "positive", "neutral"]
  const sorted = [...signals].sort(
    (a, b) => order.indexOf(a.variant) - order.indexOf(b.variant)
  )

  return (
    <div className="flex flex-wrap gap-2">
      {sorted.map((s) => (
        <SignalChip key={s.key} signal={s} />
      ))}
    </div>
  )
}