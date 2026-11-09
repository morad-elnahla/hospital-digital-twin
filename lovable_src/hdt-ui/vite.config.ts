// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Packaged source build for app.py. Public assets live in the project ui/ folder.
const PACKAGE = process.env.HDT_PACKAGE === "1";

export default defineConfig({
  vite: PACKAGE
    ? {
        // images may be data: (img-src allows it; app.py does not serve .jpg); fonts may not (no font-src).
        build: {
          assetsInlineLimit: (file: string) => /\.(jpe?g|png|webp)$/.test(file),
          // Stable paths: app.py serves the generated dashboard and assets without a hash manifest.
          rolldownOptions: { output: { entryFileNames: "assets/[name].js", chunkFileNames: "assets/[name].js", assetFileNames: "assets/[name][extname]" } },
        },
        experimental: {
          renderBuiltUrl(filename: string, { hostType }: { hostType: string }) {
            return hostType === "js" ? { runtime: `"/ui/" + ${JSON.stringify(filename)}` } : "/ui/" + filename;
          },
        },
      }
    : {},
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});
