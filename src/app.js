import { marked } from "marked";
import DOMPurify from "dompurify";
import katex from "katex";
import hljs from "highlight.js/lib/common";
import "./code-highlight.css";
import { mountDraftHighlight } from "./draft-highlight.js";
import {
  mountRichEditor,
  destroyRichEditor,
  hasUnsavedRichChanges,
} from "./rich-editor.js";
import { openNewDocument } from "./new-document.js";
import { openExternalBookmarkForm, safeLink } from "./external-bookmarks.js";
import "./saved-links.css";
import { requireSession, mountAccountMenu, api } from "./account-ui.js";
const { siteName, siteLogo } = await api("/api/config");
const brand = document.querySelector(".brand");
brand.lastChild.textContent = siteName;
brand.querySelector("img").src = siteLogo;
document.title = siteName;
const { user: currentUser, state: accountState } = await requireSession();
const can = (action) =>
  currentUser.admin || currentUser.permissions[action] === true;
const $ = (s, p = document) => p.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
function modifiedTime(item) {
  const date = new Date(item.modifiedAt);
  if (Number.isNaN(date.getTime())) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .map((x) => [x.type, x.value]),
  );
  return `<time class="modified-time" datetime="${esc(item.modifiedAt)}" title="北京时间">修改于 ${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}</time>`;
}
const labels = {
  notes: "Note",
  interview: "面试题",
  problems: "手撕题",
  learning: "学习路径",
  papers: "最新论文",
  saved: "我的收藏",
};
const subtitles = {
  interview: "从原理到实践，系统准备大模型技术面试。",
  problems: "理解每一行代码，从基础算子到完整模型。",
  learning: "沿着清晰的路线，把知识变成自己的能力。",
  papers: "阅读归档论文，跟进研究思路与方法。",
  notes: "整理个人技术笔记、论文阅读与系统实践。",
  saved: "把值得回看的内容，留在自己的学习清单里。",
};
const english = {
  interview: "INTERVIEW COLLECTION",
  problems: "LEARN BY CODING",
  learning: "LEARNING PATHS",
  papers: "RESEARCH LIBRARY",
  notes: "JAFEKIN NOTES",
  saved: "YOUR COLLECTION",
};
let pendingWrites = Promise.resolve(),
  writeFailure = null;
const draftTimers = new Map();
function getStore(key, fallback) {
  if (key !== "dark") return accountState[key] ?? fallback;
  try {
    return (
      JSON.parse(localStorage.getItem("llmforge.local." + key)) ?? fallback
    );
  } catch {
    return fallback;
  }
}
function queueWrite(key, value) {
  const snapshot = JSON.parse(JSON.stringify(value));
  accountState[key] = snapshot;
  const request = pendingWrites
    .catch(() => {})
    .then(() => api("/api/state", { key, value: snapshot }));
  pendingWrites = request;
  request.then(
    () => {
      writeFailure = null;
    },
    () => {},
  );
  request.catch((error) => {
    writeFailure = error;
    toast("个人数据未保存：" + error.message);
  });
  return request;
}
function setStore(key, value) {
  if (key === "dark") {
    try {
      localStorage.setItem("llmforge.local.dark", JSON.stringify(value));
      return true;
    } catch {
      return false;
    }
  }
  if (key.startsWith("draft.")) {
    accountState[key] = value;
    clearTimeout(draftTimers.get(key));
    draftTimers.set(
      key,
      setTimeout(() => {
        draftTimers.delete(key);
        queueWrite(key, value);
      }, 450),
    );
  } else queueWrite(key, value);
  return true;
}
async function flushPersonal() {
  for (const [key, timer] of draftTimers) {
    clearTimeout(timer);
    queueWrite(key, accountState[key]);
  }
  draftTimers.clear();
  await pendingWrites;
  if (writeFailure) throw writeFailure;
}
window.addEventListener("beforeunload", () => {
  for (const [key, timer] of draftTimers) {
    clearTimeout(timer);
    fetch("/api/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value: accountState[key] }),
      keepalive: true,
    }).catch(() => {});
  }
  draftTimers.clear();
});
let progress = getStore("progress", {}),
  saved = getStore("saved", {}),
  externalBookmarks = getStore("externalBookmarks", []),
  index,
  byId;
