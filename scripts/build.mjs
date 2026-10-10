import { gzipSync } from "node:zlib";
import { build } from "esbuild";
import {
  cp,
  mkdir,
  readFile,
  writeFile,
  access,
  readdir,
} from "node:fs/promises";
await mkdir("dist/assets", { recursive: true });
await build({
  entryPoints: ["src/app.js"],
  bundle: true,
  minify: true,
  format: "esm",
  outdir: "dist/assets",
  splitting: true,
  chunkNames: "[name]-[hash]",
  plugins: [
    {
      name: "editor-resize-lifecycle",
      setup(builder) {
        builder.onLoad(
          { filter: /@toast-ui\/editor\/dist\/esm\/index\.js$/ },
          async ({ path }) => {
            const contents = await readFile(path, "utf8");
            // Toast UI 3.2.2 leaves a trailing toolbar resize callback queued after
            // destroy. Avoid rendering into a detached toolbar after closing/saving.
            const target = "this.handleResize = throttle_1(function () {";
            if (!contents.includes(target))
              throw Error(
                "Review Toast UI resize lifecycle patch after upgrading the editor",
              );
            return {
              contents: contents.replace(
                target,
                target +
                  "\n            if (!_this.refs.el || !_this.refs.el.isConnected) return;",
              ),
              loader: "js",
            };
          },
        );
      },
    },
  ],
});
for (const name of ["index.html", "style.css", "favicon.svg", "logo.svg"])
  await cp(`src/${name}`, `dist/${name}`);
await cp("src/logo-warm.svg", "dist/assets/logo-warm.svg");
try {
  await access("src/jkb-logo-v2.png");
  await cp("src/jkb-logo-v2.png", "dist/jkb-logo-v2.png");
} catch {}
const html = await readFile("dist/index.html", "utf8");
// Use the same local config and environment overrides as the API so the
// initial document already has the configured name before JavaScript loads.
let localConfig = {};
try {
  localConfig = JSON.parse(await readFile("config.local.json", "utf8"));
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
const siteName = String(
  process.env.MYKB_SITE_NAME ?? localConfig.site_name ?? "MyKB",
);
const escapedSiteName = siteName.replace(
  /[&<>"']/g,
  (character) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
      character
    ],
);
await writeFile(
  "dist/index.html",
  html
    .replaceAll("MyKB", () => escapedSiteName)
    .replace(
      "</head>",
      '<link rel="stylesheet" href="/assets/app.css"></head>',
    ),
);
await cp("node_modules/katex/dist/katex.min.css", "dist/assets/katex.min.css");
await cp("node_modules/katex/dist/fonts", "dist/assets/fonts", {
  recursive: true,
});
async function compressText(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = `${directory}/${entry.name}`;
    if (entry.isDirectory()) await compressText(path);
    else if (/\.(js|css|html)$/.test(entry.name))
      await writeFile(path + ".gz", gzipSync(await readFile(path)));
  }
}
await compressText("dist/assets");
for (const path of ["dist/index.html", "dist/style.css"])
  await writeFile(path + ".gz", gzipSync(await readFile(path)));
console.log("Built portable site in dist/");
