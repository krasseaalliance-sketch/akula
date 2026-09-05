import type { NextConfig } from "next";

const appBasePath = process.env.APP_BASE_PATH ?? "/scout";
const appProduct = process.env.APP_PRODUCT ?? "scout";

const nextConfig: NextConfig = {
  output: "standalone",
  basePath: appBasePath,
  env: {
    NEXT_PUBLIC_APP_BASE_PATH: appBasePath,
    NEXT_PUBLIC_APP_PRODUCT: appProduct,
    NEXT_PUBLIC_SCOUT_BASE_PATH: appBasePath,
  },
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
};
export default nextConfig;
