// Chain desktop document and sidebar scrolling in both directions.
export function mountPageScroll() {
  document.addEventListener(
    "wheel",
    (event) => {
      if (
        event.defaultPrevented ||
        event.ctrlKey ||
        event.deltaY === 0 ||
        Math.abs(event.deltaX) > Math.abs(event.deltaY) ||
        !window.matchMedia("(min-width: 701px)").matches
      )
        return;
      const layout = document.querySelector(".layout");
      const sidebar = layout?.querySelector(":scope > .sidebar");
      const footer = document.querySelector(".site-footer");
      if (
        !sidebar ||
        !footer ||
        sidebar.contains(event.target) ||
        event.target.closest("dialog, textarea, .toastui-editor-defaultUI")
      )
        return;
      const delta =
        event.deltaY *
        (event.deltaMode === 1
          ? 16
          : event.deltaMode === 2
            ? window.innerHeight
            : 1);
      const boundary = Math.max(
        0,
        footer.getBoundingClientRect().top +
          window.scrollY -
          window.innerHeight,
      );
      if (delta < 0) {
        if (sidebar.scrollTop <= 1 || !event.cancelable) return;
        const distance = -delta;
        const footerStep = Math.max(0, window.scrollY - boundary);
        if (distance <= footerStep) return;
        event.preventDefault();
        const sidebarStep = Math.min(sidebar.scrollTop, distance - footerStep);
        sidebar.scrollTop -= sidebarStep;
        window.scrollTo({
          top: Math.max(
            0,
            window.scrollY - footerStep - (distance - footerStep - sidebarStep),
          ),
          behavior: "instant",
        });
        return;
      }
      const remaining =
        sidebar.scrollHeight - sidebar.clientHeight - sidebar.scrollTop;
      if (remaining <= 1) return;
      const documentStep = Math.max(0, boundary - window.scrollY);
      if (delta <= documentStep) return;
      if (!event.cancelable) return;
      event.preventDefault();
      const sidebarStep = Math.min(remaining, delta - documentStep);
      sidebar.scrollTop += sidebarStep;
      window.scrollTo({
        top:
          window.scrollY +
          documentStep +
          Math.max(0, delta - documentStep - sidebarStep),
        behavior: "instant",
      });
    },
    { passive: false },
  );
}
