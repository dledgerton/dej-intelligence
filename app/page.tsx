export default function Home() {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-6 py-24">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-gold">
          DEJ Intelligence
        </p>
        <h1 className="mt-4 font-serif text-5xl leading-tight text-navy md:text-6xl">
          The intelligence layer for nonprofit executive search.
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-muted-foreground">
          Built by a search consultant, for search consultants. Spot leadership
          transitions before your competitors do, prep BD meetings in 60
          seconds, and replace the half-used Candid subscription you keep
          paying for.
        </p>
        <div className="mt-10 flex gap-4">
          <a
            href="/signup"
            className="inline-flex items-center rounded-md bg-navy px-6 py-3 font-medium text-white transition hover:bg-navy/90"
          >
            Start 14-day trial
          </a>
          <a
            href="/pricing"
            className="inline-flex items-center rounded-md border border-navy/20 px-6 py-3 font-medium text-navy transition hover:bg-navy/5"
          >
            See pricing
          </a>
        </div>
        <p className="mt-12 text-sm text-muted-foreground">
          Phase 0 scaffolding. Real product coming soon.
        </p>
      </div>
    </main>
  );
}
