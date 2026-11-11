import Link from "next/link"

type LogoProps = {
  href?: string
  className?: string
  variant?: "light" | "dark"
}

// SectorWindow lockup: the lit-pane mark plus the wordmark (outlined SVG).
export function Logo({ href = "/", className = "h-8", variant = "light" }: LogoProps) {
  const src =
    variant === "dark"
      ? "/logo/sectorwindow-lockup-dark.svg"
      : "/logo/sectorwindow-lockup.svg"
  return (
    <Link href={href} aria-label="SectorWindow home" className="inline-flex items-center">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="SectorWindow" className={className} />
    </Link>
  )
}
