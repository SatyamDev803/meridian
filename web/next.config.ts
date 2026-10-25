import type { NextConfig } from "next";

// Static export: FastAPI serves web/out, so the demo is one process and one URL.
const config: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
