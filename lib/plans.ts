// lib/plans.ts
export const PLANS = {
    solo: {
      name: 'Solo',
      price: 97,
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