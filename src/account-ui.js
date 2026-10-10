import "./account-ui.css";
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const labels = {
  notes: "Note",
  interview: "面试题",
  problems: "手撕题",
  learning: "学习路径",
  papers: "最新论文",
};
export async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok) throw Error(result.message || "请求失败");
  return result;
}
export async function requireSession() {
  let user;
  try {
    user = (await api("/api/auth/me")).user;
  } catch {}
  if (!user) {
    document.body.classList.add("signed-out");
    document.querySelector("#nav").replaceChildren();
    document.querySelector("#app").innerHTML =
      `<main class="login-page" id="main"><form class="login-card"><p class="eyebrow">MYKB</p><h1>登录知识库</h1><label>用户名<input name="username" required autocomplete="username" maxlength="40" autofocus></label><label>密码<input name="password" type="password" required autocomplete="current-password" maxlength="256"></label><p class="account-error" role="alert"></p><button class="primary-button" type="submit">登录</button></form></main>`;
    user = await new Promise((resolve) => {
      const form = document.querySelector(".login-card");
      form.onsubmit = async (event) => {
        event.preventDefault();
        const button = form.querySelector("button");
        button.disabled = true;
        try {
          const result = await api("/api/auth/login", {
            username: form.elements.namedItem("username").value,
            password: form.elements.namedItem("password").value,
          });
          resolve(result.user);
        } catch (error) {
          form.querySelector("[role=alert]").textContent = error.message;
        } finally {
          button.disabled = false;
        }
      };
    });
    document.body.classList.remove("signed-out");
  }
  const state = await api("/api/state");
  if (user.admin && user.id === 1 && !state.legacyImported) {
    const legacy = [];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const name = localStorage.key(i),
          key = name.slice("llmforge.local.".length);
        if (
          name.startsWith("llmforge.local.") &&
          (["saved", "externalBookmarks", "progress"].includes(key) ||
            key.startsWith("draft."))
        ) {
          const value = JSON.parse(localStorage.getItem(name));
          if (
            value &&
            (!Array.isArray(value) || value.length) &&
            (!(typeof value === "object") || Object.keys(value).length)
          )
            legacy.push({ name, key, value });
        }
      }
      if (legacy.length) {
        for (const entry of legacy) {
          let value = entry.value;
          if (entry.key === "saved" || entry.key === "progress")
            value = { ...value, ...state[entry.key] };
          else if (entry.key === "externalBookmarks")
            value = [
              ...(state[entry.key] || []),
              ...value.filter(
                (item) =>
                  !(state[entry.key] || []).some(
                    (existing) => existing.url === item.url,
                  ),
              ),
            ];
          else if (state[entry.key] !== undefined) value = state[entry.key];
          await api("/api/state", { key: entry.key, value });
          state[entry.key] = value;
        }
        await api("/api/state", { key: "legacyImported", value: true });
        state.legacyImported = true;
        for (const entry of legacy) localStorage.removeItem(entry.name);
      }
    } catch {
      alert("旧浏览器记录暂未完成迁移，原数据已保留；请稍后重新登录重试。");
    }
  }

  return { user, state };
}
export function mountAccountMenu(user, actions, beforeLogout) {
  const container = document.createElement("div");
  container.className = "account-menu";
  const icon = user.admin
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 3-.6 2.4-2 .9L4 5.7 2 9l1.8 1.7v2.6L2 15l2 3.3 2.4-.6 2 .9L9 21h4l.6-2.4 2-.9 2.4.6 2-3.3-1.8-1.7v-2.6L20 9l-2-3.3-2.4.6-2-.9L13 3Z"/><circle cx="11" cy="12" r="3"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></svg>';
  container.innerHTML = `<button class="icon-button" id="account-button" aria-label="${user.admin ? "管理菜单" : "账号菜单"}" aria-expanded="false" title="${esc(user.username)}">${icon}</button><div class="account-dropdown" hidden><strong>${esc(user.username)}${user.admin ? " · 管理员" : ""}</strong>${user.admin ? '<button type="button" id="manage-users">用户管理</button>' : ""}<button type="button" id="change-password">修改密码</button><button type="button" id="logout">退出登录</button></div>`;
  actions.prepend(container);
  const toggle = container.querySelector("#account-button"),
    menu = container.querySelector(".account-dropdown");
  const close = () => {
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  };
  toggle.onclick = () => {
    menu.hidden = !menu.hidden;
    toggle.setAttribute("aria-expanded", String(!menu.hidden));
  };
  document.addEventListener("click", (e) => {
    if (!container.contains(e.target)) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });
  if (user.admin)
    container.querySelector("#manage-users").onclick = () => {
      close();
      openUsers(user);
    };
  container.querySelector("#change-password").onclick = () => {
    close();
    openPassword();
  };
  container.querySelector("#logout").onclick = async () => {
    try {
      await beforeLogout();
      await api("/api/auth/logout", {});
      location.reload();
    } catch (error) {
      alert(error.message);
    }
  };
}
function dialogShell(title, css = "") {
  const dialog = document.createElement("dialog");
  dialog.className = "account-dialog " + css;
  dialog.innerHTML = `<div class="account-dialog-head"><h2>${title}</h2><button type="button" class="outline-button" data-close>关闭</button></div><div class="account-dialog-body"></div>`;
  dialog.querySelector("[data-close]").onclick = () => dialog.close();
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  document.body.append(dialog);
  dialog.showModal();
  return dialog;
}
function openPassword() {
  const dialog = dialogShell("修改密码");
  dialog.querySelector(".account-dialog-body").innerHTML =
    '<form class="account-form"><label>当前密码<input name="current" type="password" required autocomplete="current-password"></label><label>新密码<input name="password" type="password" required minlength="10" maxlength="256" autocomplete="new-password" placeholder="至少 10 位"></label><p class="account-error" role="alert"></p><button class="primary-button">保存新密码</button></form>';
  const form = dialog.querySelector("form");
  form.onsubmit = async (e) => {
    e.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      await api("/api/auth/password", {
        currentPassword: form.elements.namedItem("current").value,
        password: form.elements.namedItem("password").value,
      });
      location.reload();
    } catch (error) {
      form.querySelector("[role=alert]").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
}
async function openUsers(actor) {
  const dialog = dialogShell("用户管理", "users-dialog"),
    body = dialog.querySelector(".account-dialog-body");
  body.textContent = "正在加载…";
  try {
    const data = await api("/api/admin/users");
    const draw = () => {
      body.innerHTML = `<div class="users-layout"><aside><button class="primary-button" id="add-user">＋ 添加用户</button><div class="user-list">${data.users.map((user) => `<button type="button" data-user="${user.id}">${esc(user.username)}<small>${user.admin ? "管理员" : "普通用户"}</small></button>`).join("")}</div></aside><section id="user-settings"></section></div>`;
      body.querySelector("#add-user").onclick = () => edit(null);
      body
        .querySelectorAll("[data-user]")
        .forEach(
          (button) =>
            (button.onclick = () =>
              edit(
                data.users.find(
                  (user) => user.id === Number(button.dataset.user),
                ),
              )),
        );
      edit(data.users.find((user) => user.id === actor.id));
    };
    function edit(user) {
      const permissions = user?.permissions || { visible: null },
        panel = body.querySelector("#user-settings");
      panel.innerHTML = `<form class="account-form"><h3>${user ? "编辑 " + esc(user.username) : "添加用户"}</h3>${user ? "" : '<label>用户名<input name="username" required minlength="3" maxlength="40" pattern="[A-Za-z0-9_.\\-]+" autocomplete="off"></label>'}<label>${user ? "重设密码（留空不修改）" : "密码"}<input name="password" type="password" ${user ? "" : "required"} minlength="10" maxlength="256" autocomplete="new-password" placeholder="至少 10 位"></label><label class="account-check"><input name="admin" type="checkbox" ${user?.admin ? "checked" : ""} ${user?.id === actor.id ? "disabled" : ""}>管理员（所有权限）</label><fieldset class="document-permissions"><legend>文档操作权限</legend>${[
        ["create", "新建文档"],
        ["edit", "编辑文档"],
        ["delete", "删除文档"],
      ]
        .map(
          ([key, label]) =>
            `<label class="account-check"><input type="checkbox" name="${key}" ${permissions[key] ? "checked" : ""}>${label}</label>`,
        )
        .join(
          "",
        )}</fieldset><fieldset class="visibility-permissions"><legend>文章分类可见性</legend><label class="account-check"><input type="checkbox" name="allVisible" ${permissions.visible === null ? "checked" : ""}>全部分类（包含今后新增的分类）</label><div class="visibility-categories">${Object.entries(
        labels,
      )
        .map(
          ([section, label]) =>
            `<details open><summary><label class="account-check visibility-section"><input type="checkbox" data-visible-section="${section}" aria-label="${label}全部分类">${label}</label></summary>${data.categories
              .filter((category) => category.section === section)
              .map(
                (category) =>
                  `<label class="account-check"><input type="checkbox" name="visible" value="${esc(category.key)}" ${permissions.visible === null || permissions.visible?.includes(category.key) ? "checked" : ""}>${esc(category.category)}</label>`,
              )
              .join("")}</details>`,
        )
        .join(
          "",
        )}</div></fieldset><p class="account-error" role="alert"></p><div class="account-form-actions"><button class="primary-button" type="submit">保存设置</button>${user && user.id !== actor.id ? '<button type="button" class="outline-button danger-button" id="remove-user">删除用户</button>' : ""}</div></form>`;
      const form = panel.querySelector("form"),
        admin = form.elements.namedItem("admin"),
        all = form.elements.namedItem("allVisible");
      const groups = [...panel.querySelectorAll("[data-visible-section]")];
      function syncGroups() {
        for (const group of groups) {
          const children = [
            ...group.closest("details").querySelectorAll("[name=visible]"),
          ];
          const checked = children.filter((input) => input.checked).length;
          group.checked = children.length > 0 && checked === children.length;
          group.indeterminate = checked > 0 && checked < children.length;
          group.disabled = admin.checked || !children.length;
        }
      }
      function disabled() {
        panel
          .querySelectorAll("fieldset input")
          .forEach((input) => (input.disabled = admin.checked));
        syncGroups();
      }
      groups.forEach((group) => {
        group.onclick = (event) => event.stopPropagation();
        group.closest("label").onclick = (event) => event.stopPropagation();
        group.onchange = () => {
          group
            .closest("details")
            .querySelectorAll("[name=visible]")
            .forEach((input) => (input.checked = group.checked));
          all.checked = false;
          syncGroups();
        };
      });
      panel.querySelectorAll("[name=visible]").forEach((input) => {
        input.onchange = () => {
          all.checked = false;
          syncGroups();
        };
      });
      admin.onchange = disabled;
      all.onchange = () => {
        if (all.checked)
          panel
            .querySelectorAll("[name=visible]")
            .forEach((input) => (input.checked = true));
        disabled();
      };
      disabled();
      async function save(payload) {
        const result = await api("/api/admin/users", payload);
        const refreshed = await api("/api/admin/users");
        data.users = refreshed.users;
        draw();
        return result;
      }
      form.onsubmit = async (event) => {
        event.preventDefault();
        const button = form.querySelector("[type=submit]");
        button.disabled = true;
        try {
          await save({
            action: user ? "update" : "create",
            id: user?.id,
            username: form.elements.namedItem("username")?.value,
            password: form.elements.namedItem("password").value,
            admin: admin.checked,
            permissions: {
              visible: all.checked
                ? null
                : [...form.querySelectorAll("[name=visible]:checked")].map(
                    (input) => input.value,
                  ),
              edit: form.elements.namedItem("edit").checked,
              create: form.elements.namedItem("create").checked,
              delete: form.elements.namedItem("delete").checked,
            },
          });
        } catch (error) {
          form.querySelector("[role=alert]").textContent = error.message;
          button.disabled = false;
        }
      };
      if (panel.querySelector("#remove-user"))
        panel.querySelector("#remove-user").onclick = async () => {
          if (
            !confirm(
              "删除用户 " +
                user.username +
                "？该用户的收藏、草稿和登录会话将同时删除。",
            )
          )
            return;
          try {
            await save({ action: "delete", id: user.id });
          } catch (error) {
            form.querySelector("[role=alert]").textContent = error.message;
          }
        };
    }
    draw();
  } catch (error) {
    body.textContent = error.message;
  }
}
