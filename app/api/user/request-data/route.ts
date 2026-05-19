// app/api/user/request-data/route.ts
// Sends a data refresh request email to DEJ Search when a user requests
// latest financials for an organization.

import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'
import { Resend } from 'resend'

const resend = new Resend(process.env.RESEND_API_KEY)

export async function POST(req: NextRequest) {
  console.log('RESEND_API_KEY present:', !!process.env.RESEND_API_KEY)
  console.log('RESEND_FROM_EMAIL:', process.env.RESEND_FROM_EMAIL)
  
  const { userId } = await auth()
  ...
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const user = await currentUser()
  const userEmail = user?.emailAddresses[0]?.emailAddress ?? 'unknown'

  const { ein, orgName } = await req.json()
  if (!ein || !orgName) {
    return NextResponse.json({ error: 'ein and orgName are required' }, { status: 400 })
  }

  try {
    await resend.emails.send({
      from: process.env.RESEND_FROM_EMAIL!,
      to: 'david@dejsearch.com',
      subject: `Data Refresh Request: ${orgName}`,
      html: `
        <p><strong>Data refresh requested</strong></p>
        <p><strong>Organization:</strong> ${orgName}</p>
        <p><strong>EIN:</strong> ${ein}</p>
        <p><strong>Requested by:</strong> ${userEmail}</p>
        <p><strong>ProPublica:</strong> <a href="https://projects.propublica.org/nonprofits/organizations/${ein.replace(/-/g, '')}">View on ProPublica</a></p>
        <p>Pull the latest 990 and update the filings table for this org.</p>
      `,
    })

    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('Resend error:', err)
    return NextResponse.json({ error: 'Failed to send request' }, { status: 500 })
  }
}
