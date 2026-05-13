import { cn } from "@/lib/utils"

const tierConfig = {
  CRITICAL: { bg: "bg-score-imminent", text: "text-white", label: "Critical" },
  imminent: { bg: "bg-score-imminent", text: "text-white", label: "Critical" },
  HIGH: { bg: "bg-score-high", text: "text-white", label: "High" },
  high: { bg: "bg-score-high", text: "text-white", label: "High" },
  ELEVATED: { bg: "bg-score-elevated", text: "text-white", label: "Elevated" },
  elevated: { bg: "bg-score-elevated", text: "text-white", label: "Elevated" },
  LOW: { bg: "bg-score-low", text: "text-white", label: "Low" },
  low: { bg: "bg-score-low", text: "text-white", label: "Low" },
} as const

export function ScoreBadge({
  tier,
  score,
  className,
}: {
  tier: string
  score?: number | null
  className?: string
}) {
  const config = tierConfig[tier as keyof typeof tierConfig] ?? tierConfig.low
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        config.bg,
        config.text,
        className
      )}
    >
      {score != null && <span>{score}</span>}
      {config.label}
    </span>
  )
}