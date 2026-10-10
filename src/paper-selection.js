// Seven calendar days including today, using the site's Beijing timezone.
export function isRecentPaper(item, now = new Date()) {
  if (item.section !== "papers") return false;
  const date = (item.date || "").match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  if (!date) return false;
  const published = Date.parse(date + "T00:00:00Z");
  if (
    !Number.isFinite(published) ||
    new Date(published).toISOString().slice(0, 10) !== date
  )
    return false;
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .formatToParts(now)
      .map(({ type, value }) => [type, value]),
  );
  const today = Date.parse(
    `${parts.year}-${parts.month}-${parts.day}T00:00:00Z`,
  );
  return published <= today && published >= today - 6 * 86400000;
}
