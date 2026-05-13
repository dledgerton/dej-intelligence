// app/api/webhooks/stripe/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { clerkClient } from '@clerk/nextjs/server'
import Stripe from 'stripe'

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2025-03-31.basil',
})

export async function POST(req: NextRequest) {
  const body = await req.text()
  const sig = req.headers.get('stripe-signature')

  if (!sig) {
    return NextResponse.json({ error: 'No signature' }, { status: 400 })
  }

  let event: Stripe.Event
  try {
    event = stripe.webhooks.constructEvent(
      body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    )
  } catch (err) {
    console.error('Webhook signature verification failed:', err)
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 })
  }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session
    const userId = session.metadata?.userId
    const plan = session.metadata?.plan

    if (!userId || !plan) {
      console.error('Missing userId or plan in session metadata')
      return NextResponse.json({ error: 'Missing metadata' }, { status: 400 })
    }

    try {
      const client = await clerkClient()
      await client.users.updateUserMetadata(userId, {
        publicMetadata: {
          tier: plan,
          stripeCustomerId: session.customer,
          stripeSubscriptionId: session.subscription,
        },
      })
      console.log(`Tier set: ${plan} for user ${userId}`)
    } catch (err) {
      console.error('Failed to update Clerk metadata:', err)
      return NextResponse.json({ error: 'Metadata update failed' }, { status: 500 })
    }
  }

  return NextResponse.json({ received: true })
}
