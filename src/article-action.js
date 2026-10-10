const paths = {
  sparkles:
    '<path d="m9 3 2 6 6 2-6 2-2 6-2-6-6-2 6-2Z" fill="currentColor"/><path d="M19 2v6m-3-3h6M19 16v4m-2-2h4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  random: '<path d="m16 3 5 0 0 5M4 20 17 7M4 4l5 5m6 6 6 6m-5 0h5v-5"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  save: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',
  complete: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  download: '<path d="M12 3v12m-4-4 4 4 4-4M5 16v4h14v-4"/>',
  edit: '<path d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15Z"/>',
  back: '<path d="m10 5-7 7 7 7M3 12h18"/>',
};

export function actionIcon(icon) {
  return `<svg class="action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[icon]}</svg>`;
}

export function articleAction(icon, label) {
  return `${actionIcon(icon)}<span>${label}</span>`;
}
