/**
 * Auto-generated. DO NOT edit by hand.
 *
 * After running migrations, regenerate with:
 *   npm run db:types
 *
 * For Phase 0 we leave this as a permissive type so the app compiles
 * before Supabase is provisioned.
 */
export type Database = {
  public: {
    Tables: Record<string, { Row: Record<string, unknown> }>;
    Views: Record<string, { Row: Record<string, unknown> }>;
    Functions: Record<string, unknown>;
    Enums: Record<string, unknown>;
    CompositeTypes: Record<string, unknown>;
  };
};
