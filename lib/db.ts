// lib/db.ts
// Returns the correct DuckDB connection string based on environment.
// Development: local DuckDB file
// Production: MotherDuck cloud database

export function getDbPath(): string {
    const token = process.env.MOTHERDUCK_TOKEN
    if (token) {
      return `md:dej_intelligence?motherduck_token=${token}`
    }
    const local = process.env.DEJ_DB_PATH
    if (!local) throw new Error('DEJ_DB_PATH or MOTHERDUCK_TOKEN must be set')
    return local
  }
  