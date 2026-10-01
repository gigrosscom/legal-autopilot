import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // the build's id, baked into the pages and served by /version.json: an open tab finds out it runs an old build
  env: { NEXT_PUBLIC_BUILD_ID: process.env.BUILD_ID_OVERRIDE || String(Date.now()) },
};

export default config;
