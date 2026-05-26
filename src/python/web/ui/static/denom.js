'use strict';

(function () {
  var STORAGE_KEY = 'btc-denom';
  var SATS_PER_BTC = 100000000;
  var VALID = ['btc', 'sats'];

  function getPreference() {
    var v = localStorage.getItem(STORAGE_KEY);
    return VALID.indexOf(v) !== -1 ? v : 'btc';
  }

  function setPreference(denom) {
    if (VALID.indexOf(denom) === -1) return;
    localStorage.setItem(STORAGE_KEY, denom);
    window.dispatchEvent(new CustomEvent('btc:denom-change', {
      detail: { denom: denom }
    }));
  }

  function formatValue(btcAmount) {
    var n = Number(btcAmount);
    if (isNaN(n)) return '–';
    if (getPreference() === 'sats') {
      var sats = Math.round(n * SATS_PER_BTC);
      return sats.toLocaleString('en-US') + ' sats';
    }
    return n.toFixed(8) + ' BTC';
  }

  function unit() {
    return getPreference() === 'sats' ? 'sats' : 'BTC';
  }

  window.BtcDenom = {
    getPreference: getPreference,
    setPreference: setPreference,
    format: formatValue,
    unit: unit,
    SATS_PER_BTC: SATS_PER_BTC
  };
})();