if (getStore("dark", false)) document.body.classList.add("dark");
$("#theme").onclick = () => {
  document.body.classList.toggle("dark");
  setStore("dark", document.body.classList.contains("dark"));
};
let toastTimer;
function toast(s) {
  $("#toast").textContent = s;
  $("#toast").style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").style.display = "none"), 2200);
}
const refreshIcon =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-8-8c2.2 0 4.2.9 5.7 2.3L20 9"/><path d="M20 4v5h-5"/></svg>';
$("#theme").innerHTML =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 4a8 8 0 0 0 0 16Z" fill="currentColor"/></svg>';
const rebuildButton = document.createElement("button");
rebuildButton.id = "rebuild-index";
rebuildButton.className = "icon-button rebuild-button";
rebuildButton.innerHTML = refreshIcon;
rebuildButton.setAttribute("aria-label", "重建索引");
rebuildButton.title = "重建索引：重新扫描知识库源文件，更新列表与搜索";
const headerActions = document.createElement("div");
headerActions.className = "header-actions";
headerActions.append(rebuildButton, $("#theme"));
$(".header-inner").append(headerActions);
rebuildButton.hidden = !currentUser.admin;
mountAccountMenu(currentUser, headerActions, flushPersonal);
rebuildButton.onclick = async () => {
  rebuildButton.disabled = true;
  rebuildButton.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/api/index/rebuild", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }),
      result = await response.json();
    if (!response.ok) throw Error(result.message || "重建失败");
    const refreshed = await fetch("/data/index.json");
    if (!refreshed.ok) throw Error("索引已重建，请刷新网页加载");
    index = await refreshed.json();
    byId = Object.fromEntries(index.items.map((item) => [item.id, item]));
    if (!hasUnsavedRichChanges()) await render();
    toast(
      `索引已重建 · ${result.sections.reduce((sum, section) => sum + section.count, 0)} 篇内容${hasUnsavedRichChanges() ? "，未保存编辑已保留" : ""}`,
    );
  } catch (error) {
    toast(error.message || "重建失败");
  } finally {
    rebuildButton.disabled = false;
    rebuildButton.removeAttribute("aria-busy");
  }
};
function route() {
  const p = new URL(location.href);
  return {
    section: labels[p.pathname.slice(1)] ? p.pathname.slice(1) : "interview",
    id: p.searchParams.get("id"),
    q: p.searchParams.get("q") || "",
    category: p.searchParams.get("category") || "",
    scope: p.searchParams.get("scope") || "current",
    difficulty: p.searchParams.get("difficulty") || "",
    done: p.searchParams.get("done") === "1",
    page: Math.max(1, Number(p.searchParams.get("page")) || 1),
  };
}
function href(item) {
  return `/${item.section}?id=${item.id}`;
}
function go(url, replace = false) {
  history[replace ? "replaceState" : "pushState"]({}, "", url);
  render();
  window.scrollTo(0, 0);
}
function listingUrl(s) {
  const p = new URLSearchParams();
  for (const k of ["q", "category", "difficulty", "group"])
    if (s[k]) p.set(k, s[k]);
  if (s.scope === "all") p.set("scope", "all");
  if (s.done) p.set("done", "1");
  if (s.page > 1) p.set("page", s.page);
  return "/" + s.section + (p.size ? "?" + p : "");
}
function update(patch) {
  go(
    listingUrl({
      ...route(),
      group: new URL(location.href).searchParams.get("group") || "",
      page: 1,
      ...patch,
    }),
  );
}
function download(name, body, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}
async function toggleSaved(id) {
  const next = { ...saved };
  next[id] ? delete next[id] : (next[id] = true);
  try {
    await queueWrite("saved", next);
    saved = next;
    document.querySelectorAll(`[data-save="${id}"]`).forEach((b) => {
      b.classList.toggle("saved", !!saved[id]);
      b.classList.toggle("selected", !!saved[id]);
      b.setAttribute("aria-pressed", !!saved[id]);
      b.innerHTML = b.classList.contains("card-save")
        ? saved[id]
          ? "★"
          : "☆"
        : saved[id]
          ? "★ 已收藏"
          : "☆ 收藏";
    });
    toast(saved[id] ? "已加入收藏" : "已取消收藏");
    if (route().section === "saved" && !route().id) render();
  } catch {}
}
function mathHTML(text, displayMode) {
  try {
    return katex.renderToString(text.replace(/\\\\(?=[a-zA-Z])/g, "\\"), {
      displayMode,
      throwOnError: false,
      strict: "ignore",
      trust: false,
    });
  } catch {
    return esc(text);
  }
}
marked.use({
  extensions: [
    {
      name: "mathBlock",
      level: "block",
      start: (s) => s.indexOf("$$"),
      tokenizer(s) {
        const m = /^\$\$([\s\S]+?)\$\$(?:\n|$)/.exec(s);
        if (m) return { type: "mathBlock", raw: m[0], text: m[1] };
      },
      renderer(t) {
        return mathHTML(t.text, true);
      },
    },
    {
      name: "mathInline",
      level: "inline",
      start: (s) => s.indexOf("$"),
      tokenizer(s) {
        const m = /^\$\$([\s\S]+?)\$\$|^\$([^$\n]+?)\$/.exec(s);
        if (m)
          return {
            type: "mathInline",
            raw: m[0],
            text: m[1] || m[2],
            display: !!m[1],
          };
      },
      renderer(t) {
        return mathHTML(t.text, t.display);
      },
    },
  ],
});
marked.use({
  renderer: {
    code({ text, lang }) {
      const language = (lang || "").trim().split(/\s+/)[0].toLowerCase();
      let html = esc(text);
      if (text.length <= 100000) {
        if (language && hljs.getLanguage(language))
          html = hljs.highlight(text, { language, ignoreIllegals: true }).value;
        else if (!language)
          html = hljs.highlightAuto(text, [
            "python",
            "javascript",
            "typescript",
            "cpp",
            "java",
            "bash",
            "json",
            "sql",
          ]).value;
      }
      return `<pre><code class="hljs${language ? " language-" + esc(language) : ""}">${html}\n</code></pre>`;
    },
  },
});
function markdown(s) {
  return DOMPurify.sanitize(marked.parse(s), {
    ADD_TAGS: ["annotation", "semantics"],
    ADD_ATTR: ["encoding"],
  });
}
function nav(section) {
  $(".brand").href =
    "/" +
    (Object.keys(labels).find(
      (key) =>
        key !== "saved" && index.items.some((item) => item.section === key),
    ) || "saved");
  $("#nav").innerHTML = Object.entries(labels)
    .filter(
      ([key]) =>
        key === "saved" || index.items.some((item) => item.section === key),
    )
    .map(
      ([key, label]) =>
        `<a href="/${key}" class="${key === section ? "active" : ""}" ${key === section ? 'aria-current="page"' : ""}>${label}</a>`,
    )
    .join("");
}
function card(item) {
  return `<article class="card"><button class="card-save ${saved[item.id] ? "saved" : ""}" data-save="${item.id}" aria-label="收藏 ${esc(item.title)}" aria-pressed="${!!saved[item.id]}">${saved[item.id] ? "★" : "☆"}</button><a href="${href(item)}"><div class="card-meta"><span class="tag">${esc(item.category)}</span>${item.difficulty ? `<span class="tag ${esc(item.difficulty.toLowerCase())}">${esc(item.difficulty)}</span>` : ""}${item.judgeable ? '<span class="tag accent">可评测</span>' : ""}${progress[item.id] ? '<span class="tag accent">✓ 已学完</span>' : ""}${item.date ? `<span>${esc(item.date.slice(0, 10))}</span>` : ""}${modifiedTime(item)}</div><h2>${esc(item.title)}</h2><p>${esc(item.excerpt)}</p><div class="card-footer"><span>${labels[item.section]}</span><span class="read">${item.section === "problems" ? "开始练习" : "开始阅读"} ↗</span></div></a></article>`;
}
function externalCard(item) {
  const url = safeLink(item.url),
    image = safeLink(item.image),
    favicon = safeLink(item.favicon);
  let host;
  try {
    host = new URL(url).hostname.replace(/^www\./, "");
  } catch {
    host = "外部网站";
  }
  return `<article class="external-bookmark-card"><a class="external-bookmark-main" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${image ? `<span class="external-bookmark-preview"><img src="${esc(image)}" alt="" loading="lazy" referrerpolicy="no-referrer"></span>` : ""}<span class="external-bookmark-content"><strong>${favicon ? `<img class="external-bookmark-favicon" src="${esc(favicon)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}${esc(host)}</strong><span class="external-bookmark-title">${esc(item.title)}</span>${item.description ? `<span class="external-bookmark-description">${esc(item.description)}</span>` : ""}<span class="external-bookmark-url">${esc(url)}</span></span></a><button class="external-bookmark-remove" data-remove-external="${esc(item.id)}" aria-label="移除 ${esc(item.title)}" title="移除收藏">×</button></article>`;
}
function renderList(s) {
  destroyRichEditor();
  const collections = ["专题合集", "公司合集"];
  s.group =
    s.section === "problems" &&
    s.scope !== "all" &&
    (new URL(location.href).searchParams.get("group") === "other" ||
      (s.category && !collections.includes(s.category)))
      ? "other"
      : "";
  const base = index.items.filter(
    (x) =>
      !x.isIndex &&
      (s.section === "saved"
        ? saved[x.id]
        : s.scope === "all" || x.section === s.section),
  );
  if (s.section === "notes")
    base.sort(
      (a, b) =>
        (Date.parse(b.modifiedAt) || 0) - (Date.parse(a.modifiedAt) || 0) ||
        a.path.localeCompare(b.path, "zh-CN"),
    );
  const cats = [
    ...new Set([
      ...base.map((x) => x.category),
      ...(s.section === "saved" && externalBookmarks.length
        ? ["网络文章"]
        : []),
    ]),
  ].sort((a, b) => a.localeCompare(b, "zh-CN"));
  const finished = base.filter((x) => progress[x.id]).length;
  $("#app").innerHTML =
    `<div class="layout"><aside class="sidebar"><p class="side-label">${s.section === "papers" ? "研究领域" : "内容分类"}</p><div class="side-links"><button data-category="" class="${!s.category ? "active" : ""}">全部内容 <span class="count">${base.length + (s.section === "saved" ? externalBookmarks.length : 0)}</span></button>${cats.map((c) => `<button data-category="${esc(c)}" class="${c === s.category ? "active" : ""}">${esc(c)}<span class="count">${c === "网络文章" ? externalBookmarks.length : base.filter((x) => x.category === c).length}</span></button>`).join("")}</div><div class="study-box"><strong>一点一滴，持续进步</strong><div class="progress-track"><span style="width:${base.length ? (finished / base.length) * 100 : 0}%"></span></div><p>已完成 ${finished} / ${base.length} 篇</p><p>收藏与学习进度保存在你的账号中。</p><button class="outline-button" id="export" style="margin-top:14px">导出学习记录</button></div></aside><main id="main"><div class="page-title"><div><p class="eyebrow">${english[s.section]}</p><h1>${labels[s.section]}</h1><p>${subtitles[s.section]}</p></div>${["interview", "problems"].includes(s.section) ? '<button class="outline-button" id="random">随机一题 ↗</button>' : ""}</div><form class="toolbar" id="search-form"><div class="search-wrap"><span>⌕</span><input id="search" type="search" placeholder="搜索标题、知识点或正文…" aria-label="搜索内容" value="${esc(s.q)}"></div><select id="scope" aria-label="搜索范围"><option value="current">当前栏目</option><option value="all" ${s.scope === "all" ? "selected" : ""}>全部栏目</option></select><select id="difficulty" aria-label="难度"><option value="">全部难度</option>${["EASY", "MEDIUM", "HARD"].map((x) => `<option ${s.difficulty === x ? "selected" : ""}>${x}</option>`).join("")}</select></form><div class="results-head"><span id="result-count"></span><label><input type="checkbox" id="done" ${s.done ? "checked" : ""}> 只看未完成</label></div><div id="results"></div><div id="pagination" class="pagination"></div></main></div>`;
  const newButton = document.createElement("button");
  newButton.className = "primary-button";
  newButton.id =
    s.section === "saved" ? "add-external-bookmark" : "new-document";
  newButton.textContent = s.section === "saved" ? "+ 添加外链" : "+ 新建文档";
  const actions = document.createElement("div");
  actions.className = "page-title-actions";
  if ($("#random")) actions.append($("#random"));
  actions.append(newButton);
  $(".page-title").append(actions);
  if (s.section !== "saved" && !can("create")) newButton.remove();
  newButton.onclick =
    s.section === "saved"
      ? () =>
          openExternalBookmarkForm(async (entry) => {
            if (externalBookmarks.some((item) => item.url === entry.url)) {
              toast("这条网址已经收藏");
              return false;
            }
            const next = [
              {
                id:
                  Date.now().toString(36) +
                  "-" +
                  Array.from(crypto.getRandomValues(new Uint32Array(2)), (n) =>
                    n.toString(36),
                  ).join("-"),
                ...entry,
                addedAt: new Date().toISOString(),
              },
              ...externalBookmarks,
            ];
            await queueWrite("externalBookmarks", next);
            externalBookmarks = next;
            toast("已添加网络文章收藏");
            render();
            return true;
          })
      : () =>
          openNewDocument(index, s.section, s.category, async (result) => {
            const response = await fetch("/data/index.json");
            if (!response.ok)
              throw Error("文档已创建，索引加载失败，请刷新页面");
            index = await response.json();
            byId = Object.fromEntries(
              index.items.map((item) => [item.id, item]),
            );
            toast(result.message);
            go(href(byId[result.id]));
          });
  if (s.section === "problems" && s.scope !== "all") {
    const others = base.filter((item) => !collections.includes(item.category));
    $(".side-links").innerHTML =
      `<button data-category="" class="${!s.category && !s.group ? "active" : ""}">全部内容<span class="count">${base.length}</span></button>${collections.map((category) => `<button data-category="${category}" class="${s.category === category ? "active" : ""}">${category}<span class="count">${base.filter((item) => item.category === category).length}</span></button>`).join("")}<button data-problem-group="other" class="${s.group === "other" && !s.category ? "active" : ""}">知识点合集<span class="count">${others.length}</span></button>${
        s.group === "other"
          ? `<div class="problem-subcategories" role="group" aria-label="知识点合集分类">${cats
              .filter((category) => !collections.includes(category))
              .map(
                (category) =>
                  `<button data-category="${esc(category)}" class="${s.category === category ? "active" : ""}">${esc(category)}<span class="count">${others.filter((item) => item.category === category).length}</span></button>`,
              )
              .join("")}</div>`
          : ""
      }`;
  }
  const filter = () =>
    base.filter(
      (x) =>
        (!s.group || !collections.includes(x.category)) &&
        (!s.category || x.category === s.category) &&
        (!s.difficulty || x.difficulty === s.difficulty) &&
        (!s.done || !progress[x.id]) &&
        s.q
          .toLowerCase()
          .trim()
          .split(/\s+/)
          .every((w) => x.search.includes(w)),
    );
  const filterExternal = () =>
    s.section === "saved" && (!s.category || s.category === "网络文章")
      ? externalBookmarks.filter((item) =>
          s.q
            .toLowerCase()
            .trim()
            .split(/\s+/)
            .every((word) =>
              `${item.title} ${item.description} ${item.url}`
                .toLowerCase()
                .includes(word),
            ),
        )
      : [];
  let filtered = filter(),
    filteredExternal = filterExternal();
  const draw = () => {
    const visible =
      s.section === "saved"
        ? [
            ...filtered.map((item) => ({ type: "local", item })),
            ...filteredExternal.map((item) => ({ type: "external", item })),
          ]
        : filtered.map((item) => ({ type: "local", item }));
    const pages = Math.max(1, Math.ceil(visible.length / 18));
    s.page = Math.min(s.page, pages);
    $("#result-count").textContent =
      `${s.q ? "搜索结果 · " : ""}${visible.length.toLocaleString()} 篇内容${s.category ? " / " + s.category : ""}`;
    $("#results").innerHTML = visible.length
      ? `<div class="cards ${["learning", "papers"].includes(s.section) ? "grid-cards" : ""} ${s.section === "saved" ? "saved-cards" : ""}">${visible
          .slice((s.page - 1) * 18, s.page * 18)
          .map((entry) =>
            entry.type === "external"
              ? externalCard(entry.item)
              : card(entry.item),
          )
          .join("")}</div>`
      : `<div class="empty"><h2>${s.section === "saved" && !s.q ? "还没有收藏" : "没有匹配的内容"}</h2><p>${s.section === "saved" && !s.q ? "点击题目旁的 ☆ 收藏站内内容，或添加网络文章外链。" : "试试其他关键词，或清除分类和难度筛选。"}</p><button class="outline-button" id="clear">${s.section === "saved" ? "浏览面试题" : "清除筛选"}</button></div>`;
    $("#results")
      .querySelectorAll(".external-bookmark-main img")
      .forEach((img) => {
        img.onerror = () => {
          const preview = img.closest(".external-bookmark-preview");
          if (preview) preview.remove();
          else img.remove();
        };
      });
    $("#pagination").innerHTML =
      pages > 1
        ? `<button class="outline-button" id="prev" ${s.page <= 1 ? "disabled" : ""}>← 上一页</button><span>${s.page} / ${pages}</span><button class="outline-button" id="next" ${s.page >= pages ? "disabled" : ""}>下一页 →</button>`
        : "";
    if ($("#prev"))
      $("#prev").onclick = () => update({ ...s, page: s.page - 1 });
    if ($("#next"))
      $("#next").onclick = () => update({ ...s, page: s.page + 1 });
    if ($("#clear"))
      $("#clear").onclick = () =>
        go("/" + (s.section === "saved" ? "interview" : s.section));
  };
  draw();
  document
    .querySelectorAll("[data-category]")
    .forEach(
      (b) =>
        (b.onclick = () => update({ category: b.dataset.category, group: "" })),
    );
  document
    .querySelectorAll("[data-problem-group]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          update({ group: b.dataset.problemGroup, category: "" })),
    );
  $("#search-form").onsubmit = (e) => {
    e.preventDefault();
  };
  let timer;
  $("#search").oninput = (e) => {
    const value = e.target.value;
    clearTimeout(timer);
    timer = setTimeout(() => {
      s.q = value;
      s.page = 1;
      filtered = filter();
      filteredExternal = filterExternal();
      history.replaceState({}, "", listingUrl(s));
      draw();
    }, 140);
  };
  $("#scope").onchange = (e) =>
    update({
      scope: e.target.value,
      category: "",
      group: "",
      q: $("#search").value,
    });
  $("#difficulty").onchange = (e) =>
    update({ difficulty: e.target.value, q: $("#search").value });
  $("#done").onchange = (e) =>
    update({ done: e.target.checked, q: $("#search").value });
  if ($("#random"))
    $("#random").onclick = () => {
      if (filtered.length)
        go(href(filtered[Math.floor(Math.random() * filtered.length)]));
      else toast("当前筛选下没有题目");
    };
  $("#export").onclick = () => {
    const drafts = Object.fromEntries(
      Object.entries(accountState).filter(([key]) => key.startsWith("draft.")),
    );
    download(
      "mykb-learning-records.json",
      JSON.stringify(
        {
          version: 2,
          username: currentUser.username,
          exportedAt: new Date().toISOString(),
          saved,
          externalBookmarks,
          progress,
          drafts,
        },
        null,
        2,
      ),
      "application/json",
    );
  };
}
let renderSequence = 0;
async function renderArticle(item, sequence) {
  destroyRichEditor();
  $("#app").innerHTML = '<main id="main" class="loading">正在打开内容…</main>';
  const response = await fetch(`/data/articles/${item.id}.json`);
  if (!response.ok) throw Error("内容文件未找到");
  const data = await response.json();
  if (sequence !== renderSequence) return;
  setStore("last", item.id);
  const body = data.body.replace(/^# .*(?:\r?\n|$)/, "");
  const answerAt =
    item.section === "interview" ? body.indexOf("## 参考答案") : -1;
  const rendered =
    answerAt >= 0
      ? markdown(body.slice(0, answerAt)) +
        `<details class="answer"><summary>查看参考答案</summary>${markdown(body.slice(answerAt))}</details>`
      : markdown(body);
  $("#app").innerHTML =
    `<div class="detail-layout"><main id="main"><div class="breadcrumb"><a href="/${item.section}">${labels[item.section]}</a><span> / </span><a href="/${item.section}?category=${encodeURIComponent(item.category)}">${esc(item.category)}</a><span> / 阅读</span></div><article class="article-card"><span class="tag accent">${labels[item.section]}</span>${item.difficulty ? ` <span class="tag">${esc(item.difficulty)}</span>` : ""}<h1 class="article-title">${esc(item.title)}</h1><div class="article-actions"><button class="outline-button ${saved[item.id] ? "selected" : ""}" data-save="${item.id}" aria-pressed="${!!saved[item.id]}">${saved[item.id] ? "★ 已收藏" : "☆ 收藏"}</button><button class="outline-button ${progress[item.id] ? "selected" : ""}" id="complete">${progress[item.id] ? "✓ 已学完" : "○ 标记学完"}</button><button class="outline-button" id="download">↓ 下载 Markdown</button><button class="outline-button" id="copy-link">复制链接</button><button class="outline-button" id="edit-markdown">✎ 编辑 Markdown</button></div><div class="prose" id="article-body">${rendered}</div><section class="markdown-editor" id="markdown-editor" hidden><div class="markdown-editor-head"><div><h2>编辑 Markdown</h2><p>保存后将直接更新知识库中的原始文件。</p></div><div class="markdown-editor-actions"><button class="outline-button" id="markdown-preview">预览</button><button class="primary-button" id="save-markdown">保存修改</button></div></div><textarea id="markdown-source" spellcheck="false" aria-label="Markdown 内容"></textarea><div class="prose markdown-preview" id="markdown-preview-body" hidden></div><p class="markdown-status" id="markdown-status">尚未保存</p></section>${item.section === "problems" && !item.isIndex && !["专题合集", "公司合集"].includes(item.category) ? `<section class="editor"><h2>我的练习草稿</h2><textarea id="draft" spellcheck="false" aria-label="练习代码草稿"></textarea><div class="editor-toolbar">${item.judgeable ? '<button class="primary-button" id="judge-code">▶ 提交评测</button>' : '<button class="outline-button" disabled>暂未配置自动评测</button>'}<button class="outline-button" id="download-code">下载代码</button><button class="outline-button" id="reset-code">恢复起步代码</button></div><div id="judge-result" class="judge-result" hidden></div></section>` : ""}</article></main><aside class="toc"><div class="section-rule"></div><h3>本页目录</h3><div id="toc-links"></div><hr><a href="/${item.section}">← 返回${labels[item.section]}</a></aside></div>`;
  const practice = $(".editor");
  if (practice) {
    const rail = document.createElement("aside");
    rail.className = "practice-rail";
    const toc = $(".toc");
    toc.before(rail);
    rail.append(toc, practice);
    $(".detail-layout").classList.add("practice-layout");
  }
  const article = $("#article-body");
  if (item.modifiedAt) {
    const metadata = document.createElement("div");
    metadata.className = "article-modified";
    metadata.innerHTML = modifiedTime(item);
    $(".article-title").after(metadata);
  }
  article.querySelectorAll("h1,h2,h3").forEach((h, i) => {
    h.id = "heading-" + i;
    const a = document.createElement("a");
    a.href = "#" + h.id;
    a.textContent = h.textContent;
    if (h.tagName === "H3") a.className = "sub";
    a.onclick = (e) => {
      e.preventDefault();
      const details = h.closest("details");
      if (details) details.open = true;
      h.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    $("#toc-links").append(a);
  });
  article.querySelectorAll("table").forEach((t) => {
    const wrap = document.createElement("div");
    wrap.className = "table-scroll";
    t.before(wrap);
    wrap.append(t);
  });
  article.querySelectorAll("pre").forEach((pre) => {
    const b = document.createElement("button");
    b.className = "copy-code";
    b.textContent = "复制";
    b.onclick = async () => {
      try {
        await navigator.clipboard.writeText(
          pre.querySelector("code")?.textContent || "",
        );
        toast("代码已复制");
      } catch {
        toast("无法访问剪贴板，请手动选择代码");
      }
    };
    pre.append(b);
  });
  article.querySelectorAll("a[href]").forEach((a) => {
    const link = a.getAttribute("href");
    if (link.startsWith("#")) return;
    if (/^https?:\/\//i.test(link)) {
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      return;
    }
    if (/^[a-z][a-z\d+.-]*:/i.test(link)) return;
    try {
      const resolved = new URL(
        link,
        "https://local.invalid/" +
          item.path.split("/").map(encodeURIComponent).join("/"),
      );
      const path = decodeURIComponent(resolved.pathname.slice(1));
      const id =
        index.paths[path] || index.paths[path.replace(/\/$/, "") + "/目录.md"];
      if (id) a.href = href(byId[id]);
      else {
        a.removeAttribute("href");
        a.title = "归档中未包含此链接目标";
        a.classList.add("unavailable");
      }
    } catch {
      a.removeAttribute("href");
    }
  });
  article.querySelectorAll("img").forEach((img) => {
    const src = img.getAttribute("src") || "";
    if (item.section === "notes" && !/^(https?:|data:|\/)/i.test(src)) {
      let rel;
      if (src.startsWith("assets/")) rel = src;
      else {
        try {
          rel = decodeURIComponent(
            new URL(src, "https://local.invalid/" + item.path).pathname.slice(
              1,
            ),
          ).replace(/^notes\//, "");
        } catch {
          rel = src;
        }
      }
      img.src =
        "/note-files/" + rel.split("/").map(encodeURIComponent).join("/");
    }
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.onerror = () => {
      const note = document.createElement("p");
      note.className = "footer-note";
      note.textContent = "图片未缓存，联网后可查看原文图片。";
      img.replaceWith(note);
    };
  });
  $("#complete").onclick = () => {
    progress[item.id]
      ? delete progress[item.id]
      : (progress[item.id] = new Date().toISOString());
    setStore("progress", progress);
    $("#complete").textContent = progress[item.id] ? "✓ 已学完" : "○ 标记学完";
    $("#complete").classList.toggle("selected", !!progress[item.id]);
    toast(progress[item.id] ? "已记录学习进度" : "已取消完成标记");
  };
  $("#download").onclick = () =>
    download(item.title.replace(/[\\/:*?"<>|]/g, "_") + ".md", data.body);
  $("#copy-link").onclick = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      toast("链接已复制");
    } catch {
      toast("请复制浏览器地址栏中的链接");
    }
  };
  if (can("edit"))
    mountRichEditor(item, async (result) => {
      const response = await fetch("/data/index.json");
      index = await response.json();
      byId = Object.fromEntries(index.items.map((x) => [x.id, x]));
      toast(result.message);
      go(href(byId[result.id] || item), true);
    });
  if (!can("edit")) $("#edit-markdown").remove();
  const deleteButton = document.createElement("button");
  deleteButton.id = "delete-document";
  deleteButton.className = "outline-button danger-button";
  deleteButton.textContent = "删除文档";
  if (can("delete")) $(".article-actions").append(deleteButton);
  deleteButton.onclick = async () => {
    deleteButton.disabled = true;
    try {
      const response = await fetch(`/api/articles/${item.id}`),
        data = await response.json();
      if (!response.ok) throw Error(data.message);
      const copies =
        data.copies > 1
          ? `\n知识库中有 ${data.copies} 份相同正文的源文件，将一并移入回收目录。`
          : "";
      if (
        !confirm(
          `确定删除「${item.title}」？${copies}\n文件可从回收目录恢复，未保存的编辑将被放弃。`,
        )
      )
        return;
      const deleted = await fetch(`/api/articles/${item.id}/delete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            revision: data.revision,
            copies: data.copies,
          }),
        }),
        result = await deleted.json();
      if (!deleted.ok) throw Error(result.message);
      const refreshed = await fetch("/data/index.json");
      if (!refreshed.ok) throw Error("文档已删除，请刷新网页更新列表");
      index = await refreshed.json();
      byId = Object.fromEntries(index.items.map((x) => [x.id, x]));
      delete saved[item.id];
      delete progress[item.id];
      setStore("saved", saved);
      setStore("progress", progress);
      destroyRichEditor();
      go("/" + item.section, true);
      toast(result.message);
    } catch (error) {
      toast(error.message || "删除失败");
    } finally {
      deleteButton.disabled = false;
    }
  };
  if ($("#draft")) {
    const starter =
      data.body.match(
        /## 起步代码[\s\S]*?```(?:python|py)?\n([\s\S]*?)```/,
      )?.[1] || "# 在这里编写你的解法\n";
    const draft = $("#draft");
    draft.value = getStore("draft." + item.id, starter);
    const highlightDraft = mountDraftHighlight(draft);
    const save = () => {
      highlightDraft();
      if (!setStore("draft." + item.id, draft.value))
        toast("保存失败，请下载备份");
    };
    draft.oninput = save;
    draft.onkeydown = (e) => {
      if (e.key === "Tab") {
        e.preventDefault();
        draft.setRangeText(
          "    ",
          draft.selectionStart,
          draft.selectionEnd,
          "end",
        );
        save();
      }
    };
    $("#download-code").onclick = () => download("solution.py", draft.value);
    $("#reset-code").onclick = () => {
      if (confirm("恢复起步代码将替换当前草稿，是否继续？")) {
        draft.value = starter;
        save();
      }
    };
    if ($("#judge-code")) {
      $("#judge-code").onclick = async () => {
        const button = $("#judge-code"),
          panel = $("#judge-result");
        button.disabled = true;
        panel.hidden = false;
        panel.className = "judge-result running";
        panel.textContent = "正在沙箱中运行隐藏测试…";
        try {
          const response = await fetch("/api/judge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ problemId: item.id, source: draft.value }),
          });
          const result = await response.json();
          const accepted = result.status === "accepted";
          panel.className =
            "judge-result " + (accepted ? "accepted" : "failed");
          panel.textContent =
            (accepted ? "✓ " : "✕ ") +
            result.message +
            " · " +
            (result.durationMs ?? "—") +
            " ms" +
            (result.output ? "\n\n程序输出：\n" + result.output : "");
          if (accepted) {
            progress[item.id] = new Date().toISOString();
            setStore("progress", progress);
            $("#complete").textContent = "✓ 已学完";
            $("#complete").classList.add("selected");
          }
        } catch {
          panel.className = "judge-result failed";
          panel.textContent = "评测服务不可用，请稍后重试";
        } finally {
          button.disabled = false;
        }
      };
    }
  }
}
async function render() {
  const sequence = ++renderSequence;
  const s = route();
  if (
    !s.id &&
    s.section !== "saved" &&
    !index.items.some((item) => item.section === s.section)
  ) {
    s.section =
      Object.keys(labels).find(
        (key) =>
          key !== "saved" && index.items.some((item) => item.section === key),
      ) || "saved";
    history.replaceState({}, "", listingUrl(s));
  }
  nav(s.section);
  document.title = `${s.id && byId[s.id] ? byId[s.id].title : labels[s.section]} · ${siteName}`;
  try {
    if (s.id) {
      const item = byId[s.id];
      if (!item) {
        $("#app").innerHTML =
          '<main id="main" class="empty"><h2>没有找到这篇内容</h2><a href="/interview">返回面试题</a></main>';
        return;
      }
      nav(item.section);
      await renderArticle(item, sequence);
    } else renderList(s);
  } catch (e) {
    if (sequence === renderSequence)
      $("#app").innerHTML =
        `<main id="main" class="empty"><h2>内容暂时无法打开</h2><p>${esc(e.message)}</p><a href="/${s.section}">返回栏目</a></main>`;
  }
}
document.addEventListener("click", async (e) => {
  const external = e.target.closest("[data-remove-external]");
  if (external) {
    const next = externalBookmarks.filter(
      (item) => item.id !== external.dataset.removeExternal,
    );
    try {
      await queueWrite("externalBookmarks", next);
      externalBookmarks = next;
      toast("已移除网络文章收藏");
      render();
    } catch {}
    return;
  }
  const b = e.target.closest("[data-save]");
  if (b) {
    await toggleSaved(b.dataset.save);
    return;
  }
  const a = e.target.closest("a[href]");
  if (
    !a ||
    e.defaultPrevented ||
    e.button !== 0 ||
    e.metaKey ||
    e.ctrlKey ||
    e.shiftKey ||
    e.altKey ||
    a.target ||
    a.hasAttribute("download") ||
    a.getAttribute("href").startsWith("#")
  )
    return;
  const url = new URL(a.href);
  if (
    url.origin === location.origin &&
    (/^\/(interview|problems|learning|papers|notes|saved)$/.test(
      url.pathname,
    ) ||
      url.pathname === "/")
  ) {
    e.preventDefault();
    go(url.pathname + url.search);
  }
});
window.addEventListener("popstate", render);
try {
  const r = await fetch("/data/index.json");
  if (!r.ok) throw Error("索引加载失败");
  index = await r.json();
  byId = Object.fromEntries(index.items.map((x) => [x.id, x]));
  await render();
} catch (e) {
  $("#app").innerHTML =
    `<main id="main" class="empty"><h2>学习库未能载入</h2><p>${esc(e.message)}。请确认本地服务正在运行。</p><button class="outline-button" onclick="location.reload()">重新加载</button></main>`;
}
