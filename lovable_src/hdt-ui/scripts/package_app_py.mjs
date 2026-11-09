#!/usr/bin/env node
/** Build and package the Lovable source for app.py without Bash, Bun, or rsync. */
import { spawnSync } from "node:child_process";
import { cp, mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.resolve(process.argv[2] ?? path.join(root, "..", "..", "ui"));
if (out === root || out === path.parse(out).root) throw new Error(`Refusing unsafe output directory: ${out}`);
const stage = path.join(path.dirname(out), `.ui-stage-${process.pid}`);
const backup = path.join(path.dirname(out), `.ui-backup-${process.pid}`);
const env = { ...process.env, HDT_PACKAGE: "1", VITE_HASH_ROUTER: "1", VITE_HDT_DIRECT: "1" };
const run = (exe, args, options = {}) => {
  const r = spawnSync(exe, args, { cwd: root, env, encoding: "utf8", stdio: "inherit", ...options });
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error(`${path.basename(exe)} ${args.join(" ")} exited ${r.status}`);
  return r;
};

try {
  await rm(stage, { recursive: true, force: true });
  await rm(backup, { recursive: true, force: true });
  run(process.execPath, [path.join(root, "node_modules", "vite", "bin", "vite.js"), "build"]);
  const rendered = run(process.execPath, [path.join(root, "scripts", "package-ssr.mjs"), path.join(root, ".output")], { stdio: ["ignore", "pipe", "inherit"] }).stdout;
  await mkdir(path.join(stage, "assets"), { recursive: true });
  await cp(path.join(root, ".output", "public", "assets"), path.join(stage, "assets"), { recursive: true });
  await cp(path.join(root, "public", "favicon.ico"), path.join(stage, "favicon.ico"));
  let html = rendered.replaceAll('"/assets/', '"/ui/assets/');
  let inlineIndex = 0;
  html = html.replace(/<script([^>]*)>([\s\S]*?)<\/script>/g, (whole, attrs, body) => {
    if (/\bsrc\s*=/.test(attrs) || !body.trim()) return whole;
    const name = `inline-${inlineIndex++}.js`;
    writeFile(path.join(stage, name), body, "utf8");
    return `<script${attrs} src="/ui/${name}"></script>`;
  });
  html = html.replaceAll('href="/favicon.ico"', 'href="/ui/favicon.ico"');
  await writeFile(path.join(stage, "dashboard.html"), html, "utf8");

  const cssFiles = [];
  const walk = async (dir) => { for (const ent of await (await import("node:fs/promises")).readdir(dir, { withFileTypes: true })) { const p = path.join(dir, ent.name); if (ent.isDirectory()) await walk(p); else if (ent.name.endsWith(".css")) cssFiles.push(await readFile(p, "utf8")); } };
  await walk(path.join(stage, "assets"));
  if (cssFiles.some((css) => /url\(\s*data:font/i.test(css))) throw new Error("Packaged CSS contains an inlined font forbidden by app.py CSP");
  if (/\b(?:src|href)="\/assets\//.test(html)) throw new Error("Packaged HTML has an asset URL outside /ui/");
  if (!html.includes("/ui/assets/")) throw new Error("Packaged HTML does not reference the staged asset folder");

  await mkdir(path.dirname(out), { recursive: true });
  let hadOut = false;
  try { await rename(out, backup); hadOut = true; } catch (e) { if (e.code !== "ENOENT") throw e; }
  try { await rename(stage, out); }
  catch (e) { if (hadOut) await rename(backup, out); throw e; }
  if (hadOut) await rm(backup, { recursive: true, force: true });
  console.log(`Packaged UI to ${out} using Node ${process.versions.node}`);
} catch (e) {
  await rm(stage, { recursive: true, force: true });
  throw e;
}
