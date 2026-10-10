import Editor from "@toast-ui/editor";

const labels = {
  notes: "Note",
  interview: "面试题",
  problems: "手撕题",
  learning: "学习路径",
  papers: "最新论文",
};
export function openNewDocument(index, section, category, onCreated) {
  const dialog = document.createElement("dialog");
  dialog.className = "new-document-dialog";
  dialog.innerHTML =
    '<form id="new-document-form"><div class="markdown-editor-head"><h2>新建文档</h2><button type="button" class="outline-button" id="cancel-document">取消</button></div><div class="document-fields"><label>标题<input id="document-title" required maxlength="120" placeholder="输入文档标题"></label><label>栏目<select id="document-section"></select></label><label>分类<input id="document-category" maxlength="80" list="document-categories" placeholder="留空归入综合，也可输入新分类"><datalist id="document-categories"></datalist></label></div><div class="markdown-editor"><div id="new-document-editor"></div></div><div class="editor-toolbar"><button type="button" class="outline-button" id="document-mode">Markdown 源码</button><button type="submit" class="primary-button" id="create-document">创建并保存</button><span id="document-status" class="draft-status" role="status"></span></div></form>';
  document.body.append(dialog);
  const $ = (s) => dialog.querySelector(s),
    select = $("#document-section"),
    title = $("#document-title"),
    input = $("#document-category"),
    status = $("#document-status");
  for (const [id, label] of Object.entries(labels)) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = label;
    select.append(option);
  }
  select.value = labels[section] ? section : "notes";
  input.value = category || "";
  const categories = () => {
    $("#document-categories").replaceChildren(
      ...[
        ...new Set(
          index.items
            .filter((item) => item.section === select.value)
            .map((item) => item.category)
            .filter((name) => name !== "综合"),
        ),
      ]
        .sort()
        .map((name) => {
          const option = document.createElement("option");
          option.value = name;
          return option;
        }),
    );
  };
  categories();
  select.onchange = () => {
    input.value = "";
    categories();
  };
  dialog.showModal();
  const editor = new Editor({
    el: $("#new-document-editor"),
    height: "400px",
    initialEditType: "wysiwyg",
    initialValue: "",
    language: "zh-CN",
    hideModeSwitch: true,
    usageStatistics: false,
    autofocus: false,
    placeholder: "在这里编写正文…",
    toolbarItems: [
      ["heading", "bold", "italic", "strike"],
      ["hr", "quote"],
      ["ul", "ol", "task", "indent", "outdent"],
      ["table", "image", "link"],
      ["code", "codeblock"],
    ],
    hooks: {
      addImageBlobHook: () => {
        status.textContent = "请使用图片链接插入图片";
        return false;
      },
    },
  });
  const resizeObserver = new ResizeObserver(() => {
    const height = $(".markdown-editor").clientHeight;
    if (height > 0) editor.setHeight(height + "px");
  });
  resizeObserver.observe($(".markdown-editor"));
  let saving = false,
    dirty = false;
  const beforeUnload = (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  };
  window.addEventListener("beforeunload", beforeUnload);
  editor.on("change", () => {
    dirty = true;
  });
  title.oninput = input.oninput = () => {
    dirty = true;
  };
  const close = () => {
    if (saving) return;
    if (dirty && !confirm("文档尚未保存，确定取消创建？")) return;
    dialog.close();
  };
  $("#cancel-document").onclick = close;
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  dialog.addEventListener("close", () => {
    resizeObserver.disconnect();
    window.removeEventListener("beforeunload", beforeUnload);
    editor.destroy();
    dialog.remove();
  });
  $("#document-mode").onclick = () => {
    const wysiwyg = editor.isWysiwygMode();
    editor.changeMode(wysiwyg ? "markdown" : "wysiwyg");
    $("#document-mode").textContent = wysiwyg ? "所见即所得" : "Markdown 源码";
  };
  $("#new-document-form").onsubmit = async (e) => {
    e.preventDefault();
    if (saving) return;
    const body = editor.getMarkdown();
    if (!body.trim()) {
      status.textContent = "请填写文档正文";
      editor.focus();
      return;
    }
    saving = true;
    $("#create-document").disabled = $("#cancel-document").disabled = true;
    status.textContent = "正在创建文档…";
    try {
      const response = await fetch("/api/articles", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title.value,
            section: select.value,
            category: input.value,
            body,
          }),
        }),
        result = await response.json();
      if (!response.ok) throw Error(result.message || "创建失败");
      dirty = false;
      dialog.close();
      await onCreated(result);
    } catch (error) {
      status.textContent = error.message;
    } finally {
      saving = false;
      if (dialog.isConnected)
        $("#create-document").disabled = $("#cancel-document").disabled = false;
    }
  };
  title.focus();
}
