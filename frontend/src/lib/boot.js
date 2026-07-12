export function hideBootLoading() {
  const el = document.getElementById('boot-loading');
  if (el) el.style.display = 'none';
}

export function showBootError(msg) {
  hideBootLoading();
  const el = document.getElementById('boot-error');
  if (el) {
    el.style.display = 'block';
    el.textContent = msg;
  }
}
