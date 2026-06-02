/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static HTML export for hosting on Render Static Site (no Node server).
  output: "export",
  images: {
    // Next.js image optimization needs a server, which a static export doesn't
    // have — serve images as-is.
    unoptimized: true,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.supabase.co",
        pathname: "/storage/v1/object/public/**",
      },
    ],
  },
};

export default nextConfig;
