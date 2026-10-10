import { paperCategoryBadge } from "./paper-category.js";

const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[char],
  );

export function paperHeader(item, source) {
  const lines = source.split(/\r?\n/);
  const firstSection = lines.findIndex((line) => /^##\s/.test(line));
  const end = firstSection < 0 ? lines.length : firstSection;
  const intro = lines.slice(0, end);
  const englishAt = intro.findIndex((line) => /^>\s+/.test(line));
  const english =
    englishAt < 0 ? "" : intro[englishAt].replace(/^>\s+/, "").trim();
  const fields = {};
  const removed = new Set();
  intro.forEach((line, i) => {
    const match = line.match(
      /^\s*(?:-\s+)?\*\*(发布日期|作者|论文分类|分类)\*\*\s*[：:]\s*(.+)$/,
    );
    if (match) {
      fields[match[1]] = match[2].trim();
      removed.add(i);
    }
  });
  if (englishAt >= 0) removed.add(englishAt);
  const arxiv = source.match(
    /https:\/\/arxiv\.org\/abs\/(\d{4}\.\d{4,5}(?:v\d+)?)/i,
  )?.[1];
  const category = fields["论文分类"] || fields["分类"];
  const date = (fields["发布日期"] || "").match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  const authors = fields["作者"];
  const parts = [];
  if (category) parts.push(paperCategoryBadge(category));
  if (date)
    parts.push(`<time datetime="${date}">${date.replaceAll("-", "/")}</time>`);
  if (arxiv)
    parts.push(
      `<a href="https://arxiv.org/abs/${arxiv}" target="_blank" rel="noopener noreferrer">arXiv:${arxiv}</a><button class="paper-copy-id" type="button" data-arxiv="${arxiv}" aria-label="复制 arXiv 编号" title="复制 arXiv 编号">⧉</button>`,
    );
  if (authors)
    parts.push(`<span class="paper-authors">${escapeHtml(authors)}</span>`);
  return {
    html: `<div class="paper-heading"><h1 class="article-title paper-title">${escapeHtml(english || item.title)}</h1>${english && english !== item.title ? `<p class="paper-subtitle">${escapeHtml(item.title)}</p>` : ""}${parts.length ? `<div class="paper-meta">${parts.join("")}</div>` : ""}</div>`,
    body: lines
      .filter((_, i) => !removed.has(i))
      .join("\n")
      .trimStart(),
  };
}
