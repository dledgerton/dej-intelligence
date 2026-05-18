import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { clerkClient } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

const isPublicRoute = createRouteMatcher([
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/pricing',
  '/api/webhooks/stripe',
  '/api/stripe/checkout',
])

const isApiRoute = createRouteMatcher(['/api/query/(.*)', '/api/export/(.*)'])
const isUserApiRoute = createRouteMatcher(['/api/user/(.*)'])

export default clerkMiddleware(async (auth, request) => {
  if (isPublicRoute(request)) return

  const { userId } = await auth.protect()

  if ((isApiRoute(request) || isUserApiRoute(request)) && userId) {
    const client = await clerkClient()
    const user = await client.users.getUser(userId)
    const tier = user.publicMetadata?.tier

    if (!tier) {
      return NextResponse.json(
        { error: 'Subscription required', redirect: '/pricing' },
        { status: 402 }
      )
    }
  }
})

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
}
