import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format USD currency with sensible defaults.
 * formatCurrency(4520000) => "$4.5M"
 * formatCurrency(4520000, { style: "full" }) => "$4,520,000"
 */
export function formatCurrency(
  value: number | null | undefined,
  opts: { style?: "compact" | "full" } = {},
): string {
  if (value == null) return "—";
  if (opts.style === "full") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(value);
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/**
 * EIN formatter: "521447813" => "52-1447813"
 */
export function formatEIN(ein: string | null | undefined): string {
  if (!ein) return "—";
  const cleaned = ein.replace(/\D/g, "");
  if (cleaned.length !== 9) return ein;
  return `${cleaned.slice(0, 2)}-${cleaned.slice(2)}`;
}

/**
 * Score tier from numeric score.
 */
export function scoreTier(score: number): "low" | "elevated" | "high" | "imminent" {
  if (score >= 80) return "imminent";
  if (score >= 60) return "high";
  if (score >= 30) return "elevated";
  return "low";
}
