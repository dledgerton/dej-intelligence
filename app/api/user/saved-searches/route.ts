// app/api/user/saved-searches/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { auth, clerkClient } from '@clerk/nextjs/server'

export interface SavedSearch {
  id: string
  name: string
  route: string
  params: Record<string, string>
  lastCount: number | null
  lastRun: string | null
  savedAt: string
}

async function getClient() {
  return await clerkClient()
}

export async function GET() {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  const client = await getClient()
  const user = await client.users.getUser(userId)
  const searches = (user.privateMetadata?.savedSearches ?? []) as SavedSearch[]
  return NextResponse.json({ searches })
}

export async function POST(req: NextRequest) {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  const body = await req.json()
  const { name, route, params, lastCount } = body
  if (!name || !route || !params) {
    return NextResponse.json({ error: 'name, route, and params are required' }, { status: 400 })
  }
  const client = await getClient()
  const user = await client.users.getUser(userId)
  const existing = (user.privateMetadata?.savedSearches ?? []) as SavedSearch[]
  const tier = user.publicMetadata?.tier as string | undefined
  const tierLimits: Record<string, number> = { trial: 1, solo: 3, firm: 10, enterprise: Infinity }
  const limit = tierLimits[tier ?? 'trial'] ?? 1
  if (existing.length >= limit) {
    return NextResponse.json(
      { error: `Your plan allows ${limit} saved search${limit === 1 ? '' : 'es'}. Upgrade to save more.` },
      { status: 403 }
    )
  }
  const newSearch: SavedSearch = {
    id: crypto.randomUUID(),
    name,
    route,
    params,
    lastCount: lastCount ?? null,
    lastRun: new Date().toISOString(),
    savedAt: new Date().toISOString(),
  }
  await client.users.updateUserMetadata(userId, {
    privateMetadata: {
      ...user.privateMetadata,
      savedSearches: [...existing, newSearch],
    },
  })
  return NextResponse.json({ search: newSearch })
}

export async function DELETE(req: NextRequest) {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  const { id } = await req.json()
  if (!id) return NextResponse.json({ error: 'id is required' }, { status: 400 })
  const client = await getClient()
  const user = await client.users.getUser(userId)
  const existing = (user.privateMetadata?.savedSearches ?? []) as SavedSearch[]
  await client.users.updateUserMetadata(userId, {
    privateMetadata: {
      ...user.privateMetadata,
      savedSearches: existing.filter((s) => s.id !== id),
    },
  })
  return NextResponse.json({ ok: true })
}
