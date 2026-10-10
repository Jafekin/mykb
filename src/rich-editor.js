import { articleAction } from "./article-action.js";
import { loadEditor } from "./editor-loader.js";
import "@toast-ui/editor/dist/toastui-editor.css";
import "./rich-editor.css";

let current;
export function hasUnsavedRichChanges() {
  return current?.hasUnsavedChanges?.() || false;
}
export function destroyRichEditor() {
  current?.destroy();
  current = null;
}
export function mountRichEditor(item, onSaved, onError) {
  const panel = document.querySelector("#markdown-editor"),
    toggle = document.querySelector("#edit-markdown");
  panel.innerHTML =
    '<div class="markdown-editor-head"><div><h2>编辑文章</h2><p>直接编辑正文，保存到原始 Markdown 文件。</p></div><div class="markdown-editor-actions"><button class="outline-button" id="editor-mode">所见即所得</button><button class="primary-button" id="save-markdown">保存修改</button></div></div><p class="markdown-status" id="markdown-status" role="status">正在读取源文件…</p><div id="rich-editor"></div>';
  if (item.personal) {
    panel.querySelector(".markdown-editor-head p").textContent =
      "保存到你的个人文档，仅你可见。";
    panel.querySelector("#markdown-status").textContent = "正在读取个人文档…";
  }
  const status = panel.querySelector("#markdown-status"),
    save = panel.querySelector("#save-markdown"),
    mode = panel.querySelector("#editor-mode");
  let revision,
    original,
    dirty = false,
    saving = false,
    opening = false;
  toggle.innerHTML = articleAction("edit", "编辑文章");
  const beforeUnload = (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  };
  window.addEventListener("beforeunload", beforeUnload);
  toggle.onclick = async () => {
    if (opening || saving) return;
    if (!panel.hidden) {
      panel.hidden = true;
      document.querySelector("#article-body").hidden = false;
      toggle.innerHTML = articleAction("edit", "编辑文章");
      return;
    }
    panel.hidden = false;
    document.querySelector("#article-body").hidden = true;
    toggle.innerHTML = articleAction("back", "返回阅读");
    if (current) {
      current.focus();
      return;
    }
    opening = true;
    save.disabled = true;
    try {
      status.textContent = "正在加载编辑器…";
      const [response, Editor] = await Promise.all([
        fetch(`/api/articles/${item.id}`),
        loadEditor(),
      ]);
      const data = await response.json();
      if (!response.ok) throw Error(data.message || "无法读取源文件");
      if (!panel.isConnected) return;
      revision = data.revision;
      original = data.body;
      current = new Editor({
        el: panel.querySelector("#rich-editor"),
        height: "auto",
        minHeight: "500px",
        initialEditType: "markdown",
        initialValue: original,
        language: "zh-CN",
        hideModeSwitch: true,
        usageStatistics: false,
        autofocus: true,
        toolbarItems: [
          ["heading", "bold", "italic", "strike"],
          ["hr", "quote"],
          ["ul", "ol", "task", "indent", "outdent"],
          ["table", "image", "link"],
          ["code", "codeblock"],
        ],
        events: {
          change: () => {
            dirty = true;
            status.textContent = "有未保存的修改";
          },
        },
        hooks: {
          addImageBlobHook: () => {
            status.textContent = "请使用图片链接插入图片";
            return false;
          },
        },
      });
      status.textContent = item.personal ? "已打开个人文档" : "已打开源文件";
      current.hasUnsavedChanges = () => dirty;
      const destroy = current.destroy.bind(current);
      current.destroy = () => {
        window.removeEventListener("beforeunload", beforeUnload);
        destroy();
      };
    } catch (error) {
      status.textContent = "打开失败：" + error.message;
      onError?.(status.textContent);
    } finally {
      opening = false;
      save.disabled = !current;
    }
  };
  mode.onclick = () => {
    if (!current) return;
    const wysiwyg = current.isWysiwygMode();
    current.changeMode(wysiwyg ? "markdown" : "wysiwyg");
    mode.textContent = wysiwyg ? "所见即所得" : "Markdown 源码";
  };
  save.onclick = async () => {
    if (!current || saving) return;
    saving = true;
    save.disabled = true;
    mode.disabled = true;
    status.textContent = item.personal
      ? "正在保存个人文档…"
      : "正在保存源文件…";
    try {
      const body = dirty ? current.getMarkdown() : original;
      const response = await fetch(`/api/articles/${item.id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ body, revision }),
        }),
        result = await response.json();
      if (!response.ok) throw Error(result.message || "保存失败");
      dirty = false;
      await onSaved(result);
    } catch (error) {
      status.textContent = "保存失败：" + error.message;
      onError?.(status.textContent);
    } finally {
      saving = false;
      save.disabled = false;
      mode.disabled = false;
    }
  };
}
