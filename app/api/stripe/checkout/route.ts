// app/api/stripe/checkout/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'
import { stripe } from '@/lib/stripe'
import { type PlanKey } from '@/lib/plans'

const PRICE_IDS: Record<PlanKey, string> = {
  solo:       process.env.STRIPE_PRICE_SOLO_MONTHLY!,
  firm:       process.env.STRIPE_PRICE_FIRM_MONTHLY!,
  enterprise: process.env.STRIPE_PRICE_ENTERPRISE_MONTHLY!,
}

export async function POST(req: NextRequest) {
  const { userId } = await auth()
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const user = await currentUser()
  if (!user) {
    return NextResponse.json({ error: 'User not found' }, { status: 404 })
  }

  const { plan } = await req.json() as { plan: PlanKey }
  if (!plan || !PRICE_IDS[plan]) {
    return NextResponse.json({ error: 'Invalid plan' }, { status: 400 })
  }

  const email = user.emailAddresses[0]?.emailAddress

  const session = await stripe.checkout.sessions.create({
    mode: 'subscription',
    payment_method_types: ['card'],
    customer_email: email,
    line_items: [
      {
        price: PRICE_IDS[plan],
        quantity: 1,
      },
    ],
    metadata: {
      userId,
      plan,
    },
    success_url: `${process.env.NEXT_PUBLIC_APP_URL}/?upgraded=true`,
    cancel_url: `${process.env.NEXT_PUBLIC_APP_URL}/pricing`,
  })

  return NextResponse.json({ url: session.url })
}