"use client"
// components/save-search-button.tsx
// Renders a bookmark button that saves the current search to the user's dashboard.
// Props mirror what each page already has in state.

import { useState } from "react"

interface Props {
  name?: string          // pre-filled name (e.g. "Hot List: DC, MD, VA")
  route: string          // '/hot-list' | '/' | '/sector-pulse'
  params: Record<string, string>
  resultCount?: number   // current result count to store as lastCount
}

export function SaveSearchButton({ name: defaultName, route, params, resultCount }: Props) {
  const [status, setStatus] = useState<"idle" | "naming" | "saving" | "saved" | "error">("idle")
  const [inputName, setInputName] = useState(defaultName ?? "")
  const [errorMsg, setErrorMsg] = useState("")

  async function handleSave() {
    if (!inputName.trim()) return
    setStatus("saving")
    try {
      const res = await fetch("/api/user/saved-searches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: inputName.trim(),
          route,
          params,
          lastCount: resultCount ?? null,
        }),
      })
      if (res.status === 403) {
        const data = await res.json()
        setErrorMsg(data.error ?? "Upgrade to save more searches.")
        setStatus("error")
        return
      }
      if (!res.ok) throw new Error("Save failed")
      setStatus("saved")
    } catch {
      setStatus("error")
      setErrorMsg("Something went wrong. Try again.")
    }
  }

  if (status === "saved") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-lg border border-gold/40 bg-gold/10 px-3 py-1.5 text-sm font-medium text-navy">
        <svg className="h-3.5 w-3.5 text-gold" fill="currentColor" viewBox="0 0 20 20">
          <path d="M5 4a2 2 0 012-2h6a2 2 0 012 2v14l-5-2.5L5 18V4z" />
        </svg>
        Saved
      </span>
    )
  }

  if (status === "naming" || status === "saving" || status === "error") {
    return (
      <div className="flex items-center gap-2">
        <input
          autoFocus
          type="text"
          value={inputName}
          onChange={(e) => { setInputName(e.target.value); setErrorMsg("") }}
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setStatus("idle") }}
          placeholder="Name this search…"
          className="rounded-md border border-border px-3 py-1.5 text-sm focus:border-navy focus:outline-none focus:ring-1 focus:ring-navy"
        />
        <button
          onClick={handleSave}
          disabled={status === "saving" || !inputName.trim()}
          className="rounded-md bg-navy px-3 py-1.5 text-sm font-medium text-white transition hover:bg-navy/90 disabled:opacity-50"
        >
          {status === "saving" ? "Saving…" : "Save"}
        </button>
        <button
          onClick={() => { setStatus("idle"); setErrorMsg("") }}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Cancel
        </button>
        {errorMsg && (
          <span className="text-xs text-red-500">{errorMsg}</span>
        )}
      </div>
    )
  }

  // idle
  return (
    <button
      onClick={() => setStatus("naming")}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-muted-foreground transition hover:border-navy/40 hover:text-navy"
    >
      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
      </svg>
      Save Search
    </button>
  )
}
