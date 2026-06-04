'use strict';

(function () {
  var STORAGE_KEY = 'btc-privacy';
  var VALID = ['off', 'on'];

  function getPreference() {
    var v = localStorage.getItem(STORAGE_KEY);
    return VALID.indexOf(v) !== -1 ? v : 'off';
  }

  function setPreference(val) {
    if (VALID.indexOf(val) === -1) return;
    localStorage.setItem(STORAGE_KEY, val);
    apply(val);
    window.dispatchEvent(new CustomEvent('btc:privacy-change', {
      detail: { privacy: val }
    }));
  }

  function isEnabled() {
    return getPreference() === 'on';
  }

  function apply(val) {
    document.documentElement.setAttribute('data-privacy', val || getPreference());
  }

  apply();

  window.BtcPrivacy = {
    getPreference: getPreference,
    setPreference: setPreference,
    isEnabled: isEnabled
  };
})();
