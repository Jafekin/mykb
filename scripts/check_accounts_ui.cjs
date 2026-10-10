const { chromium, expect } = require("@playwright/test");
const fs = require("fs");
const url = process.env.SITE_URL || "http://127.0.0.1:4173";
(async () => {
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
    headless: true,
    args: ["--no-sandbox"],
  });
  const adminContext = await browser.newContext(),
    page = await adminContext.newPage(),
    errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const password = fs
    .readFileSync("private/admin-initial-password.txt", "utf8")
    .split("初始密码：")[1]
    .split("\n")[0];
  async function login(page, name, password) {
    await page.goto(url + "/saved");
    await page.locator("[name=username]").fill(name);
    await page.locator("[name=password]").fill(password);
    await page.locator(".login-card button").click();
    await expect(page.locator("#account-button")).toBeVisible();
  }
  await page.goto(url + "/notes");
  await expect(page.locator(".login-card")).toBeVisible();
  await expect(page.locator("#nav a")).toHaveCount(0);
  await login(page, "admin", password);
  const editableIndex = await (
    await adminContext.request.get(url + "/data/index.json")
  ).json();
  const editable = editableIndex.items.find(
    (item) => item.section === "notes" && !item.isIndex,
  );
  await page.goto(url + "/notes?id=" + editable.id);
  expect(
    await page.evaluate(() =>
      performance
        .getEntriesByType("resource")
        .some((entry) => entry.name.includes("editor-runtime-")),
    ),
  ).toBe(false);
  const compressedIndex = await adminContext.request.get(
    url + "/data/index.json",
    { headers: { "Accept-Encoding": "gzip" } },
  );
  expect(compressedIndex.headers()["content-encoding"]).toBe("gzip");
  const asset = await adminContext.request.get(url + "/assets/app.js", {
    headers: { "Accept-Encoding": "gzip" },
  });
  expect(asset.headers()["content-encoding"]).toBe("gzip");
  const cachedAsset = await adminContext.request.get(url + "/assets/app.js", {
    headers: {
      "Accept-Encoding": "gzip",
      "If-None-Match": asset.headers().etag,
    },
  });
  expect(cachedAsset.status()).toBe(304);
  await page.locator("#edit-markdown").click();
  const richText = page.locator(
    '.toastui-editor-ww-container [contenteditable="true"]',
  );
  await expect(richText).toBeVisible();
  await richText.click();
  await page.keyboard.press("Control+End");
  await page.keyboard.press("Enter");
  await page.keyboard.insertText("编辑保存回归验证");
  await page.route("**/api/articles/" + editable.id, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 500,
      json: { message: "知识库磁盘只读" },
    });
  });
  await page.locator("#save-markdown").click();
  await expect(page.locator("#markdown-status")).toHaveText(
    "保存失败：知识库磁盘只读",
  );
  await expect(page.locator("#toast")).toHaveText("保存失败：知识库磁盘只读");
  await expect(richText).toContainText("编辑保存回归验证");
  await expect(page.locator("#save-markdown")).toBeEnabled();
  await page.unroute("**/api/articles/" + editable.id);
  const saveResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/articles/" + editable.id) &&
      response.request().method() === "POST",
  );
  await page.locator("#save-markdown").click();
  expect((await saveResponse).status()).toBe(200);
  await expect(page.locator("#article-body")).toContainText("编辑保存回归验证");
  const source = await (
    await adminContext.request.get(url + "/api/articles/" + editable.id)
  ).json();
  expect(source.body).toContain("编辑保存回归验证");
  await page.locator("#account-button").click();
  await page.locator("#manage-users").click();
  await expect(page.locator(".users-dialog")).toBeVisible();
  const name = "ui_" + Date.now().toString(36),
    pw = "TemporaryPassword-" + Date.now();
  let id;
  try {
    await page.locator("#add-user").click();
    const form = page.locator("#user-settings form");
    await form.locator("[name=username]").fill(name);
    await form.locator("[name=password]").fill(pw);
    await form.locator("[name=allVisible]").uncheck();
    await form
      .locator("[name=visible]")
      .evaluateAll((inputs) =>
        inputs.forEach((input) => (input.checked = false)),
      );
    const category = form.locator('[name=visible][value^="notes::"]').first();
    await category.check();
    const key = await category.getAttribute("value");
    await form.locator("[type=submit]").click();
    await expect(page.locator(".user-list")).toContainText(name);
    const info = await (
      await adminContext.request.get(url + "/api/admin/users")
    ).json();
    id = info.users.find((user) => user.username === name).id;
    await page.locator("[data-close]").click();
    const userContext = await browser.newContext(),
      userPage = await userContext.newPage();
    userPage.on("pageerror", (error) => errors.push(error.message));
    await login(userPage, name, pw);
    await expect(userPage.locator("#rebuild-index")).toBeHidden();
    await userPage.locator("#account-button").click();
    await expect(userPage.locator("#manage-users")).toHaveCount(0);
    await userPage.locator("#account-button").click();
    const index = await (
      await userContext.request.get(url + "/data/index.json")
    ).json();
    const item = index.items.find((item) => !item.isIndex);
    await userPage.goto(url + "/notes?id=" + item.id);
    await expect(userPage.locator(".article-title")).toBeVisible();
    await expect(userPage.locator("#edit-markdown")).toHaveCount(0);
    await expect(userPage.locator("#delete-document")).toHaveCount(0);
    await userPage.locator("[data-save]").click();
    await expect(userPage.locator("[data-save]")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userPage.goto(url + "/saved");
    await userPage.route("**/api/links/preview", (route) =>
      route.fulfill({
        json: {
          title: "测试外链",
          description: "私有收藏测试",
          image: "",
          favicon: "",
        },
      }),
    );
    await userPage.locator("#add-external-bookmark").click();
    await userPage
      .locator("[name=url]")
      .fill("https://example.com/private-bookmark");
    await userPage.locator("[type=submit]").click();
    await expect(userPage.getByText("测试外链", { exact: true })).toBeVisible();
    const second = await browser.newContext(),
      secondPage = await second.newPage();
    await login(secondPage, name, pw);
    await expect(
      secondPage.getByText("测试外链", { exact: true }),
    ).toBeVisible();
    await expect(
      secondPage.getByText(item.title, { exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(page.getByText("测试外链", { exact: true })).toHaveCount(0);
    await userPage.locator("#account-button").click();
    await userPage.locator("#logout").click();
    await expect(userPage.locator(".login-card")).toBeVisible();
    await page.locator("#account-button").click();
    await page.locator("#manage-users").click();
    await page.locator(`[data-user="${id}"]`).click();
    page.once("dialog", (dialog) => dialog.accept());
    await page.locator("#remove-user").click();
    await expect(page.locator(".user-list")).not.toContainText(name);
    id = null;
    if (errors.length) throw Error(errors.join("\n"));
    console.log(
      "PASS: login UI, gear submenu, add/delete users, restricted navigation/actions, local and external bookmarks across browsers, private favorites and logout",
    );
  } finally {
    if (id)
      await adminContext.request.post(url + "/api/admin/users", {
        data: { action: "delete", id },
      });
    await browser.close();
  }
})();
