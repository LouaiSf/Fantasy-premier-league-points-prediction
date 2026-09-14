import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Without this, opening the dev server via the raw loopback IP (rather
  // than "localhost") gets its HMR socket silently blocked, which aborts
  // the client bundle before React ever hydrates -- the page looks alive
  // but every effect (data fetch included) never runs.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "resources.premierleague.com",
      },
    ],
  },
};

export default nextConfig;
