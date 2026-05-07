/**
 * Tier definitions. Single source of truth for pricing, quotas, and features.
 * Stripe price IDs come from environment variables.
 */

export type Tier = "trial" | "solo" | "firm" | "enterprise";

export interface TierConfig {
  name: string;
  monthlyPrice: number;
  annualPrice: number;
  briefsPerMonth: number;
  searchesPerDay: number;
  watchlists: number;
  seats: number;
  apiAccess: boolean;
  stripePriceMonthly?: string;
  stripePriceAnnual?: string;
}

export const TIERS: Record<Tier, TierConfig> = {
  trial: {
    name: "Trial",
    monthlyPrice: 0,
    annualPrice: 0,
    briefsPerMonth: 5,
    searchesPerDay: 50,
    watchlists: 1,
    seats: 1,
    apiAccess: false,
  },
  solo: {
    name: "Solo",
    monthlyPrice: 97,
    annualPrice: 970,
    briefsPerMonth: 25,
    searchesPerDay: 100,
    watchlists: 3,
    seats: 1,
    apiAccess: false,
    stripePriceMonthly: process.env.STRIPE_PRICE_SOLO_MONTHLY,
    stripePriceAnnual: process.env.STRIPE_PRICE_SOLO_ANNUAL,
  },
  firm: {
    name: "Firm",
    monthlyPrice: 297,
    annualPrice: 2970,
    briefsPerMonth: 100,
    searchesPerDay: 500,
    watchlists: 10,
    seats: 3,
    apiAccess: false,
    stripePriceMonthly: process.env.STRIPE_PRICE_FIRM_MONTHLY,
    stripePriceAnnual: process.env.STRIPE_PRICE_FIRM_ANNUAL,
  },
  enterprise: {
    name: "Enterprise",
    monthlyPrice: 497,
    annualPrice: 4970,
    briefsPerMonth: Infinity,
    searchesPerDay: Infinity,
    watchlists: Infinity,
    seats: 5,
    apiAccess: true,
    stripePriceMonthly: process.env.STRIPE_PRICE_ENTERPRISE_MONTHLY,
    stripePriceAnnual: process.env.STRIPE_PRICE_ENTERPRISE_ANNUAL,
  },
};

export function canGenerateBrief(tier: Tier, briefsUsedMonth: number): boolean {
  return briefsUsedMonth < TIERS[tier].briefsPerMonth;
}

export function canCreateWatchlist(tier: Tier, watchlistsUsed: number): boolean {
  return watchlistsUsed < TIERS[tier].watchlists;
}
