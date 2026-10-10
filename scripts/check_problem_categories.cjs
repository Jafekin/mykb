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
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(url + "/problems");
    await page.locator("[name=username]").fill("admin");
    const password = fs
      .readFileSync("private/admin-initial-password.txt", "utf8")
      .split("初始密码：")[1]
      .split("\n")[0];
    await page.locator("[name=password]").fill(password);
    await page.locator(".login-card button").click();
    const traditional = page.locator('[data-problem-group="traditional"]');
    await expect(traditional).toBeVisible();
    await expect(traditional.locator(".count")).toHaveText("3");
    await traditional.click();
    const children = page.getByRole("group", {
      name: "传统算法分类",
      exact: true,
    });
    await expect(children).toBeVisible();
    await expect(page.locator("#results .card")).toHaveCount(3);
    await children.locator('[data-category="滑动窗口"]').click();
    await expect(page).toHaveURL(/group=traditional/);
    await expect(page.locator("#results .card")).toHaveCount(1);
    await expect(page.locator("#results")).toContainText("传统滑动窗口");
    await page.reload();
    await expect(page.locator("#results .card")).toHaveCount(1);
    await expect(
      page.getByRole("group", { name: "传统算法分类", exact: true }),
    ).toBeVisible();
    await page.locator('[data-problem-group="other"]').click();
    await expect(page.locator("#results")).not.toContainText("传统滑动窗口");
    await page
      .locator('[data-category-group="other"][data-category="滑动窗口"]')
      .click();
    await expect(page.locator("#results .card")).toHaveCount(1);
    await expect(page.locator("#results")).toContainText("知识点滑动窗口");
    await page.locator('.side-links > [data-category=""]').click();
    await expect(page.locator("#results .card")).toHaveCount(5);
    expect(errors).toEqual([]);
    console.log(
      "PASS: traditional algorithms first-level menu, nested categories, counts, filtering, reload and same-name category isolation",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
