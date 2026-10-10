const { chromium, expect } = require("@playwright/test");
const fs = require("fs");
const url = process.env.SITE_URL;
(async () => {
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
    args: ["--no-sandbox"],
  });
  try {
    const context = await browser.newContext();
    const password = fs
      .readFileSync("private/admin-initial-password.txt", "utf8")
      .split("初始密码：")[1]
      .split("\n")[0];
    await context.request.post(url + "/api/auth/login", {
      data: { username: "admin", password },
    });
    const page = await context.newPage();
    const fullRequests = [];
    page.on("request", (request) => {
      const address = new URL(request.url());
      if (address.pathname === "/data/index.json" && !address.search)
        fullRequests.push(request.url());
    });
    await page.goto(url + "/notes");
    await expect(page.locator("#results .card")).toHaveCount(1);
    expect(fullRequests).toHaveLength(0);
    const summary = await (
      await context.request.get(url + "/data/index.json?view=summary")
    ).json();
    expect(summary.items.every((item) => !Object.hasOwn(item, "search"))).toBe(
      true,
    );
    expect(
      summary.items.find((item) => item.section === "notes").excerpt,
    ).not.toContain("仅正文搜索标记XYZ");
    await page.locator("#search").fill("仅正文搜索标记XYZ");
    await expect(page.locator("#result-count")).toHaveText("1 篇内容");
    await expect.poll(() => fullRequests.length).toBe(1);
    await expect(page.locator("#results .card")).toHaveCount(1);
    await page.locator("#search").fill("不存在的关键词ABC");
    await expect(page.locator("#results .card")).toHaveCount(0);
    expect(fullRequests).toHaveLength(1);
    await page.goto(
      url + "/notes?q=" + encodeURIComponent("仅正文搜索标记XYZ"),
    );
    await expect(page.locator("#results .card")).toHaveCount(1);
    console.log(
      "PASS: compact initial index, lazy full-text search, query cache reuse and search URL reload",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
