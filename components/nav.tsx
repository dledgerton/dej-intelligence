"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useClerk } from "@clerk/nextjs"
import { cn } from "@/lib/utils"

const links: { href: string; label: string }[] = [
  { href: "/", label: "Market Scan" },
  { href: "/hot-list", label: "Hot List" },
  { href: "/sector-pulse", label: "Sector Pulse" },
  { href: "/dashboard", label: "Dashboard" },
]

export function Nav() {
  const pathname = usePathname()
  const { signOut } = useClerk()

  async function handleManageBilling() {
    const res = await fetch("/api/stripe/portal", { method: "POST" })
    const data = await res.json()
    if (data.url) window.location.href = data.url
  }

  return (
    <header className="border-b border-border bg-white">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-8 px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-sm font-bold uppercase tracking-[0.15em] text-gold">
            DEJ Intelligence
          </span>
        </Link>
        <nav className="flex flex-1 gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition",
                pathname === l.href
                  ? "bg-navy text-white"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-4">
          <button
            onClick={handleManageBilling}
            className="text-xs text-muted-foreground hover:text-navy transition"
          >
            Manage subscription
          </button>
          <button
            onClick={() => signOut({ redirectUrl: "/sign-in" })}
            className="text-xs text-muted-foreground hover:text-navy transition"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}
