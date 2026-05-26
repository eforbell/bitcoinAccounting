'use strict';

(function () {
  var STORAGE_KEY = 'btc-theme';
  var themeMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

  function getPreference() {
    return localStorage.getItem(STORAGE_KEY) || 'system';
  }

  function resolveTheme(preference) {
    if (preference === 'light' || preference === 'dark') return preference;
    return themeMedia && themeMedia.matches ? 'light' : 'dark';
  }

  function themeColor(theme) {
    return theme === 'light' ? '#FAF8F4' : '#141310';
  }

  function setThemeColorMeta(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', themeColor(theme));
  }

  function applyTheme(preference) {
    var resolvedTheme = resolveTheme(preference);
    document.documentElement.setAttribute('data-theme', resolvedTheme);
    document.documentElement.setAttribute('data-theme-preference', preference);
    setThemeColorMeta(resolvedTheme);

    window.dispatchEvent(new CustomEvent('btc:theme-change', {
      detail: { preference: preference, theme: resolvedTheme }
    }));
  }

  function setPreference(preference) {
    if (preference === 'system') localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, preference);
    applyTheme(getPreference());
  }

  window.BtcTheme = {
    getPreference: getPreference,
    getResolvedTheme: function () {
      return document.documentElement.getAttribute('data-theme') || resolveTheme(getPreference());
    },
    setPreference: setPreference,
    applyCurrentTheme: function () {
      applyTheme(getPreference());
    }
  };

  if (themeMedia && typeof themeMedia.addEventListener === 'function') {
    themeMedia.addEventListener('change', function () {
      if (getPreference() === 'system') applyTheme('system');
    });
  }

  applyTheme(getPreference());
})();
