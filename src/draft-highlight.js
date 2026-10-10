import hljs from "highlight.js/lib/common";
import "./draft-highlight.css";

export function mountDraftHighlight(textarea) {
  const wrapper = document.createElement("div");
  wrapper.className = "draft-code-editor";
  const preview = document.createElement("pre");
  preview.className = "draft-highlight";
  preview.setAttribute("aria-hidden", "true");
  const code = document.createElement("code");
  preview.append(code);
  textarea.before(wrapper);
  wrapper.append(preview, textarea);
  textarea.wrap = "off";
  textarea.autocomplete = "off";
  textarea.setAttribute("autocapitalize", "off");
  const syncScroll = () => {
    preview.scrollTop = textarea.scrollTop;
    preview.scrollLeft = textarea.scrollLeft;
  };
  const render = () => {
    if (textarea.value.length <= 100000)
      code.innerHTML = hljs.highlight(textarea.value + "\n", {
        language: "python",
        ignoreIllegals: true,
      }).value;
    else code.textContent = textarea.value + "\n";
    syncScroll();
  };
  textarea.addEventListener("scroll", syncScroll);
  render();
  return render;
}
