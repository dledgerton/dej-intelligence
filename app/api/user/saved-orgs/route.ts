// app/api/user/saved-orgs/route.ts
// GET  — list saved orgs for current user
// POST — save an org to watchlist
// DELETE — remove an org by ein

import { NextRequest, NextResponse } from 'next/server'
import { auth, clerkClient } from '@clerk/nextjs/server'

export interface SavedOrg {
  ein: string
  name: string
  city: string
  state: string
  tier: string | null
  score: number | null
  savedAt: string // ISO timestamp
}

async function getClient() {
  return await clerkClient()
}

export async function GET() {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const client = await getClient()
  const user = await client.users.getUser(userId)
  const orgs = (user.privateMetadata?.savedOrgs ?? []) as SavedOrg[]
  return NextResponse.json({ orgs })
}

export async function POST(req: NextRequest) {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await req.json()
  const { ein, name, city, state, tier, score } = body

  if (!ein || !name) {
    return NextResponse.json({ error: 'ein and name are required' }, { status: 400 })
  }

  const client = await getClient()
  const user = await client.users.getUser(userId)
  const existing = (user.privateMetadata?.savedOrgs ?? []) as SavedOrg[]

  // Check tier watchlist limit
  const userTier = user.publicMetadata?.tier as string | undefined
  const watchlistLimits: Record<string, number> = { trial: 1, solo: 3, firm: 10, enterprise: Infinity }
  // Watchlist limit is per-list; treat all saved orgs as one list with a max count
  const orgLimits: Record<string, number> = { trial: 25, solo: 100, firm: 500, enterprise: Infinity }
  const limit = orgLimits[userTier ?? 'trial'] ?? 25

  if (existing.length >= limit) {
    return NextResponse.json(
      { error: `Your plan allows ${limit} saved org${limit === 1 ? '' : 's'}. Upgrade to save more.` },
      { status: 403 }
    )
  }

  // Dedupe — don't save same org twice
  if (existing.some((o) => o.ein === ein)) {
    return NextResponse.json({ error: 'Already saved' }, { status: 409 })
  }

  const newOrg: SavedOrg = {
    ein,
    name,
    city: city ?? '',
    state: state ?? '',
    tier: tier ?? null,
    score: score ?? null,
    savedAt: new Date().toISOString(),
  }

  await client.users.updateUserMetadata(userId, {
    privateMetadata: {
      ...user.privateMetadata,
      savedOrgs: [...existing, newOrg],
    },
  })

  return NextResponse.json({ org: newOrg })
}

export async function DELETE(req: NextRequest) {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { ein } = await req.json()
  if (!ein) return NextResponse.json({ error: 'ein is required' }, { status: 400 })

  const client = await getClient()
  const user = await client.users.getUser(userId)
  const existing = (user.privateMetadata?.savedOrgs ?? []) as SavedOrg[]

  await client.users.updateUserMetadata(userId, {
    privateMetadata: {
      ...user.privateMetadata,
      savedOrgs: existing.filter((o) => o.ein !== ein),
    },
  })

  return NextResponse.json({ ok: true })
}
