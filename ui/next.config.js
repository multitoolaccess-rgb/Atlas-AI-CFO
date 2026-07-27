/** @type {import('next').NextConfig} */
const nextConfig = {
  // ESLint runs separately via `next lint` in CI (scripts/check-build.sh).
  // Ignoring during build prevents custom rules from blocking production
  // builds while still catching violations in the lint step.
  eslint: {
    ignoreDuringBuilds: true,
  },
}

module.exports = nextConfig
