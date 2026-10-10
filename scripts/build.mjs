import { build } from "esbuild";
import { cp, mkdir, readFile, writeFile, access } from "node:fs/promises";
await mkdir("dist/assets", { recursive: true });
await build({
  entryPoints: ["src/app.js"],
  bundle: true,
  minify: true,
  format: "esm",
  outfile: "dist/assets/app.js",
});
for (const name of ["index.html", "style.css", "favicon.svg", "logo.svg"])
  await cp(`src/${name}`, `dist/${name}`);
try {
  await access("src/jkb-logo-v2.png");
  await cp("src/jkb-logo-v2.png", "dist/jkb-logo-v2.png");
} catch {}
const html = await readFile("dist/index.html", "utf8");
await writeFile(
  "dist/index.html",
  html.replace(
    "</head>",
    '<link rel="stylesheet" href="/assets/app.css"></head>',
  ),
);
await cp("node_modules/katex/dist/katex.min.css", "dist/assets/katex.min.css");
await cp("node_modules/katex/dist/fonts", "dist/assets/fonts", {
  recursive: true,
});
console.log("Built portable site in dist/");
