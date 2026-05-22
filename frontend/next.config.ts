import type { NextConfig } from "next";

/** FastAPI upstream for dev proxy (127.0.0.1 avoids Windows localhost IPv6 issues). */
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_INTERNAL_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
