function categoryInfo(category) {
  const name = String(category).trim();
  const groups = [
    ["cv", /计算机视觉|^CV$|cs\.CV/i],
    ["nlp", /自然语言处理|^NLP$|cs\.CL/i],
    ["stat", /统计|^STAT$|stat\.ML/i],
    ["ml", /机器学习|^ML$|cs\.LG/i],
    ["ma", /多智能体|^MA$|cs\.MA/i],
    ["ir", /信息检索|^IR$|cs\.IR/i],
    ["ai", /智能体|人工智能|^AI$|cs\.AI/i],
  ];
  const color =
    groups.find(([, pattern]) => pattern.test(name))?.[0] || "other";
  return { color, label: color === "other" ? "ARXIV" : color.toUpperCase() };
}

export function paperCategoryDot(category) {
  const { color } = categoryInfo(category);
  return `<span class="paper-category-dot paper-category-${color}" aria-hidden="true"></span>`;
}

export function paperCategoryBadge(category) {
  const { color, label } = categoryInfo(category);
  const name = String(category).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
  return `<span class="tag paper-category-badge paper-category-${color}" title="${name}" aria-label="${name}">${label}</span>`;
}
