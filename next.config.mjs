/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: true,
  serverExternalPackages: ['duckdb', 'duckdb-async'],
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [...(config.externals || []), 'duckdb', 'duckdb-async']
    }
    return config
  },
};
export default nextConfig;