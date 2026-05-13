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

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-6 py-16">
        <div className="mb-12 text-center">
          <h1 className="font-serif text-4xl text-navy">
            Intelligence for Nonprofit Search
          </h1>
          <p className="mt-3 text-lg text-muted-foreground">
            44,000+ scored organizations. Real transition signals. Built for search consultants.
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
                </div>

                <ul className="mb-8 flex-1 space-y-3">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm">
                      <span
                        className={`mt-0.5 text-xs ${
                          key === "firm" ? "text-gold" : "text-navy"
                        }`}
                      >
                        ok
                      </span>
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
                    key === "firm"
                      ? "bg-gold text-navy hover:bg-gold/90"
                      : "bg-navy text-white hover:bg-navy/90"
                  }`}
                >
                  {loading === key ? "Redirecting..." : `Start ${plan.name}`}
                </button>
              </div>
            )
          )}
        </div>

        <p className="mt-10 text-center text-sm text-muted-foreground">
          All plans billed monthly. Cancel anytime. Test mode — no real charges.
        </p>
      </main>
    </>
  )
}