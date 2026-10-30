import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Trang chứa token trong URL không được lộ token qua Referer
  async headers() {
    return ["/verify-email", "/reset-password", "/join"].map((source) => ({ source, headers: [{ key: "Referrer-Policy", value: "no-referrer" }] }));
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
