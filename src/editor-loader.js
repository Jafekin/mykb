let loading;
export function loadEditor() {
  loading ??= import("./editor-runtime.js").catch((error) => {
    loading = null;
    throw error;
  });
  return loading.then((module) => module.default);
}
