export function sortOptions(section) {
  return [
    ["modified-desc", "修改时间：最新优先"],
    ["modified-asc", "修改时间：最早优先"],
    ["created-desc", "创建时间：最新优先"],
    ["created-asc", "创建时间：最早优先"],
    ["title-asc", "标题：升序"],
    ["title-desc", "标题：降序"],
    ["difficulty-asc", "难度：从低到高"],
    ["difficulty-desc", "难度：从高到低"],
    ...(section === "saved"
      ? [
          ["saved-desc", "收藏时间：最新优先"],
          ["saved-asc", "收藏时间：最早优先"],
        ]
      : []),
  ];
}

export function sortEntries(entries, order, saved = {}) {
  if (!sortOptions("saved").some(([value]) => value === order)) return entries;
  const [field, direction] = order.split("-");
  const sign = direction === "asc" ? 1 : -1;
  const value = ({ item, type }) => {
    if (field === "title") return item.title || "";
    if (field === "difficulty")
      return { EASY: 1, MEDIUM: 2, HARD: 3 }[item.difficulty] ?? null;
    const time =
      field === "saved"
        ? type === "external"
          ? item.addedAt
          : item.personal
            ? item.createdAt
            : saved[item.id]
        : type === "external"
          ? item.addedAt
          : field === "created"
            ? item.createdAt
            : item.modifiedAt;
    const parsed = typeof time === "string" ? Date.parse(time) : NaN;
    return Number.isFinite(parsed) ? parsed : null;
  };
  return [...entries].sort((a, b) => {
    const av = value(a),
      bv = value(b);
    // Unknown dates/difficulties stay at the end in either direction.
    if (av === null || bv === null) return av === bv ? 0 : av === null ? 1 : -1;
    if (field === "title")
      return sign * av.localeCompare(bv, "zh-CN", { numeric: true });
    return sign * (av - bv);
  });
}
