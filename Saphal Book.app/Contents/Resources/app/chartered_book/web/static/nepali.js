/* Bikram Sambat and Nepali number handling in the browser.
   The month table here is generated from chartered_book/core/nepali_date.py so
   the screen and the books can never disagree about a date. Do not hand edit it. */

var NP = (function () {
  "use strict";

  var START_YEAR = 2000;
  var REFERENCE_AD = Date.UTC(1943, 3, 14);
  var DAY = 86400000;

  var MONTH_DAYS = [
  [30,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,31,32,31,31,30,29,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,30],
  [31,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,31,32,31,31,30,29,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,31,32,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,31,29,30,30,29,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,30,29,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,30],
  [31,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,31,32,31,31,30,29,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,30],
  [31,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,31,32,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,31,29,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,30,29,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,30],
  [31,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,31,32,31,31,30,29,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,30],
  [31,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [30,32,31,32,31,30,30,30,29,30,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,29,31],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  [31,32,31,32,31,30,30,30,29,29,30,31],
  [31,31,31,32,31,31,29,30,30,29,30,30],
  [31,31,32,31,31,31,30,29,30,29,30,30],
  [31,31,32,32,31,30,30,29,30,29,30,30],
  ];

  var MONTHS_EN = ["Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
                   "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"];
  var MONTHS_NP = ["बैशाख", "जेठ", "असार", "श्रावण",
                   "भाद्र", "आश्विन", "कार्तिक", "मंसिर",
                   "पुष", "माघ", "फाल्गुन", "चैत"];
  var DOW_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var DOW_NP = ["आइत", "सोम", "मङ्गल", "बुध", "बिहि", "शुक्र", "शनि"];
  var DEVA = "०१२३४५६७८९";

  var offsets = [];
  var running = 0;
  for (var i = 0; i < MONTH_DAYS.length; i++) {
    offsets.push(running);
    for (var m = 0; m < 12; m++) { running += MONTH_DAYS[i][m]; }
  }
  var TOTAL_DAYS = running;

  function pad(value, width) {
    var text = String(value);
    while (text.length < width) { text = "0" + text; }
    return text;
  }

  function isoToUTC(iso) {
    if (!iso) { return null; }
    var parts = String(iso).split("-");
    if (parts.length !== 3) { return null; }
    var stamp = Date.UTC(+parts[0], +parts[1] - 1, +parts[2]);
    return isNaN(stamp) ? null : stamp;
  }

  function utcToIso(stamp) {
    var d = new Date(stamp);
    return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1, 2) + "-" + pad(d.getUTCDate(), 2);
  }

  function inRange(bsYear) {
    return bsYear >= START_YEAR && bsYear < START_YEAR + MONTH_DAYS.length;
  }

  function daysInMonth(bsYear, bsMonth) {
    if (!inRange(bsYear) || bsMonth < 1 || bsMonth > 12) { return 0; }
    return MONTH_DAYS[bsYear - START_YEAR][bsMonth - 1];
  }

  function bsToAd(bsYear, bsMonth, bsDay) {
    if (!inRange(bsYear)) { return null; }
    var limit = daysInMonth(bsYear, bsMonth);
    if (bsMonth < 1 || bsMonth > 12 || bsDay < 1 || bsDay > limit) { return null; }
    var elapsed = offsets[bsYear - START_YEAR];
    for (var m = 0; m < bsMonth - 1; m++) { elapsed += MONTH_DAYS[bsYear - START_YEAR][m]; }
    elapsed += bsDay - 1;
    return utcToIso(REFERENCE_AD + elapsed * DAY);
  }

  function adToBs(iso) {
    var stamp = isoToUTC(iso);
    if (stamp === null) { return null; }
    var elapsed = Math.round((stamp - REFERENCE_AD) / DAY);
    if (elapsed < 0 || elapsed >= TOTAL_DAYS) { return null; }
    var year = 0;
    while (year + 1 < offsets.length && offsets[year + 1] <= elapsed) { year++; }
    var remaining = elapsed - offsets[year];
    var month = 0;
    while (remaining >= MONTH_DAYS[year][month]) { remaining -= MONTH_DAYS[year][month]; month++; }
    return { year: year + START_YEAR, month: month + 1, day: remaining + 1 };
  }

  function formatBs(bs, style, lang) {
    if (!bs) { return ""; }
    var names = lang === "np" ? MONTHS_NP : MONTHS_EN;
    var text;
    if (style === "long") {
      text = bs.day + " " + names[bs.month - 1] + " " + bs.year;
    } else if (style === "short") {
      text = bs.day + " " + (lang === "np" ? names[bs.month - 1] : names[bs.month - 1].slice(0, 3)) + " " + bs.year;
    } else {
      text = pad(bs.year, 4) + "-" + pad(bs.month, 2) + "-" + pad(bs.day, 2);
    }
    return lang === "np" ? toDevanagari(text) : text;
  }

  function parseBs(text) {
    if (!text) { return null; }
    var cleaned = fromDevanagari(String(text).trim()).replace(/[\/.\s]/g, "-");
    var parts = cleaned.split("-").filter(function (p) { return p !== ""; });
    if (parts.length !== 3) { return null; }
    var y = parseInt(parts[0], 10), m = parseInt(parts[1], 10), d = parseInt(parts[2], 10);
    if (isNaN(y) || isNaN(m) || isNaN(d)) { return null; }
    if (!bsToAd(y, m, d)) { return null; }
    return { year: y, month: m, day: d };
  }

  function toDevanagari(text) {
    return String(text).replace(/[0-9]/g, function (d) { return DEVA[+d]; });
  }

  function fromDevanagari(text) {
    return String(text).replace(/[०-९]/g, function (d) { return String(DEVA.indexOf(d)); });
  }

  function weekdayIndex(iso) {
    var stamp = isoToUTC(iso);
    return stamp === null ? 0 : new Date(stamp).getUTCDay();
  }

  function todayIso() {
    var now = new Date();
    return now.getFullYear() + "-" + pad(now.getMonth() + 1, 2) + "-" + pad(now.getDate(), 2);
  }

  function addDays(iso, count) {
    var stamp = isoToUTC(iso);
    return stamp === null ? null : utcToIso(stamp + count * DAY);
  }

  function fiscalYearOf(iso) {
    var bs = adToBs(iso);
    if (!bs) { return null; }
    var startYear = bs.month >= 4 ? bs.year : bs.year - 1;
    return fiscalYear(startYear);
  }

  function fiscalYear(startYear) {
    var endYear = startYear + 1;
    var lastDay = daysInMonth(endYear, 3);
    return {
      label: startYear + "/" + pad(endYear % 100, 2),
      startAd: bsToAd(startYear, 4, 1),
      endAd: bsToAd(endYear, 3, lastDay)
    };
  }

  /* Money. The browser mirrors the paisa arithmetic used in the books so a
     figure on screen always matches the figure that was saved. */

  function groupNepali(digits) {
    digits = String(digits);
    if (digits.length <= 3) { return digits; }
    var head = digits.slice(0, -3), tail = digits.slice(-3), parts = [];
    while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) { parts.unshift(head); }
    return parts.join(",") + "," + tail;
  }

  function groupWestern(digits) {
    return String(digits).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function formatMoney(paisa, options) {
    options = options || {};
    paisa = Math.round(Number(paisa) || 0);
    if (paisa === 0 && options.blankZero) { return ""; }
    var negative = paisa < 0;
    var absolute = Math.abs(paisa);
    var whole = Math.floor(absolute / 100);
    var minor = absolute % 100;
    var grouped = options.grouping === "western" ? groupWestern(whole) : groupNepali(whole);
    var body = options.decimals === 0 ? grouped : grouped + "." + pad(minor, 2);
    if (options.lang === "np") { body = toDevanagari(body); }
    if (!negative) { return body; }
    return options.negative === "bracket" ? "(" + body + ")" : "-" + body;
  }

  function toPaisa(value) {
    if (value === null || value === undefined || value === "") { return 0; }
    var text = fromDevanagari(String(value)).replace(/[,\s]/g, "")
      .replace(/Rs\.?|NPR|रु\.?/gi, "");
    if (/^\(.*\)$/.test(text)) { text = "-" + text.slice(1, -1); }
    if (text === "" || text === "-" || text === "+") { return 0; }
    if (!/^[+-]?\d*\.?\d*$/.test(text)) { return NaN; }
    var negative = text.charAt(0) === "-";
    text = text.replace(/^[+-]/, "");
    var bits = text.split(".");
    var whole = bits[0] === "" ? 0 : parseInt(bits[0], 10);
    var frac = (bits[1] || "") + "000";
    var minor = parseInt(frac.slice(0, 2), 10);
    var third = parseInt(frac.charAt(2), 10) || 0;
    var total = whole * 100 + minor + (third >= 5 ? 1 : 0);
    return negative ? -total : total;
  }

  function formatQty(units, lang) {
    units = Math.round(Number(units) || 0);
    var negative = units < 0;
    var absolute = Math.abs(units);
    var whole = Math.floor(absolute / 1000);
    var frac = pad(absolute % 1000, 3).replace(/0+$/, "");
    var text = groupNepali(whole) + (frac ? "." + frac : "");
    if (negative) { text = "-" + text; }
    return lang === "np" ? toDevanagari(text) : text;
  }

  function toQty(value) {
    if (value === null || value === undefined || value === "") { return 0; }
    var text = fromDevanagari(String(value)).replace(/[,\s]/g, "");
    if (!/^[+-]?\d*\.?\d*$/.test(text)) { return NaN; }
    var negative = text.charAt(0) === "-";
    text = text.replace(/^[+-]/, "");
    var bits = text.split(".");
    var whole = bits[0] === "" ? 0 : parseInt(bits[0], 10);
    var frac = (bits[1] || "") + "0000";
    var thousandths = parseInt(frac.slice(0, 3), 10);
    var fourth = parseInt(frac.charAt(3), 10) || 0;
    var total = whole * 1000 + thousandths + (fourth >= 5 ? 1 : 0);
    return negative ? -total : total;
  }

  function applyRate(paisa, basisPoints) {
    var product = Math.round(paisa) * Math.round(basisPoints);
    var sign = product < 0 ? -1 : 1;
    return sign * Math.floor((Math.abs(product) * 2 + 10000) / 20000);
  }

  function roundHalfUp(numerator, denominator) {
    if (!denominator) { return 0; }
    var sign = (numerator < 0) !== (denominator < 0) ? -1 : 1;
    var n = Math.abs(numerator), d = Math.abs(denominator);
    return sign * Math.floor((n * 2 + d) / (2 * d));
  }

  // The same split as money.allocate on the Python side, written the same way
  // so the totals on screen never differ by a paisa from the totals that get
  // saved. Used for spreading a discount given on the whole bill back over the
  // lines it was given on.
  function allocate(total, weights) {
    var i;
    var sum = 0;
    for (i = 0; i < weights.length; i += 1) { sum += weights[i]; }
    var shares = [];
    if (!weights.length) { return shares; }
    if (sum === 0) {
      for (i = 0; i < weights.length; i += 1) { shares.push(0); }
      shares[0] = total;
      return shares;
    }
    var raw = [];
    var placed = 0;
    for (i = 0; i < weights.length; i += 1) {
      raw.push(total * weights[i]);
      shares.push(Math.floor(raw[i] / sum));
      placed += shares[i];
    }
    var remainder = total - placed;
    var order = [];
    for (i = 0; i < weights.length; i += 1) { order.push(i); }
    order.sort(function (a, b) {
      var left = raw[a] % sum, right = raw[b] % sum;
      return left === right ? a - b : right - left;
    });
    var step = remainder >= 0 ? 1 : -1;
    var moves = Math.abs(remainder);
    for (i = 0; i < moves; i += 1) {
      shares[order[i % order.length]] += step;
    }
    return shares;
  }

  return {
    START_YEAR: START_YEAR,
    MONTHS_EN: MONTHS_EN, MONTHS_NP: MONTHS_NP, DOW_EN: DOW_EN, DOW_NP: DOW_NP,
    daysInMonth: daysInMonth, bsToAd: bsToAd, adToBs: adToBs,
    formatBs: formatBs, parseBs: parseBs, weekdayIndex: weekdayIndex,
    toDevanagari: toDevanagari, fromDevanagari: fromDevanagari,
    todayIso: todayIso, addDays: addDays, pad: pad,
    fiscalYear: fiscalYear, fiscalYearOf: fiscalYearOf,
    formatMoney: formatMoney, toPaisa: toPaisa,
    formatQty: formatQty, toQty: toQty,
    applyRate: applyRate, roundHalfUp: roundHalfUp, allocate: allocate,
    groupNepali: groupNepali
  };
}());
