import type { NextConfig } from "next";

// The browser talks only to this Next.js server; /api requests are proxied
// server-side to the FastAPI backend. This keeps the app working when the
// frontend is accessed through a forwarded/remote URL (GitHub Codespaces,
// etc.) where the browser cannot reach the backend's port directly.
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  // Let the dev server accept requests arriving through GitHub Codespaces'
  // forwarded URLs (fixes hot-reload/asset 403s when used remotely).
  allowedDevOrigins: ["*.app.github.dev"],
  experimental: {
    // The proxy buffers request bodies (10MB default), which would truncate
    // audio uploads. The backend enforces its own 50MB limit, so stay above it.
    proxyClientMaxBodySize: "60mb",
    // Transcribing a full song takes well over the 30s default before the
    // synchronous /transcribe request returns.
    proxyTimeout: 600_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
