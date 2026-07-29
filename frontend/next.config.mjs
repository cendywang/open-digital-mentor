import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadPublicEnv } from "./scripts/public-env.mjs";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));
loadPublicEnv(path.resolve(projectRoot, "../.env"));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep `next dev` from sharing artifacts with `next build` / `next start`.
  // A production verification must not invalidate a running dev session.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  outputFileTracingRoot: projectRoot,
  turbopack: { root: projectRoot },
  // Next 16 blocks dev runtime/HMR requests whose Host differs from its
  // selected canonical host. Both loopback spellings are documented and are
  // also present in the backend CORS allowlist, so keep either URL usable.
  allowedDevOrigins: ["localhost", "127.0.0.1"],
  reactStrictMode: true,
  // The VRM is a reviewed static asset; the app has no runtime download route.
};
export default nextConfig;
