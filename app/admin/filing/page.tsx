"use client"

import { useState } from "react"
import { Nav } from "@/components/nav"

const ADMIN_SECRET = process.env.NEXT_PUBLIC_ADMIN_SECRET ?? ""

interface FilingForm {
  ein: string
  tax_year: string
  total_revenue: string
  total_expenses: string
  total_assets: string
  net_assets_eoy: string
  net_assets_boy: string
  total_liabilities: string
  contributions: string
  program_revenue: string
  investment_income: string
  num_employees: string
  source_url: string
}

const empty: FilingForm = {
  ein: "",
  tax_year: "",
  total_revenue: "",
  total_expenses: "",
  total_assets: "",
  net_assets_eoy: "",
  net_assets_boy: "",
  total_liabilities: "",
  contributions: "",
  program_revenue: "",
  investment_income: "",
  num_employees: "",
  source_url: "",
}

function parseNum(v: string) {
  const n = parseFloat(v.replace(/,/g, ""))
  return isNaN(n) ? null : n
}

export default function AdminFilingPage() {
  const [form, setForm] = useState<FilingForm>(empty)
  const [secret, setSecret] = useState("")
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle")
  const [message, setMessage] = useState("")

  function set(field: keyof FilingForm) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  async function handleSubmit() {
    if (!form.ein || !form.tax_year) {
      setMessage("EIN and Tax Year are required.")
      setStatus("error")
      return
    }

    setStatus("loading")
    setMessage("")

    try {
      const res = await fetch("/api/admin/filing", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-admin-secret": secret,
        },
        body: JSON.stringify({
          ein: form.ein,
          tax_year: parseInt(form.tax_year),
          total_revenue: parseNum(form.total_revenue),
          total_expenses: parseNum(form.total_expenses),
          total_assets: parseNum(form.total_assets),
          net_assets_eoy: parseNum(form.net_assets_eoy),
          net_assets_boy: parseNum(form.net_assets_boy),
          total_liabilities: parseNum(form.total_liabilities),
          contributions: parseNum(form.contributions),
          program_revenue: parseNum(form.program_revenue),
          investment_income: parseNum(form.investment_income),
          num_employees: form.num_employees ? parseInt(form.num_employees) : null,
          source_url: form.source_url || null,
        }),
      })

      const data = await res.json()
      if (!res.ok) {
        setMessage(data.error ?? "Something went wrong.")
        setStatus("error")
      } else {
        setMessage(`Filing ${data.action} successfully for EIN ${form.ein} (${form.tax_year}).`)
        setStatus("success")
        setForm(empty)
      }
    } catch {
      setMessage("Network error. Try again.")
      setStatus("error")
    }
  }

  const field = (label: string, key: keyof FilingForm, hint?: string) => (
    <div>
      <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
        {hint && <span className="ml-1 font-normal normal-case text-muted-foreground/70">({hint})</span>}
      </label>
      <input
        type="text"
        value={form[key]}
        onChange={set(key)}
        placeholder={hint ?? ""}
        className="w-full rounded-md border border-border px-3 py-2 text-sm focus:border-navy focus:outline-none focus:ring-1 focus:ring-navy"
      />
    </div>
  )

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-3xl px-6 py-8">
        <div className="mb-6">
          <h1 className="font-serif text-3xl text-navy">Admin — Manual Filing Entry</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Enter financial data from a 990 filing to update an org profile.
            Values in dollars — no commas required but accepted.
          </p>
        </div>

        <div className="mb-6 rounded-lg border border-border bg-white p-6 space-y-4">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Admin Secret
            </label>
            <input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="Enter admin secret"
              className="w-full rounded-md border border-border px-3 py-2 text-sm focus:border-navy focus:outline-none focus:ring-1 focus:ring-navy"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {field("EIN", "ein", "9 digits, no dashes")}
            {field("Tax Year", "tax_year", "e.g. 2022")}
          </div>

          <div className="border-t border-border pt-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Financial Data (Part I)
            </p>
            <div className="grid grid-cols-2 gap-4">
              {field("Total Revenue", "total_revenue", "line 12")}
              {field("Total Expenses", "total_expenses", "line 17")}
              {field("Total Assets EOY", "total_assets", "balance sheet")}
              {field("Net Assets EOY", "net_assets_eoy", "line 22")}
              {field("Net Assets BOY", "net_assets_boy", "prior year")}
              {field("Total Liabilities", "total_liabilities", "balance sheet")}
              {field("Contributions", "contributions", "line 8")}
              {field("Program Revenue", "program_revenue", "line 9")}
              {field("Investment Income", "investment_income", "line 10")}
              {field("Num Employees", "num_employees", "line 5")}
            </div>
          </div>

          <div className="border-t border-border pt-4">
            {field("ProPublica URL", "source_url", "paste the filing URL")}
          </div>

          {message && (
            <div className={`rounded-md px-4 py-3 text-sm ${
              status === "success"
                ? "bg-green-50 text-green-700 border border-green-200"
                : "bg-red-50 text-red-700 border border-red-200"
            }`}>
              {message}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={status === "loading"}
            className="w-full rounded-lg bg-navy px-6 py-3 text-sm font-semibold text-white transition hover:bg-navy/90 disabled:opacity-50"
          >
            {status === "loading" ? "Saving..." : "Save Filing"}
          </button>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          After saving, run the MotherDuck sync script to push changes to production.
        </p>
      </main>
    </>
  )
}
