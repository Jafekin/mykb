export const problemCollections = ["专题合集", "公司合集"];

export function problemGroup(item) {
  if (item.path?.startsWith("03-手撕题/传统算法/")) return "traditional";
  return problemCollections.includes(item.category) ? "" : "other";
}

export function problemSubcategory(item) {
  return problemGroup(item) === "traditional" && item.category === "传统算法"
    ? "综合"
    : item.category;
}
