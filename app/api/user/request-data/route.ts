// app/api/user/request-data/route.ts
// Sends a data refresh request email to DEJ Search when a user requests
// latest financials for an organization.

import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'
import { Resend } from 'resend'

const resend = new Resend(process.env.RESEND_API_KEY)

export async function POST(req: NextRequest) {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const user = await currentUser()
  const userEmail = user?.emailAddresses[0]?.emailAddress ?? 'unknown'

  const { ein, orgName } = await req.json()
  if (!ein || !orgName) {
    return NextResponse.json({ error: 'ein and orgName are required' }, { status: 400 })
  }

  const einClean = ein.replace(/-/g, '')
  const propublicaUrl = `https://projects.propublica.org/nonprofits/organizations/${einClean}`

  const htmlBody = [
    '<p><strong>Data refresh requested</strong></p>',
    '<p><strong>Organization:</strong> ' + orgName + '</p>',
    '<p><strong>EIN:</strong> ' + ein + '</p>',
    '<p><strong>Requested by:</strong> ' + userEmail + '</p>',
    '<p><strong>ProPublica:</strong> <a href="' + propublicaUrl + '">View on ProPublica</a></p>',
    '<p>Pull the latest 990 and update the filings table for this org.</p>',
  ].join('')

  try {
    const result = await resend.emails.send({
      from: process.env.RESEND_FROM_EMAIL!,
      to: 'david@dejsearch.com',
      subject: 'Data Refresh Request: ' + orgName,
      html: htmlBody,
    })

    console.log('Resend result:', JSON.stringify(result))
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('Resend error:', JSON.stringify(err))
    return NextResponse.json({ error: 'Failed to send request' }, { status: 500 })
  }
}
