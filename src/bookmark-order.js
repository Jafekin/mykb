export function sortBookmarks(local, external, saved) {
  const legacyOrder = new Map(Object.keys(saved).map((id, i) => [id, i]));
  const timestamp = (value) =>
    typeof value === "string" ? Date.parse(value) || 0 : 0;
  return [
    ...local.map((item) => ({ type: "local", item })),
    ...external.map((item) => ({ type: "external", item })),
  ].sort((a, b) => {
    const time = (entry) =>
      timestamp(
        entry.type === "local"
          ? entry.item.personal
            ? entry.item.createdAt
            : saved[entry.item.id]
          : entry.item.addedAt,
      );
    const delta = time(b) - time(a);
    if (delta) return delta;
    if (a.type === "local" && b.type === "local")
      return legacyOrder.get(b.item.id) - legacyOrder.get(a.item.id);
    return 0;
  });
}
