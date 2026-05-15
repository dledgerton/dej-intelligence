"use client"
// components/save-org-button.tsx
// Bookmark toggle for saving/unsaving an org to the user's watchlist.
// Accepts org fields needed for the saved record.

import { useState } from "react"

interface Props {
  ein: string
  name: string
  city: string
  state: string
  tier: string | null
  score: number | null
  initialSaved?: boolean
}

export function SaveOrgButton({ ein, name, city, state, tier, score, initialSaved = false }: Props) {
  const [saved, setSaved] = useState(initialSaved)
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")

  async function toggle() {
    setLoading(true)
    setErrorMsg("")
    try {
      if (saved) {
        const res = await fetch("/api/user/saved-orgs", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ein }),
        })
        if (!res.ok) throw new Error("Remove failed")
        setSaved(false)
      } else {
        const res = await fetch("/api/user/saved-orgs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ein, name, city, state, tier, score }),
        })
        if (res.status === 403) {
          const data = await res.json()
          setErrorMsg(data.error ?? "Upgrade to save more orgs.")
          return
        }
        if (res.status === 409) {
          setSaved(true) // already saved, sync state
          return
        }
        if (!res.ok) throw new Error("Save failed")
        setSaved(true)
      }
    } catch {
      setErrorMsg("Try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center">
      <button
        onClick={toggle}
        disabled={loading}
        title={saved ? "Remove from watchlist" : "Save to watchlist"}
        className={`rounded p-1 transition ${
          saved
            ? "text-gold hover:text-gold/70"
            : "text-muted-foreground hover:text-navy"
        } disabled:opacity-40`}
      >
        <svg
          className="h-4 w-4"
          fill={saved ? "currentColor" : "none"}
          stroke="currentColor"
          strokeWidth={2}
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
        </svg>
      </button>
      {errorMsg && (
        <span className="mt-1 text-center text-[10px] leading-tight text-red-500 max-w-[80px]">
          {errorMsg}
        </span>
      )}
    </div>
  )
}
