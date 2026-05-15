"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Nav } from "@/components/nav"
import { PLANS, type PlanKey } from "@/lib/plans"

export default function PricingPage() {
  const router = useRouter()
  const [loading, setLoading] = useState<PlanKey | null>(null)

  async function handleCheckout(plan: PlanKey) {
    setLoading(plan)
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan }),
      })
      const data = await res.json()
      if (data.url) {
        router.push(data.url)
      } else {
        console.error("No checkout URL returned", data)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(null)
    }
  }

  function getCtaLabel(key: PlanKey, plan: typeof PLANS[PlanKey], isLoading: boolean) {
    if (isLoading) return "Redirecting..."
    if (plan.trial) return `Start ${plan.trialDays}-Day Free Trial`
    return `Start ${plan.name}`
  }

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-6 py-16">
        <div className="mb-12 text-center">
          <h1 className="font-serif text-4xl text-navy">
            Intelligence for Nonprofit Search
          </h1>
          <p className="mt-3 text-lg text-muted-foreground">
            237,000+ scored organizations. Real transition signals. Built for search consultants.
          </p>
          <p className="mt-2 text-sm text-green-600 font-medium">
            Try Solo free for 14 days. No charge until your trial ends.
          </p>
        </div>

        <div className="grid gap-8 md:grid-cols-3">
          {(Object.entries(PLANS) as [PlanKey, typeof PLANS[PlanKey]][]).map(
            ([key, plan]) => (
              <div
                key={key}
                className={`relative flex flex-col rounded-xl border p-8 ${
                  key === "firm"
                    ? "border-gold bg-navy text-white shadow-xl"
                    : "border-border bg-white"
                }`}
              >
                {key === "firm" && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="rounded-full bg-gold px-3 py-1 text-xs font-semibold text-navy">
                      Most Popular
                    </span>
                  </div>
                )}

                {key === "solo" && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="rounded-full bg-green-600 px-3 py-1 text-xs font-semibold text-white">
                      14-Day Free Trial
                    </span>
                  </div>
                )}

                <div className="mb-6">
                  <h2
                    className={`font-serif text-2xl ${
                      key === "firm" ? "text-white" : "text-navy"
                    }`}
                  >
                    {plan.name}
                  </h2>
                  <p
                    className={`mt-1 text-sm ${
                      key === "firm" ? "text-white/70" : "text-muted-foreground"
                    }`}
                  >
                    {plan.description}
                  </p>
                  <div className="mt-4 flex items-baseline gap-1">
                    <span
                      className={`font-serif text-4xl font-bold ${
                        key === "firm" ? "text-gold" : "text-navy"
                      }`}
                    >
                      ${plan.price}
                    </span>
                    <span
                      className={`text-sm ${
                        key === "firm" ? "text-white/70" : "text-muted-foreground"
                      }`}
                    >
                      /month
                    </span>
                  </div>
                  {plan.trial && (
                    <p className="mt-1 text-xs text-green-600 font-medium">
                      Free for {plan.trialDays} days, then ${plan.price}/mo
                    </p>
                  )}
                </div>

                <ul className="mb-8 flex-1 space-y-3">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm">
                      <svg
                        className={`mt-0.5 h-4 w-4 shrink-0 ${
                          key === "firm" ? "text-gold" : "text-navy"
                        }`}
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2.5}
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                      </svg>
                      <span
                        className={
                          key === "firm" ? "text-white/90" : "text-foreground"
                        }
                      >
                        {feature}
                      </span>
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => handleCheckout(key)}
                  disabled={loading === key}
                  className={`w-full rounded-lg px-6 py-3 text-sm font-semibold transition disabled:opacity-60 ${
                    key === "solo"
                      ? "bg-green-600 text-white hover:bg-green-700"
                      : key === "firm"
                      ? "bg-gold text-navy hover:bg-gold/90"
                      : "bg-navy text-white hover:bg-navy/90"
                  }`}
                >
                  {getCtaLabel(key, plan, loading === key)}
                </button>
              </div>
            )
          )}
        </div>

        <p className="mt-10 text-center text-sm text-muted-foreground">
          All plans billed monthly. Cancel anytime. Card required to start trial.
        </p>
      </main>
    </>
  )
}
