import { existsSync, readdirSync, rmSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "frontend", "src", "app.jsx");
const outdir = join(root, "frontend");
const chunksDir = join(outdir, "chunks");
const require = createRequire(import.meta.url);

if (!existsSync(src)) {
  console.error("缺少 frontend/src/app.jsx，请先运行 node scripts/split_frontend.mjs");
  process.exit(1);
}

// 清理旧 chunk，避免浏览器/懒加载仍引用过期 hash 文件
if (existsSync(chunksDir)) {
  for (const name of readdirSync(chunksDir)) {
    if (name.endsWith(".js")) {
      rmSync(join(chunksDir, name), { force: true });
    }
  }
}

let esbuild;
try {
  esbuild = require("esbuild");
} catch {
  console.error("请先运行: npm install");
  process.exit(1);
}

const result = await esbuild.build({
  entryPoints: [src],
  outdir,
  bundle: true,
  splitting: true,
  format: "esm",
  platform: "browser",
  jsx: "transform",
  jsxFactory: "React.createElement",
  jsxFragment: "React.Fragment",
  entryNames: "[name]",
  chunkNames: "chunks/[name]-[hash]",
  logLevel: "warning",
  metafile: true,
});

const outputs = Object.values(result.metafile?.outputs || {});
const totalKb = Math.round(outputs.reduce((sum, o) => sum + o.bytes, 0) / 1024);
const chunkCount = outputs.filter((o) => o.entryPoint == null).length;
console.log(`前端编译完成 -> frontend/app.js + ${chunkCount} 个 chunk（合计约 ${totalKb} KB）`);
