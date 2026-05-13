// lib/stripe.ts
import 'server-only'
import Stripe from 'stripe'

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2025-02-24.acacia',
})

export const PLANS = {
  solo: {
    name: 'Solo',
    price: 97,
    priceId: process.env.STRIPE_PRICE_SOLO_MONTHLY!,
    description: 'For independent search consultants',
    features: [
      'Full market scan access',
      'Hot list — top 100 transition signals',
      'Sector pulse by NTEE category',
      'Org profiles with financial history',
      'CSV export up to 1,000 rows',
    ],
  },
  firm: {
    name: 'Firm',
    price: 297,
    priceId: process.env.STRIPE_PRICE_FIRM_MONTHLY!,
    description: 'For boutique search firms',
    features: [
      'Everything in Solo',
      'CSV export up to 5,000 rows',
      'Saved searches',
      'Up to 3 team seats',
      'Priority support',
    ],
  },
  enterprise: {
    name: 'Enterprise',
    price: 497,
    priceId: process.env.STRIPE_PRICE_ENTERPRISE_MONTHLY!,
    description: 'For national search practices',
    features: [
      'Everything in Firm',
      'Unlimited CSV export',
      'Unlimited team seats',
      'API access',
      'Custom reporting',
    ],
  },
} as const

export type PlanKey = keyof typeof PLANS