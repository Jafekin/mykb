import "./external-bookmarks.css";

export function safeLink(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : "";
  } catch {
    return "";
  }
}
export function safeImage(value) {
  const link = safeLink(value);
  if (!link) return "";
  const url = new URL(link);
  if (url.hostname === "hdslb.com" || url.hostname.endsWith(".hdslb.com"))
    url.protocol = "https:";
  return url.href;
}
export function openExternalBookmarkForm(onAdd) {
  const dialog = document.createElement("dialog");
  dialog.className = "external-bookmark-dialog";
  dialog.innerHTML = `<form id="external-bookmark-form"><div class="external-bookmark-heading"><div><p class="eyebrow">WEB BOOKMARK</p><h2>添加网络文章</h2></div><button type="button" class="outline-button" id="cancel-bookmark">取消</button></div><label>文章网址<input name="url" type="url" inputmode="url" placeholder="粘贴文章链接，自动读取预览" required maxlength="2048" autocomplete="url"></label><p class="external-bookmark-status" role="status">只需填写链接，以下内容会自动生成，也可以修改。</p><label>标题<input name="title" placeholder="自动读取文章标题" maxlength="180"></label><label>简介<textarea name="description" placeholder="自动读取文章简介" rows="3" maxlength="500"></textarea></label><label>标签（可选）<input name="tags" maxlength="650" placeholder="例如：大模型、待读、工程实践"></label><p class="external-bookmark-status">用逗号或顿号分隔，最多 20 个标签，每个不超过 30 字。</p><label>封面网址（可选）<input name="image" type="url" placeholder="没有封面时留空，清空即可移除照片" maxlength="2048"></label><img class="external-bookmark-cover" alt="封面预览" hidden referrerpolicy="no-referrer"><p class="external-bookmark-error" role="alert" hidden></p><div class="external-bookmark-footer"><button type="submit" class="primary-button">添加收藏</button></div></form>`;
  document.body.append(dialog);
  const form = dialog.querySelector("form"),
    fields = Object.fromEntries(
      ["url", "title", "description", "image", "tags"].map((name) => [
        name,
        form.elements.namedItem(name),
      ]),
    ),
    status = dialog.querySelector('[role="status"]'),
    error = dialog.querySelector('[role="alert"]'),
    cover = dialog.querySelector("img"),
    save = form.querySelector('[type="submit"]');
  let controller,
    timer,
    pending,
    requested = "",
    generation = 0,
    dirty = new Set(),
    favicon = "";
  const updateCover = () => {
    const url = safeImage(fields.image.value);
    cover.hidden = !url;
    if (url) cover.src = url;
    else cover.removeAttribute("src");
  };
  cover.onerror = () => {
    cover.hidden = true;
  };
  for (const name of ["title", "description", "image"])
    fields[name].addEventListener("input", () => {
      dirty.add(name);
      if (name === "image") updateCover();
    });
  function preview() {
    const url = safeLink(fields.url.value.trim());
    if (!url) return Promise.resolve();
    if (requested === url) return pending || Promise.resolve();
    requested = url;
    controller?.abort();
    controller = new AbortController();
    const current = ++generation;
    status.textContent = "正在读取文章预览…";
    error.hidden = true;
    pending = (async () => {
      try {
        const response = await fetch("/api/links/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
          signal: controller.signal,
        });
        const result = await response.json();
        if (current !== generation) return;
        if (!response.ok) throw Error(result.message || "无法读取网站");
        for (const name of ["title", "description", "image"])
          if (!dirty.has(name)) fields[name].value = result[name] || "";
        favicon = safeLink(result.favicon);
        updateCover();
        status.textContent = "预览已读取，可修改后收藏。";
      } catch (err) {
        if (current !== generation || err.name === "AbortError") return;
        status.textContent =
          (err.message || "读取网站失败") + "。可以直接收藏，或手动补充内容。";
      }
    })();
    return pending;
  }
  fields.url.addEventListener("input", () => {
    clearTimeout(timer);
    controller?.abort();
    generation++;
    requested = "";
    pending = null;
    favicon = "";
    dirty.clear();
    for (const name of ["title", "description", "image"])
      fields[name].value = "";
    updateCover();
    status.textContent = "只需填写链接，以下内容会自动生成，也可以修改。";
    timer = setTimeout(preview, 650);
  });
  fields.url.addEventListener("blur", () => {
    clearTimeout(timer);
    preview();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const url = safeLink(fields.url.value.trim());
    if (!url) {
      error.textContent = "请输入有效的 http 或 https 网址";
      error.hidden = false;
      return;
    }
    const tags = [
      ...new Set(
        fields.tags.value
          .split(/[,，、\n]+/)
          .map((tag) => tag.trim())
          .filter(Boolean),
      ),
    ];
    if (tags.length > 20 || tags.some((tag) => tag.length > 30)) {
      error.textContent = "最多 20 个标签，每个不超过 30 字。";
      error.hidden = false;
      return;
    }
    save.disabled = true;
    save.textContent = "正在添加…";
    fields.url.readOnly = true;
    try {
      clearTimeout(timer);
      await preview();
      if (!dialog.open) return;
      const added = await onAdd({
        url,
        title: fields.title.value.trim() || new URL(url).hostname,
        description: fields.description.value.trim(),
        image: safeImage(fields.image.value.trim()),
        favicon,
        tags,
      });
      if (added === false)
        throw Error("这条网址已经收藏，或浏览器未能保存，请检查后重试。");
      dialog.close();
    } catch (err) {
      error.textContent = err.message || "添加失败，请重试";
      error.hidden = false;
    } finally {
      save.disabled = false;
      save.textContent = "添加收藏";
      fields.url.readOnly = false;
    }
  });
  dialog.querySelector("#cancel-bookmark").onclick = () => dialog.close();
  dialog.addEventListener(
    "close",
    () => {
      clearTimeout(timer);
      generation++;
      controller?.abort();
      dialog.remove();
    },
    { once: true },
  );
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.showModal();
  fields.url.focus();
}
