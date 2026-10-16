/* Extra diagnostics remain observation-only and share the panel's visual roles. */
(() => {
  async function refresh() {
    try {
      const response = await fetch('/api/controller', { cache: 'no-store' });
      const value = await response.json();
      window.SCRDesign.apply(value.palette, value.preferences?.resolved_theme);
    } catch (_) {}
  }
  refresh();
  setInterval(refresh, 15000);
})();
