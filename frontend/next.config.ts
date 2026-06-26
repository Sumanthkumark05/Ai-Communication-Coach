import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/dashboard",
        destination: "/",
      },
      {
        source: "/jam",
        destination: "/",
      },
      {
        source: "/debate",
        destination: "/",
      },
      {
        source: "/interview",
        destination: "/",
      },
      {
        source: "/dna",
        destination: "/",
      },
      {
        source: "/coach",
        destination: "/",
      },
      {
        source: "/history",
        destination: "/",
      },
      {
        source: "/doc_analyzer",
        destination: "/",
      },
      {
        source: "/sessions",
        destination: "/",
      },
      {
        source: "/results",
        destination: "/",
      },
      {
        source: "/doc_results",
        destination: "/",
      },
      {
        source: "/doc_viva",
        destination: "/",
      },
      {
        source: "/processing",
        destination: "/",
      },
      {
        source: "/doc_processing",
        destination: "/",
      },
      {
        source: "/leaderboard",
        destination: "/",
      },
    ];
  },
};

export default nextConfig;
