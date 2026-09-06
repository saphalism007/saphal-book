/* Shared building blocks for the screens: elements, requests, dialogs,
   the Bikram Sambat date field, the search picker and the calculator. */

var UI = (function () {
  "use strict";

  var lang = localStorage.getItem("cb_lang") || "en";

  function setLang(value) {
    lang = value;
    localStorage.setItem("cb_lang", value);
  }
  function getLang() { return lang; }

  /* Elements */

  function el(tag, attrs, children) {
    var parts = tag.split(".");
    var node = document.createElement(parts[0] || "div");
    if (parts.length > 1) { node.className = parts.slice(1).join(" "); }
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined || value === false) { return; }
        if (key === "class") { node.className = node.className ? node.className + " " + value : value; }
        else if (key === "text") { node.textContent = value; }
        // There is deliberately no way to hand this function a piece of markup.
        // Every screen in here is built out of names, narrations and item
        // descriptions that somebody typed, and if any of that were ever set as
        // markup rather than as text, a party named after a script tag would run
        // it. Text is the only door, so there is nothing to get wrong later.
        else if (key === "html") {
          throw new Error("el() will not set markup. Pass text, or build nodes.");
        }
        else if (key === "value") { node.value = value; }
        else if (key.slice(0, 2) === "on" && typeof value === "function") {
          node.addEventListener(key.slice(2).toLowerCase(), value);
        } else if (key === "dataset") {
          Object.keys(value).forEach(function (k) { node.dataset[k] = value[k]; });
        } else { node.setAttribute(key, value === true ? "" : value); }
      });
    }
    (children || []).forEach(function (child) {
      if (child === null || child === undefined || child === false) { return; }
      node.appendChild(typeof child === "string" || typeof child === "number"
        ? document.createTextNode(String(child)) : child);
    });
    return node;
  }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } return node; }
  function qs(selector, scope) { return (scope || document).querySelector(selector); }
  function qsa(selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  }

  /* Requests */

  /* Anything written to the books should reach the other devices shortly
     afterwards, without anybody pressing a button. Catching it here, at the one
     place every write passes through, is the only way to be sure nothing is
     missed. Reading, and the syncing itself, must not count, or it would chase
     its own tail. */

  var QUIET = /\/api\/(cloud|reports|dashboard|next-number|gate-help|network|lookups|companies\/list)/;

  function wroteSomething(path, method) {
    if (method !== "POST" && method !== "PUT" && method !== "DELETE") { return; }
    if (QUIET.test(path)) { return; }
    if (window.App && App.Sync && App.Sync.touched) { App.Sync.touched(); }
  }

  /* Saying that something is happening, in the one place it cannot say so itself.

     In the browser version the accounting engine runs on the same thread as the
     screen, so while it is working the page really is stopped: a tap does
     nothing, and nothing moves, including anything that spins.

     The first attempt at this waited two animation frames before every single
     call so the bar was certain to be on the glass first. That was wrong twice
     over. It put thirty milliseconds on the front of every call including the
     ones that take half of one, which is what turned moving between screens
     into a crawl. And requestAnimationFrame does not fire at all in a tab that
     is not on screen, so a call made by a background tab waited for ever.

     So: no animation frames, and no bar unless it is earned. How long each
     address took last time is remembered, and only the ones that were actually
     slow get a bar and a yield to paint it. A screen made of quick calls now
     costs nothing at all. */

  var SLOW_MS = 220;

  /* Addresses that go to somebody else's server and are therefore slow the
     first time as well as every time. Measured, not guessed: a backup taken in
     the browser version uploads to Google Drive over a blocking request, and
     that took just under six seconds. Waiting for it to be slow once before
     admitting it is slow leaves the first press looking like a dead button. */
  var lastTook = {
    "/api/backup/create": 6000,
    "/api/backup/restore": 6000,
    "/api/backup/check-google": 900,
    "/api/cloud/auto": 900,
    "/api/cloud/send": 3000,
    "/api/cloud/bring": 3000,
    "/api/cloud/compare": 3000,
    "/api/cloud/fetch-waiting": 3000,
    "/api/cloud/sign-in": 900,
    "/api/cloud/sign-up": 900
  };
  var busyDepth = 0;
  var busyBar = null;

  function showBusy(on) {
    busyDepth = Math.max(0, busyDepth + (on ? 1 : -1));
    if (busyDepth && !busyBar) {
      busyBar = el("div.busy", { text: "Working" });
      document.body.appendChild(busyBar);
    } else if (!busyDepth && busyBar) {
      if (busyBar.parentNode) { busyBar.parentNode.removeChild(busyBar); }
      busyBar = null;
    }
  }

  // A yield the browser honours whether or not the tab is on screen.
  function yieldOnce() {
    return new Promise(function (resolve) { setTimeout(resolve, 0); });
  }

  function api(path, options) {
    options = options || {};

    // Inside a browser there is no server to ask. The same handlers are loaded
    // into the page through Pyodide, so the call goes straight to Python.
    if (window.CHARTERED_BOOK_WEB && window.CB) {
      var method = options.method || (options.body ? "POST" : "GET");
      var address = path;
      var extra = null;
      var mark = path.indexOf("?");
      if (mark >= 0) {
        address = path.slice(0, mark);
        extra = {};
        path.slice(mark + 1).split("&").forEach(function (pair) {
          var bits = pair.split("=");
          if (bits[0]) { extra[decodeURIComponent(bits[0])] = decodeURIComponent(bits[1] || ""); }
        });
      }
      var query = options.query || extra;
      if (options.query && extra) {
        query = {};
        Object.keys(extra).forEach(function (k) { query[k] = extra[k]; });
        Object.keys(options.query).forEach(function (k) { query[k] = options.query[k]; });
      }
      var slow = (lastTook[address] || 0) > SLOW_MS;
      var began = 0;

      function go() {
        began = (window.performance ? performance.now() : Date.now());
        return window.CB.call(method, address, query, options.body);
      }
      function done() {
        var took = (window.performance ? performance.now() : Date.now()) - began;
        lastTook[address] = took;
        if (slow) { showBusy(false); }
      }

      if (!slow) {
        return go().then(function (answer) {
          done();
          wroteSomething(address, method);
          return answer;
        }, function (error) { done(); throw error; });
      }

      showBusy(true);
      return yieldOnce().then(go).then(function (answer) {
        done();
        wroteSomething(address, method);
        return answer;
      }, function (error) { done(); throw error; });
    }

    var config = {
      method: options.method || (options.body ? "POST" : "GET"),
      headers: { "X-Chartered-Book": "1" },
      credentials: "same-origin"
    };
    if (options.body) {
      config.headers["Content-Type"] = "application/json";
      config.body = JSON.stringify(options.body);
    }
    var url = path;
    if (options.query) {
      var pairs = [];
      Object.keys(options.query).forEach(function (key) {
        var value = options.query[key];
        if (value !== null && value !== undefined && value !== "") {
          pairs.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
        }
      });
      if (pairs.length) { url += (url.indexOf("?") === -1 ? "?" : "&") + pairs.join("&"); }
    }
    return fetch(url, config).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var error = new Error(data.error || "Something went wrong.");
          error.status = response.status;
          throw error;
        }
        wroteSomething(path, config.method);
        return data;
      });
    });
  }

  /* Messages */

  var flashTimer = null;
  function flash(message, kind) {
    var node = qs("#flash");
    node.className = "flash " + (kind || "good");
    node.textContent = message;
    node.classList.remove("hidden");
    if (flashTimer) { clearTimeout(flashTimer); }
    flashTimer = setTimeout(function () { node.classList.add("hidden"); },
      kind === "bad" ? 8000 : 4000);
  }

  /* Modal.

     Dialogs stack. Adding an item from inside a purchase bill, and adding a
     unit from inside that, has to leave the bill exactly as it was when both
     are closed, so each dialog is kept and put back rather than thrown away. */

  var modalStack = [];

  /* Copying text to the clipboard.

     The browser only hands over the modern clipboard on a secure page, and the
     books are served over plain http on the wifi, so on the very screen where
     an address most needs copying the modern way is switched off. The old way
     still works everywhere, so it is tried when the new one is missing or
     refused. */

  function copyText(text, button) {
    function done(ok) {
      if (button) {
        var was = button.textContent;
        button.textContent = ok ? "Copied" : "Press and hold to copy";
        setTimeout(function () { button.textContent = was; }, ok ? 1400 : 2600);
      }
      if (!ok) { flash("Could not copy on its own. Select the address and copy it.", "warn"); }
    }
    function oldWay() {
      var box = document.createElement("textarea");
      box.value = text;
      box.setAttribute("readonly", "");
      box.style.position = "fixed";
      box.style.top = "-1000px";
      document.body.appendChild(box);
      box.select();
      box.setSelectionRange(0, text.length);
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (error) { ok = false; }
      document.body.removeChild(box);
      done(ok);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, oldWay);
      return;
    }
    oldWay();
  }

  function modal(title, bodyNode, buttons, options) {
    modalStack.push({ title: title, body: bodyNode, buttons: buttons || [], options: options || {} });
    return renderModal();
  }

  function renderModal() {
    var wrap = qs("#modal");
    if (!modalStack.length) {
      wrap.classList.add("hidden");
      document.body.classList.remove("has-modal");
      clear(qs("#modal-body"));
      return wrap;
    }
    var top = modalStack[modalStack.length - 1];
    var card = qs("#modal-card");
    card.className = "modal-card"
      + (top.options.wide ? " wide" : "")
      + (top.options.slim ? " slim" : "");
    qs("#modal-title").textContent = top.title;
    clear(qs("#modal-body")).appendChild(top.body);
    var foot = clear(qs("#modal-foot"));
    top.buttons.forEach(function (spec) {
      foot.appendChild(el("button." + (spec.kind || "secondary"), {
        text: spec.label,
        onclick: function (event) {
          var button = event.currentTarget;
          if (!spec.action) { closeModal(); return; }
          var outcome;
          try {
            outcome = spec.action();
          } catch (error) {
            flash(error.message || "That did not work.", "bad");
            return;
          }
          if (outcome && typeof outcome.then === "function") {
            button.disabled = true;
            outcome.then(function (keep) {
              button.disabled = false;
              if (keep !== false) { closeModal(); }
            }).catch(function (error) {
              button.disabled = false;
              if (error) { error.handled = true; }
              flash((error && error.message) || "That did not work.", "bad");
            });
          } else if (outcome !== false) { closeModal(); }
        }
      }));
    });
    wrap.classList.remove("hidden");
    // Printing a voucher printed the screen behind it as well, which is why a
    // one page bill came out of the printer as two. The body carries a mark
    // while a panel is open and the print stylesheet hides everything else.
    document.body.classList.add("has-modal");
    var focusTarget = card.querySelector("input:not([readonly]), select, textarea");
    if (focusTarget) { setTimeout(function () { focusTarget.focus(); }, 40); }
    return wrap;
  }

  function closeModal() {
    modalStack.pop();
    renderModal();
  }

  function closeAllModals() {
    modalStack = [];
    renderModal();
  }

  function modalDepth() { return modalStack.length; }

  function confirmAction(title, message, onYes, yesLabel) {
    var body = el("div", {}, [el("p", { text: message })]);
    modal(title, body, [
      { label: "Cancel" },
      { label: yesLabel || "Yes, go ahead", kind: "danger", action: onYes }
    ]);
  }

  function promptText(title, label, onSubmit, options) {
    options = options || {};
    var input = el("input", { type: "text", value: options.value || "" });
    var body = el("div", {}, [
      el("div.field", {}, [el("label", { text: label }), input]),
      options.hint ? el("p.card-note", { text: options.hint }) : null
    ]);
    modal(title, body, [
      { label: "Cancel" },
      { label: options.submitLabel || "Save", kind: "primary",
        action: function () { return onSubmit(input.value.trim()); } }
    ]);
    return input;
  }

  /* Search picker, used for choosing a ledger, party or item by typing */

  var pickerState = { input: null, items: [], index: 0, onPick: null, options: {} };

  /*
     options.createLabel  wording for the row at the foot of the list
     options.onCreate     called with whatever has been typed, so a new item,
                          party or ledger can be added without leaving the
                          voucher. Whatever it hands back is treated as if it
                          had been picked from the list.
  */
  function attachPicker(input, loader, onPick, formatter, options) {
    options = options || {};
    input.setAttribute("autocomplete", "off");
    var timer = null;

    function run() {
      var term = input.value.trim();
      Promise.resolve(loader(term)).then(function (list) {
        showPicker(input, list, onPick, formatter, options);
      }).catch(function () {
        showPicker(input, [], onPick, formatter, options);
      });
    }

    input.addEventListener("focus", run);
    input.addEventListener("input", function () {
      if (timer) { clearTimeout(timer); }
      timer = setTimeout(run, 120);
    });
    input.addEventListener("keydown", function (event) {
      var box = qs("#picker");
      if (box.classList.contains("hidden")) {
        if (event.key === "ArrowDown") { run(); }
        return;
      }
      if (event.key === "ArrowDown") { move(1); event.preventDefault(); }
      else if (event.key === "ArrowUp") { move(-1); event.preventDefault(); }
      else if (event.key === "Enter") {
        event.preventDefault();
        if (pickerState.items.length) {
          choose(pickerState.items[pickerState.index]);
        } else if (options.onCreate && input.value.trim()) {
          startCreate(input.value.trim());
        }
      } else if (event.key === "Escape") { hidePicker(); }
    });
    input.addEventListener("blur", function () { setTimeout(hidePicker, 160); });
    return { refresh: run };
  }

  function showPicker(input, list, onPick, formatter, options) {
    options = options || {};
    var box = clear(qs("#picker"));
    box.classList.remove("calendar-host");
    pickerState = { input: input, items: list || [], index: 0, onPick: onPick, options: options };
    if (!list || !list.length) {
      box.appendChild(el("div.picker-empty", {
        text: options.onCreate
          ? "Nothing found by that name."
          : "Nothing found. Try a shorter search."
      }));
    } else {
      list.slice(0, 60).forEach(function (item, index) {
        var parts = formatter ? formatter(item) : { main: item.name, side: item.code || "" };
        var row = el("div.picker-item" + (index === 0 ? ".active" : ""), {
          dataset: { index: index },
          onmousedown: function (event) { event.preventDefault(); choose(item); }
        }, [
          el("span", { text: parts.main }),
          parts.side ? el("span.muted", { text: parts.side }) : null
        ]);
        box.appendChild(row);
      });
    }
    if (options.onCreate) {
      var typed = input.value.trim();
      box.appendChild(el("div.picker-add", {
        onmousedown: function (event) { event.preventDefault(); startCreate(typed); }
      }, [
        el("span.plus", { text: "+" }),
        el("span", { text: typed
          ? (options.createLabel || "Add") + ' "' + typed + '"'
          : (options.createLabel || "Add a new one") })
      ]));
    }
    place(box, input);
    box.classList.remove("hidden");
  }

  function place(box, anchor) {
    var rect = anchor.getBoundingClientRect();
    box.style.minWidth = Math.max(rect.width, 250) + "px";
    box.style.left = "0px";
    box.style.top = "0px";
    var width = box.offsetWidth;
    var height = box.offsetHeight;
    var left = rect.left + window.scrollX;
    if (left + width > window.scrollX + document.documentElement.clientWidth - 8) {
      left = Math.max(window.scrollX + 8,
                      window.scrollX + document.documentElement.clientWidth - width - 8);
    }
    var top = rect.bottom + window.scrollY + 3;
    var roomBelow = window.innerHeight - rect.bottom;
    if (roomBelow < height + 12 && rect.top > roomBelow) {
      top = rect.top + window.scrollY - height - 3;
    }
    box.style.left = left + "px";
    box.style.top = top + "px";
  }

  function startCreate(typed) {
    var options = pickerState.options || {};
    var input = pickerState.input;
    var onPick = pickerState.onPick;
    hidePicker();
    if (!options.onCreate) { return; }
    Promise.resolve(options.onCreate(typed, function (made) {
      if (made && onPick) { onPick(made); }
    })).catch(function (error) { flash(error.message, "bad"); });
    if (input) { setTimeout(function () { input.blur(); }, 0); }
  }

  function move(step) {
    var box = qs("#picker");
    var rows = qsa(".picker-item", box);
    if (!rows.length) { return; }
    if (!rows.length) { return; }
    rows[pickerState.index].classList.remove("active");
    pickerState.index = (pickerState.index + step + rows.length) % rows.length;
    rows[pickerState.index].classList.add("active");
    rows[pickerState.index].scrollIntoView({ block: "nearest" });
  }

  function choose(item) {
    hidePicker();
    if (pickerState.onPick) { pickerState.onPick(item); }
  }

  function hidePicker() { qs("#picker").classList.add("hidden"); }

  /* Bikram Sambat date field.
     The person types the BS date. The AD date is shown beside it and is what
     gets saved. Typing an AD date works too, the field notices the format. */

  function dateField(value, onChange, options) {
    options = options || {};
    var iso = value || NP.todayIso();
    var bsInput = el("input", { type: "text", class: "bs-date", value: NP.formatBs(NP.adToBs(iso), "numeric") });
    var adShadow = el("input", { type: "text", class: "ad-shadow", value: iso, readonly: true, tabindex: "-1" });
    var wrap = el("div.date-pair", {}, [bsInput, adShadow]);
    wrap.dataset.iso = iso;

    function apply(newIso, silent) {
      if (!newIso) { return; }
      wrap.dataset.iso = newIso;
      adShadow.value = newIso;
      bsInput.value = NP.formatBs(NP.adToBs(newIso), "numeric");
      if (!silent && onChange) { onChange(newIso); }
    }

    bsInput.addEventListener("change", function () {
      var text = bsInput.value.trim();
      if (/^\d{4}-\d{2}-\d{2}$/.test(text) && +text.slice(0, 4) > 1900 && +text.slice(0, 4) < 2200) {
        apply(text);  // an AD date was typed
        return;
      }
      var bs = NP.parseBs(text);
      if (!bs) {
        flash("That is not a date in the Nepali calendar. Try 2083-05-17.", "bad");
        apply(wrap.dataset.iso, true);
        return;
      }
      apply(NP.bsToAd(bs.year, bs.month, bs.day));
    });

    bsInput.addEventListener("keydown", function (event) {
      var step = 0;
      if (event.key === "+" || event.key === "=") { step = 1; }
      else if (event.key === "-" || event.key === "_") { step = -1; }
      else if (event.key === "PageUp") { step = 7; }
      else if (event.key === "PageDown") { step = -7; }
      if (step) {
        event.preventDefault();
        apply(NP.addDays(wrap.dataset.iso, step));
      }
      if (event.key === "F4" || (event.altKey && event.key === "ArrowDown")) {
        event.preventDefault();
        openCalendar(bsInput, wrap.dataset.iso, apply);
      }
    });
    bsInput.addEventListener("dblclick", function () {
      openCalendar(bsInput, wrap.dataset.iso, apply);
    });

    wrap.getIso = function () { return wrap.dataset.iso; };
    wrap.setIso = function (newIso) { apply(newIso, true); };
    wrap.input = bsInput;
    return wrap;
  }

  function openCalendar(anchor, iso, onPick) {
    var current = NP.adToBs(iso) || NP.adToBs(NP.todayIso());
    var view = { year: current.year, month: current.month };

    function draw() {
      var box = clear(qs("#picker"));
      box.classList.add("calendar-host");
      var head = el("div.calendar-head", {}, [
        el("button.icon-button", { text: "‹", onmousedown: function (e) { e.preventDefault(); shift(-1); } }),
        el("strong", { text: (getLang() === "np" ? NP.MONTHS_NP[view.month - 1] : NP.MONTHS_EN[view.month - 1]) + " " + view.year }),
        el("button.icon-button", { text: "›", onmousedown: function (e) { e.preventDefault(); shift(1); } })
      ]);
      var grid = el("div.calendar-grid");
      var names = NP.DOW_EN;
      names.forEach(function (name) { grid.appendChild(el("div.dow", { text: name })); });
      var firstAd = NP.bsToAd(view.year, view.month, 1);
      if (!firstAd) { return; }
      var lead = NP.weekdayIndex(firstAd);
      for (var i = 0; i < lead; i++) { grid.appendChild(el("div")); }
      var days = NP.daysInMonth(view.year, view.month);
      var todayIso = NP.todayIso();
      for (var d = 1; d <= days; d++) {
        (function (day) {
          var dayIso = NP.bsToAd(view.year, view.month, day);
          var classes = "div.day";
          if (dayIso === todayIso) { classes += ".today"; }
          if (dayIso === iso) { classes += ".chosen"; }
          if (NP.weekdayIndex(dayIso) === 6) { classes += ".holiday"; }
          grid.appendChild(el(classes, {
            text: day,
            onmousedown: function (event) { event.preventDefault(); hidePicker(); onPick(dayIso); }
          }));
        }(d));
      }
      var footer = el("div", { style: "text-align:center;margin-top:.4rem" }, [
        el("button.link-button", {
          text: "Today", onmousedown: function (e) { e.preventDefault(); hidePicker(); onPick(NP.todayIso()); }
        })
      ]);
      box.appendChild(el("div.calendar", {}, [head, grid, footer]));
      var rect = anchor.getBoundingClientRect();
      box.style.left = (rect.left + window.scrollX) + "px";
      box.style.top = (rect.bottom + window.scrollY + 2) + "px";
      box.style.minWidth = "auto";
      box.classList.remove("hidden");
    }

    function shift(step) {
      view.month += step;
      if (view.month > 12) { view.month = 1; view.year++; }
      if (view.month < 1) { view.month = 12; view.year--; }
      if (!NP.daysInMonth(view.year, view.month)) { view.month -= step; return; }
      draw();
    }

    draw();
  }

  /* Amount and quantity inputs that accept an expression such as 12*450 */

  function amountInput(value, options) {
    options = options || {};
    var input = el("input", {
      type: "text", class: "amount", inputmode: "decimal",
      value: value === undefined || value === null || value === "" ? "" : value
    });
    input.addEventListener("focus", function () { input.select(); });
    input.addEventListener("blur", function () {
      var text = input.value.trim();
      if (!text) { return; }
      var before = input.value;
      // 12*450 and 1200+300 are worked out when the box is left, because that
      // is how a shopkeeper adds up a delivery.
      if (/[+\-*/()]/.test(text) && !/^-?[\d.,]+$/.test(text)) {
        var result = evaluate(text);
        if (result !== null) { input.value = trimNumber(result); }
      }
      // Only tell anyone if the value actually moved. Firing on every blur
      // makes a screen rebuild itself under the cursor.
      if (options.onChange && input.value !== before) { options.onChange(input.value); }
    });
    if (options.onChange) {
      input.addEventListener("input", function () { options.onChange(input.value); });
    }
    return input;
  }

  function trimNumber(value) {
    return String(Math.round(value * 1000) / 1000);
  }

  function evaluate(expression) {
    var cleaned = NP.fromDevanagari(String(expression)).replace(/[,\s]/g, "")
      .replace(/[×x]/g, "*").replace(/[÷]/g, "/").replace(/%/g, "/100");
    if (!/^[0-9+\-*/().]+$/.test(cleaned) || cleaned === "") { return null; }
    try {
      /* Only digits and arithmetic symbols reach this point, checked above. */
      var result = Function('"use strict";return (' + cleaned + ")")();
      return typeof result === "number" && isFinite(result) ? result : null;
    } catch (error) { return null; }
  }

  /* Calculator */

  var calc = { display: "0", expression: "", tape: [] };

  function setupCalculator() {
    var keys = [
      ["C", "clear"], ["←", "back"], ["%", "op"], ["/", "op"],
      ["7", "n"], ["8", "n"], ["9", "n"], ["*", "op"],
      ["4", "n"], ["5", "n"], ["6", "n"], ["-", "op"],
      ["1", "n"], ["2", "n"], ["3", "n"], ["+", "op"],
      ["0", "n"], [".", "n"], ["00", "n"], ["=", "eq"]
    ];
    var pad = clear(qs("#calc-keys"));
    keys.forEach(function (spec) {
      pad.appendChild(el("button" + (spec[1] === "op" ? ".op" : spec[1] === "eq" ? ".eq" : ""), {
        text: spec[0], onclick: function () { pressKey(spec[0]); }
      }));
    });
    qs("#calc-close").addEventListener("click", toggleCalculator);
    qs("#calc-use").addEventListener("click", useCalculatorResult);
    watchAmountFields();
    qs("#calc-display").addEventListener("keydown", function (event) {
      if (event.key === "Enter") { event.preventDefault(); pressKey("="); }
    });
    qs("#calc-words").addEventListener("click", function () {
      api("/api/amount-in-words", { query: { amount: qs("#calc-display").value } })
        .then(function (data) {
          modal("Amount in words", el("div", {}, [
            el("p", { text: data.formatted }),
            el("p", { text: data.en }),
            el("p", { text: data.np })
          ]), [{ label: "Close" }]);
        }).catch(function (error) { flash(error.message, "bad"); });
    });
    qs("#calc-vat").addEventListener("click", function () {
      var paisa = NP.toPaisa(qs("#calc-display").value);
      var vat = NP.applyRate(paisa, 1300);
      pushTape("Add 13% VAT", NP.formatMoney(paisa + vat));
      setDisplay((paisa + vat) / 100);
    });
    qs("#calc-vat-out").addEventListener("click", function () {
      var gross = NP.toPaisa(qs("#calc-display").value);
      var net = NP.roundHalfUp(gross * 10000, 11300);
      pushTape("Remove 13% VAT", NP.formatMoney(net) + " plus " + NP.formatMoney(gross - net));
      setDisplay(net / 100);
    });
  }

  function setDisplay(value) {
    qs("#calc-display").value = trimNumber(value);
  }

  function pressKey(key) {
    var display = qs("#calc-display");
    if (key === "C") { display.value = "0"; qs("#calc-expression").textContent = ""; return; }
    if (key === "←") { display.value = display.value.slice(0, -1) || "0"; return; }
    if (key === "=") {
      var result = evaluate(display.value);
      if (result === null) { flash("That expression could not be worked out.", "bad"); return; }
      pushTape(display.value, NP.formatMoney(Math.round(result * 100)));
      qs("#calc-expression").textContent = display.value + " =";
      setDisplay(result);
      return;
    }
    if (display.value === "0" && /[0-9.]/.test(key)) { display.value = ""; }
    display.value += key;
  }

  function pushTape(expression, result) {
    calc.tape.unshift({ expression: expression, result: result });
    calc.tape = calc.tape.slice(0, 40);
    var tape = clear(qs("#calc-tape"));
    calc.tape.forEach(function (row) {
      tape.appendChild(el("div", {}, [
        el("span", { text: row.expression.slice(0, 22) }),
        el("span", { text: row.result })
      ]));
    });
  }

  /* The calculator and the box you were typing in.

     A calculator you have to read a number off and type again is barely a
     calculator. Whichever amount box was last in use is remembered, so opening
     the calculator starts from what is already in it and there is one button to
     put the answer back. That is the whole of it: work the sum out where the
     money is going, not beside it. */

  var lastAmountField = null;

  function rememberAmountField(input) {
    lastAmountField = input;
  }

  function watchAmountFields() {
    document.addEventListener("focusin", function (event) {
      var node = event.target;
      if (node && node.tagName === "INPUT"
          && (node.classList.contains("amount") || node.classList.contains("num")
              || node.getAttribute("inputmode") === "decimal")) {
        lastAmountField = node;
      }
    });
  }

  function calculatorTarget() {
    // Only offer it while the box is still on the screen.
    if (lastAmountField && document.body.contains(lastAmountField)
        && !lastAmountField.disabled && !lastAmountField.readOnly) {
      return lastAmountField;
    }
    return null;
  }

  function paintCalculatorTarget() {
    var use = qs("#calc-use");
    if (!use) { return; }
    var target = calculatorTarget();
    if (!target) { use.classList.add("hidden"); return; }
    var label = target.getAttribute("data-label")
      || (target.closest(".field") && target.closest(".field").querySelector("label")
          && target.closest(".field").querySelector("label").textContent.trim())
      || "";
    use.textContent = label ? "Put it in " + label : "Put it in the box";
    use.classList.remove("hidden");
  }

  function useCalculatorResult() {
    var target = calculatorTarget();
    if (!target) { return; }
    var raw = qs("#calc-display").value;
    var worked = evaluate(raw);
    var value = worked === null ? raw : trimNumber(worked);
    target.value = value;
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
    toggleCalculator();
    target.focus();
    if (target.select) { target.select(); }
  }

  function toggleCalculator() {
    var box = qs("#calculator");
    var opening = box.classList.contains("hidden");
    box.classList.toggle("hidden");
    if (!opening) { return; }
    paintCalculatorTarget();
    var target = calculatorTarget();
    var display = qs("#calc-display");
    // Start from whatever is already in the box, so a correction is one key
    // rather than typing the whole figure again.
    if (target && (target.value || "").trim()) {
      display.value = target.value.trim();
    }
    display.focus();
    display.select();
  }

  /* Appearance */

  function getTheme() { return localStorage.getItem("cb_theme") || "system"; }

  function applyTheme(choice) {
    var value = choice || getTheme();
    var dark = value === "dark" || (value === "system"
      && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = qs('meta[name="theme-color"]');
    if (meta) { meta.setAttribute("content", dark ? "#0f141a" : "#1d3557"); }
  }

  function setTheme(choice) {
    localStorage.setItem("cb_theme", choice);
    applyTheme(choice);
  }

  function watchSystemTheme() {
    if (!window.matchMedia) { return; }
    var query = window.matchMedia("(prefers-color-scheme: dark)");
    var handler = function () { if (getTheme() === "system") { applyTheme("system"); } };
    if (query.addEventListener) { query.addEventListener("change", handler); }
    else if (query.addListener) { query.addListener(handler); }
  }

  /* Guards.

     A book keeping screen that goes blank in the middle of an invoice is worse
     than one that admits something went wrong. Anything unexpected is caught,
     shown plainly, and the rest of the screen keeps working. */

  var recentErrors = [];

  function noteError(where, detail) {
    recentErrors.unshift({ at: new Date().toISOString(), where: where, detail: String(detail) });
    recentErrors = recentErrors.slice(0, 25);
    try { console.error("[Saphal Book] " + where, detail); } catch (ignored) { /* no console */ }
  }

  function installGuards() {
    window.addEventListener("error", function (event) {
      if (event && event.target && event.target !== window && event.target.tagName) {
        noteError("resource", event.target.src || event.target.href || event.target.tagName);
        return;
      }
      noteError("script", (event && event.message) || "unknown");
      flash("Something on this screen did not work. The books are untouched. "
            + "Move to another screen and back, and it usually clears.", "bad");
    });
    window.addEventListener("unhandledrejection", function (event) {
      var reason = (event && event.reason) || {};
      noteError("request", reason.message || reason);
      if (reason && reason.handled) { return; }
      flash(reason.message || "That did not go through. Nothing was saved.", "bad");
    });
  }

  function errorLog() { return recentErrors.slice(); }

  /* Small formatting helpers used by every screen */

  function rs(paisa, options) {
    options = options || {};
    options.lang = options.lang || (lang === "np" ? "np" : "en");
    return NP.formatMoney(paisa, options);
  }

  function money(paisa, options) {
    return el("span.num", { text: rs(paisa, options) });
  }

  function bs(iso, style) {
    return NP.formatBs(NP.adToBs(iso), style || "numeric", lang === "np" ? "np" : "en");
  }

  function both(iso) {
    return bs(iso, "short") + "  (" + iso + ")";
  }

  function field(labelText, control, hint) {
    return el("div.field", {}, [
      el("label", { text: labelText }),
      control,
      hint ? el("div.hint", { text: hint }) : null
    ]);
  }

  function select(options, value, onChange, attrs) {
    var node = el("select", attrs || {});
    options.forEach(function (option) {
      node.appendChild(el("option", {
        value: option.value,
        text: option.label,
        selected: String(option.value) === String(value)
      }));
    });
    if (onChange) { node.addEventListener("change", function () { onChange(node.value); }); }
    return node;
  }

  function table(headers, bodyRows, footRows, options) {
    options = options || {};
    var head = el("thead", {}, [el("tr", {}, headers.map(function (h) {
      return el("th" + (h.num ? ".num" : h.mid ? ".mid" : ""), {
        text: h.label === undefined ? h : h.label,
        style: h.width ? "width:" + h.width : null
      });
    }))]);
    var body = el("tbody", {}, bodyRows);
    var parts = [head, body];
    if (footRows && footRows.length) { parts.push(el("tfoot", {}, footRows)); }
    var wrap = el("div.table-wrap" + (options.tall ? ".tall" : ""), {}, [el("table", {}, parts)]);
    if (!bodyRows.length) {
      return el("div", {}, [wrap, el("div.empty", { text: options.emptyText || "Nothing to show yet." })]);
    }
    return wrap;
  }

  /* Exporting what is on the screen to Excel.

     The table that is being looked at is read straight out of the page, so
     every screen gets an export without every screen having to be taught how.
     Amounts go across as numbers rather than as the text "1,23,456.78", which
     is what lets them add up once they are in Excel.

     The workbook comes back as text and is turned into a file here, because
     when the whole engine is running inside the browser there is no web server
     to hand a download over. */

  function tableToSheet(table, name, titleLines) {
    var widths = [];
    var columns = [];
    var rows = [];

    function cellsOf(tr) {
      return Array.prototype.slice.call(tr.querySelectorAll("td, th"));
    }
    function readNumber(node) {
      var raw = (node.getAttribute("data-value") || node.textContent || "").trim();
      if (!raw) { return null; }
      var cleaned = raw.replace(/,/g, "").replace(/\u2212/g, "-");
      var bracketed = /^\((.*)\)$/.exec(cleaned);
      if (bracketed) { cleaned = "-" + bracketed[1]; }
      if (!/^-?\d*\.?\d+$/.test(cleaned)) { return null; }
      return parseFloat(cleaned);
    }

    var headRow = table.querySelector("thead tr:last-child");
    if (headRow) {
      cellsOf(headRow).forEach(function (cell) {
        columns.push(cell.textContent.trim());
        widths.push(Math.max(10, Math.min(46, cell.textContent.trim().length + 4)));
      });
    }

    ["tbody", "tfoot"].forEach(function (part) {
      qsa(part + " tr", table).forEach(function (tr) {
        if (tr.classList.contains("no-print")) { return; }
        var total = tr.classList.contains("total-row") || tr.classList.contains("grand-row")
                    || part === "tfoot";
        var out = [];
        cellsOf(tr).forEach(function (cell, index) {
          var text = cell.textContent.trim().replace(/\s+/g, " ");
          var number = cell.classList.contains("num") ? readNumber(cell) : null;
          if (number !== null) {
            out.push({ v: number, s: total ? "total" : "money" });
          } else {
            out.push({ v: text, s: total ? "head" : null });
          }
          var need = Math.max(10, Math.min(46, text.length + 4));
          if (widths[index] === undefined || widths[index] < need) { widths[index] = need; }
        });
        rows.push(out);
      });
    });

    return { name: name, columns: columns, rows: rows, widths: widths,
             title: titleLines || [] };
  }

  function download(filename, base64, mimeType) {
    var binary = atob(base64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i += 1) { bytes[i] = binary.charCodeAt(i); }
    var blob = new Blob([bytes], { type: mimeType
      || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function exportToExcel(scope, filename, titleLines) {
    var tables = scope
      ? (scope.tagName === "TABLE" ? [scope] : qsa("table", scope))
      : qsa("#page table");
    tables = tables.filter(function (t) { return t.querySelector("tbody tr"); });
    if (!tables.length) {
      flash("There is nothing on this screen to export yet.", "warn");
      return;
    }
    var sheets = tables.map(function (table, index) {
      var heading = table.getAttribute("data-sheet")
        || (tables.length > 1 ? "Sheet " + (index + 1) : (filename || "Sheet"));
      return tableToSheet(table, heading, index === 0 ? titleLines : []);
    });
    flash("Building the workbook.", "good");
    return api("/api/export/xlsx", { body: { filename: filename || "Saphal Book",
                                             sheets: sheets } })
      .then(function (result) {
        download(result.filename, result.content);
        flash("Saved " + result.filename + " to your downloads.", "good");
      })
      .catch(function (error) { flash(error.message || "The export did not work.", "bad"); });
  }

  function exportButton(scope, filename, titleLines) {
    return el("button.secondary.no-print", { text: "Export to Excel", onclick: function () {
      // With nothing said, take the name and the heading off the screen
      // itself, so a new screen gets a sensible file name for free.
      var title = qs("#page-title");
      var head = qs("#page .report-head");
      var lines = titleLines;
      if (!lines && head) {
        lines = qsa(".company, .title, .period", head)
          .map(function (node) { return node.textContent.trim(); })
          .filter(Boolean);
      }
      exportToExcel(typeof scope === "function" ? scope() : scope,
                    filename || (title ? title.textContent.trim() : "Saphal Book"),
                    lines || []);
    } });
  }

  function printPage() { window.print(); }

  return {
    copyText: copyText, exportToExcel: exportToExcel, downloadFile: download,
    exportButton: exportButton,
    el: el, clear: clear, qs: qs, qsa: qsa, api: api, flash: flash,
    modal: modal, closeModal: closeModal, closeAllModals: closeAllModals,
    modalDepth: modalDepth, confirmAction: confirmAction, promptText: promptText,
    attachPicker: attachPicker, hidePicker: hidePicker, placePicker: place,
    dateField: dateField, amountInput: amountInput, evaluate: evaluate,
    setupCalculator: setupCalculator, toggleCalculator: toggleCalculator,
    rememberAmountField: rememberAmountField,
    showBusy: showBusy, rs: rs, money: money, bs: bs, both: both, field: field, select: select, table: table,
    setLang: setLang, getLang: getLang, printPage: printPage, trimNumber: trimNumber,
    getTheme: getTheme, setTheme: setTheme, applyTheme: applyTheme,
    watchSystemTheme: watchSystemTheme, installGuards: installGuards, errorLog: errorLog,
    noteError: noteError
  };
}());
