const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );

const colors = new Map();
const normalize = (label) => String(label).trim().toLowerCase();

export function registerTagColors(labels) {
  for (const label of [...new Set(labels.map(normalize))].sort()) {
    if (!colors.has(label)) colors.set(label, colors.size);
  }
}

export function tagClass(label) {
  const name = normalize(label);
  registerTagColors([name]);
  return `colored-tag tag-color-${colors.get(name)}`;
}

export function categoryTag(label, key = label) {
  return `<span class="tag ${tagClass(key)}">${escapeHtml(label)}</span>`;
}

export function categoryDot(label, key = label) {
  return `<span class="category-dot ${tagClass(key)}" aria-hidden="true"></span>`;
}
