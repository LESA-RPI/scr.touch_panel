/* Role names and values are supplied by the panel's design_tokens.py. */
window.SCRDesign = {
  apply(palette, theme) {
    if (!palette) return;
    for (const [key, value] of Object.entries(palette))
      document.documentElement.style.setProperty('--' + key.replaceAll('_', '-'), value);
    for (const [alias, key] of [
      ['soft', 'control'],
      ['line', 'border'],
    ])
      document.documentElement.style.setProperty('--' + alias, palette[key]);
    document.documentElement.style.colorScheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
  },
};
