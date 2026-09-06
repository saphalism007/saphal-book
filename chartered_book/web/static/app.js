/* Saphal Book, application core.
   Holds the signed in state, the menu, the router and the screens that do not
   belong to vouchers, masters or reports. */

var App = (function () {
  "use strict";

  var state = {
    user: null,
    company: null,
    companies: [],
    fiscalYear: null,
    fiscalYears: [],
    settings: {},
    permissions: {},
    lookups: null,
    today: null,
    // Books changed in two places at once, as the last automatic run found
    // them. The account screen turns these into a question with two answers.
    conflicts: [],
    route: "dashboard"
  };

  var el = UI.el, qs = UI.qs, api = UI.api;

  /* The menu is built from what the company actually does. A practice that
     sells only its time is not shown stock screens it will never open. */

  function buildMenu() {
    var company = state.company || {};
    var goods = company.has_goods === undefined ? true : !!company.has_goods;
    var services = !!company.has_services;
    var vat = !!company.vat_registered;

    var daily = [{ key: "dashboard", label: "Dashboard", accel: "F1" }];
    daily.push({ key: "sales", label: goods && !services ? "Sales invoice"
      : !goods && services ? "Fee invoice" : "Sales invoice", accel: "F5" });
    daily.push({ key: "purchase", label: goods ? "Purchase bill" : "Expense bill", accel: "F6" });
    daily.push({ key: "receipt", label: "Receipt", accel: "F7" });
    daily.push({ key: "payment", label: "Payment", accel: "F8" });
    daily.push({ key: "journal", label: "Journal", accel: "F9" });
    daily.push({ key: "contra", label: "Contra" });
    daily.push({ key: "daybook", label: "Day book" });

    var corrections = [];
    if (goods) {
      corrections.push({ key: "sales_return", label: "Sales return" });
      corrections.push({ key: "purchase_return", label: "Purchase return" });
    }
    corrections.push({ key: "credit_note", label: "Credit note" });
    corrections.push({ key: "debit_note", label: "Debit note" });
    if (goods) { corrections.push({ key: "stock_adjust", label: "Stock adjustment" }); }

    var records = [
      { key: "parties", label: "Customers and suppliers" },
      { key: "items", label: goods && services ? "Items and services"
        : goods ? "Items and stock" : "Services and fees" },
      { key: "banking", label: "Cash and bank" },
      { key: "assets", label: "Fixed assets" },
      { key: "accounts", label: "Chart of accounts" }
    ];

    var reports = [
      { key: "trial-balance", label: "Trial balance" },
      { key: "ledger", label: "Ledger" },
      { key: "groups", label: "Group summary" }
    ];
    if (goods) { reports.push({ key: "stock", label: "Stock" }); }
    if (goods) {
      reports.push({ key: "sales-by-item", label: "Sales by item" });
      reports.push({ key: "purchase-by-item", label: "Purchases by item" });
      reports.push({ key: "profitability", label: "What each item made" });
    }
    reports.push({ key: "sales-by-customer", label: "Sales by customer" });
    reports.push({ key: "purchase-by-supplier", label: "Purchases by supplier" });
    reports.push({ key: "outstanding", label: "Receivable and payable" });
    reports.push({ key: "ageing", label: "Ageing" });
    reports.push({ key: "statement", label: "Statement of account" });
    reports.push({ key: "reconcile", label: "Bank reconciliation" });
    if (vat) {
      reports.push({ key: "vat", label: "VAT return" });
      reports.push({ key: "sales-book", label: "Sales book" });
      reports.push({ key: "purchase-book", label: "Purchase book" });
    }

    var statements = [
      { key: "statements", label: "Financial statements" },
      { key: "profit-loss", label: "Profit and loss, quick" },
      { key: "balance-sheet", label: "Balance sheet, quick" },
      { key: "income-tax", label: "Income tax" }
    ];

    var auditTools = [
      { key: "audit-tools", label: "Red flags and review" },
      { key: "reference", label: "Law and standards" },
      { key: "audit", label: "Audit trail" }
    ];

    records.push({ key: "recurring", label: "Repeating entries" });

    var yearEnd = [{ key: "period-end", label: goods ? "Closing stock and year end" : "Year end" }];

    return [
      { title: "Daily work", items: daily },
      { title: "Corrections", items: corrections },
      { title: "Records", items: records },
      { title: "Reports", items: reports },
      { title: "Financial statements", items: statements },
      { title: "Audit", items: auditTools },
      { title: "Year end", items: yearEnd },
      { title: "Setup", items: [
        { key: "company", label: "Company" },
        { key: "users", label: "Users" },
        { key: "devices", label: "Use on your phone" },
        { key: "cloud", label: "Your account" },
        { key: "backup", label: "Backup and safety" },
        { key: "dates", label: "Date converter" },
        { key: "guide", label: "Notes and rules" }
      ]}
    ];
  }

  var SCREENS = {};

  function register(key, builder) { SCREENS[key] = builder; }

  /* Boot */

  var installPrompt = null;

  function start() {
    UI.setupCalculator();
    wireChrome();
    registerWorker();
    refresh().catch(function (error) {
      qs("#boot").classList.add("hidden");
      UI.flash(error.message, "bad");
    });
  }

  function registerWorker() {
    // The worker is what lets a phone, tablet or desktop install this as an
    // app. It never caches an accounting figure, only the screens themselves.
    if (!("serviceWorker" in navigator)) { return; }
    if (location.protocol !== "https:" && location.hostname !== "localhost"
        && location.hostname !== "127.0.0.1") {
      // Browsers only allow installing over a secure connection or from this
      // machine. Over plain wifi the screens still work, they just cannot be
      // installed, so there is nothing to register.
      return;
    }
    navigator.serviceWorker.register("/sw.js").catch(function (error) {
      UI.noteError("service worker", error && error.message);
    });
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    installPrompt = event;
  });

  window.addEventListener("appinstalled", function () { installPrompt = null; });

  function canInstall() {
    return !!installPrompt;
  }

  function runInstall() {
    if (!installPrompt) { return Promise.resolve(false); }
    var prompt = installPrompt;
    installPrompt = null;
    prompt.prompt();
    return prompt.userChoice.then(function (choice) {
      return choice && choice.outcome === "accepted";
    });
  }

  function refresh() {
    return api("/api/bootstrap").then(function (data) {
      state.today = data.today;
      state.companies = data.companies || [];
      state.permissions = data.permissions || {};
      state.user = data.user;
      state.company = data.company;
      state.fiscalYear = data.fiscal_year || null;
      state.fiscalYears = data.fiscal_years || [];
      state.build = data.build || null;
      state.settings = data.settings || {};
      state.settings = data.settings || {};
      qs("#boot").classList.add("hidden");
      if (!data.user) { return showGate(data.needs_setup); }
      qs("#gate").classList.add("hidden");
      qs("#shell").classList.remove("hidden");
      paintChrome();
      if (!state.company) { return openCompanyChooser(); }
      return loadLookups().then(function () { go(state.route || "dashboard"); });
    });
  }

  function loadLookups() {
    return api("/api/lookups").then(function (data) { state.lookups = data; });
  }

  /* Sign in */

  function showGate(needsSetup) {
    qs("#shell").classList.add("hidden");
    var gate = qs("#gate");
    gate.classList.remove("hidden");
    qs("#login-username").focus();

    var stuck = qs("#gate-stuck");
    var helpPanel = qs("#gate-help-panel");
    stuck.textContent = needsSetup ? "What is this asking me for?" : "Cannot get in?";
    helpPanel.classList.add("hidden");
    stuck.onclick = function () {
      if (!helpPanel.classList.contains("hidden")) {
        helpPanel.classList.add("hidden");
        return;
      }
      helpPanel.classList.remove("hidden");
      helpPanel.textContent = "Looking…";
      api("/api/gate-help").then(function (info) {
        UI.clear(helpPanel);
        if (info.needs_setup) {
          helpPanel.appendChild(el("div", {}, [
            el("strong", { text: "There is no account on this computer yet." }),
            el("div", { text: "This screen is where you make one. There is no separate sign "
              + "up. Fill in a name, choose any username and password you like, and press "
              + "Create and continue. Write the password down, because nothing can recover "
              + "it." })
          ]));
          return;
        }
        var lines = el("div");
        lines.appendChild(el("div", {}, [
          el("strong", { text: "An account already exists on this computer." }),
          el("div", { text: info.accounts === 1
            ? "There is one account, the username is " + info.usernames[0] + "."
            : "There are " + info.accounts + " accounts: " + info.usernames.join(", ") + "." })
        ]));
        lines.appendChild(el("div", { style: "margin-top:.5rem" }, [
          el("span", { text: "That account was made the first time this was opened. The "
            + "screen that asked for a name and a password was the sign up. So there is "
            + "nothing else to press, you just need that password." })
        ]));
        if (info.empty) {
          var mac = navigator.platform.indexOf("Mac") >= 0;
          lines.appendChild(el("div", { style: "margin-top:.6rem" }, [
            el("strong", { text: "Nothing has been entered into the books yet." }),
            el("div", { text: "So starting again costs nothing. Close Saphal Book first, "
              + "then delete the file called system.db in the folder below and open "
              + "Saphal Book again. It will ask you to make a login from scratch." }),
            el("span.path", { text: info.data_folder }),
            el("div", { style: "margin-top:.4rem" }, [
              el("span", { text: mac
                ? "That folder is hidden. To reach it, open Finder, press Command, Shift and "
                  + "G together, paste the line above, and press Enter."
                : "Paste that line into the address bar of a File Explorer window and press "
                  + "Enter." })
            ]),
            el("button.secondary", {
              text: "Copy the folder", style: "margin-top:.5rem",
              onclick: function (event) {
                var button = event.currentTarget;
                var done = function () {
                  button.textContent = "Copied";
                  setTimeout(function () { button.textContent = "Copy the folder"; }, 2000);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                  navigator.clipboard.writeText(info.data_folder).then(done, function () {});
                } else {
                  var box = document.createElement("textarea");
                  box.value = info.data_folder;
                  document.body.appendChild(box);
                  box.select();
                  try { document.execCommand("copy"); done(); } catch (e) { /* nothing */ }
                  document.body.removeChild(box);
                }
              }
            })
          ]));
        } else {
          lines.appendChild(el("div", { style: "margin-top:.6rem" }, [
            el("strong", { text: "There is work in these books." }),
            el("div", { text: info.vouchers + " vouchers have been entered across "
              + info.companies + " compan" + (info.companies === 1 ? "y" : "ies")
              + ". Do not delete anything. Ask whoever set it up for the password." }),
            el("span.path", { text: info.data_folder })
          ]));
        }
        helpPanel.appendChild(lines);
      }).catch(function (error) {
        helpPanel.textContent = error.message;
      });
    };

    /* Signing in, or opening an account. Both are always on offer, because a
       second device has an account already but no login of its own, and a
       screen that only offers one of the two leaves somebody stuck. */

    var making = needsSetup;
    var switcher = qs("#gate-switch");

    function paintMode() {
      qs("#gate-title").textContent = making ? "Open an account" : "Sign in";
      qs("#gate-submit").textContent = making ? "Open it and continue" : "Sign in";
      switcher.textContent = making
        ? "I already have an account, sign me in"
        : "Open a new account";
      qs("#login-password").setAttribute(
        "autocomplete", making ? "new-password" : "current-password");
      UI.qsa(".hidden-when-login").forEach(function (node) {
        node.classList.toggle("hidden", !making);
      });
      // Signing in is not the place to explain how any of this works. Somebody
      // here wants to get into their books. The one line that survives is the
      // one that costs them something if they do not know it: the password
      // cannot be reset, because it is also the key the books are locked with.
      qs("#gate-help").textContent = making
        ? "Use at least eight characters. This password also unlocks your books "
          + "and cannot be reset, so write it down."
        : "";
      qs("#gate-error").textContent = "";
    }

    switcher.onclick = function () { making = !making; paintMode(); };
    paintMode();

    var form = qs("#login-form");
    form.onsubmit = function (event) {
      event.preventDefault();
      qs("#gate-error").textContent = "";
      var body = {
        username: qs("#login-username").value.trim(),
        password: qs("#login-password").value
      };
      if (making) { body.full_name = qs("#setup-fullname").value.trim(); }
      var submit = qs("#gate-submit");
      submit.disabled = true;
      submit.textContent = making ? "Opening…" : "Signing in…";
      api(making ? "/api/register" : "/api/login", { body: body })
        .then(function (result) {
          qs("#login-password").value = "";
          if (result && result.account === false && result.account_note) {
            UI.flash("Signed in on this machine. The account could not be reached, so "
                     + "nothing will travel to your other devices until it can.", "warn");
          }
          // Whatever is waiting on the account is fetched after the door is
          // open, not before it. Signing in should never wait on a download.
          if (result && result.account) {
            api("/api/cloud/fetch-waiting", { body: {} }).then(function (got) {
              if (!got || !got.count) { return; }
              UI.flash(got.count === 1
                ? "Brought down " + got.names[0] + "."
                : "Brought down " + got.count + " sets of books.", "good");
              return refresh();
            }).catch(function () { /* offline. The books here still open. */ });
          }
          return refresh();
        })
        .catch(function (error) {
          submit.disabled = false;
          paintMode();
          qs("#gate-error").textContent = error.message;
        });
    };
  }

  /* Chrome */

  function wireChrome() {
    qs("#btn-calc").addEventListener("click", UI.toggleCalculator);
    qs("#btn-menu").addEventListener("click", function () {
      UI.qs(".sidebar").classList.toggle("open");
    });
    qs("#today-chip").addEventListener("click", openCalendar);
    qs("#modal-close").addEventListener("click", UI.closeModal);
    qs("#modal").addEventListener("click", function (event) {
      if (event.target.id === "modal") { UI.closeModal(); }
    });
    UI.installGuards();
    UI.applyTheme();
    UI.watchSystemTheme();
    qs("#company-select").addEventListener("change", function (event) {
      api("/api/companies/select", { body: { company_id: +event.target.value } })
        .then(function () { state.route = "dashboard"; return refresh(); })
        .catch(function (error) { UI.flash(error.message, "bad"); });
    });
    qs("#user-chip").addEventListener("click", openUserMenu);
    wireFinder();
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { UI.closeModal(); UI.hidePicker(); }
      if (event.key === "F2") { event.preventDefault(); UI.toggleCalculator(); }
      if (event.key === "F3") { event.preventDefault(); openCalendar(); }
      var inField = /^(INPUT|SELECT|TEXTAREA)$/.test((event.target.tagName || ""));
      var shortcuts = { F1: "dashboard", F5: "sales", F6: "purchase",
                        F7: "receipt", F8: "payment", F9: "journal" };
      if (shortcuts[event.key] && state.user && state.company) {
        event.preventDefault();
        go(shortcuts[event.key]);
      }
      if (event.ctrlKey && event.key === "p" && !inField) {
        event.preventDefault(); UI.printPage();
      }
    });
  }

  function paintChrome() {
    if (!state.user) { return; }
    // On a narrow screen the first name is enough. The full name is in the title.
    var whole = state.user.full_name || state.user.username;
    qs("#user-chip").textContent = window.innerWidth <= 600 ? whole.split(" ")[0] : whole;
    qs("#user-chip").title = "Signed in as " + state.user.username;
    var today = state.today || {};
    var chip = UI.clear(qs("#today-chip"));
    chip.appendChild(el("span.date-full", {
      text: (today.bs_long || "") + "   " + (today.ad_long || "") }));
    chip.appendChild(el("span.date-short", { text: today.bs_parts
      ? NP.formatBs(today.bs_parts, "short") : "" }));
    chip.title = "Open the Nepali calendar";
    var fyChip = qs("#fy-chip");
    fyChip.textContent = state.fiscalYear ? "FY " + state.fiscalYear.label : "";
    fyChip.classList.toggle("hidden", !state.company || !state.fiscalYear);
    qs("#side-company").textContent = state.company ? state.company.name : "Choose a company";
    qs("#side-company").title = state.company ? state.company.name : "";


    var picker = UI.clear(qs("#company-select"));
    state.companies.forEach(function (company) {
      picker.appendChild(el("option", {
        value: company.id, text: company.name,
        selected: state.company && company.id === state.company.id
      }));
    });
    picker.appendChild(el("option", { value: "__new", text: "Add a new company" }));
    picker.onchange = function (event) {
      if (event.target.value === "__new") { openCompanyForm(); return; }
      api("/api/companies/select", { body: { company_id: +event.target.value } })
        .then(function () { state.route = "dashboard"; return refresh(); })
        .catch(function (error) { UI.flash(error.message, "bad"); });
    };

    var version = qs(".side-version");
    if (version && state.build) {
      version.textContent = state.build.behind
        ? "Out of date, built " + state.build.stamp
        : "Local and offline  ·  " + state.build.stamp;
      version.classList.toggle("stale", !!state.build.behind);
      version.title = state.build.behind
        ? "This app is running an older copy of the software than the one on this "
          + "computer. Double click \u201cUpdate Saphal Book\u201d in the project "
          + "folder and open it again."
        : "The copy of the software this app is running";
    }

    Sync.start();
    wireCloseButton();

    var nav = UI.clear(qs("#nav"));
    buildMenu().forEach(function (group) {
      var block = el("div.nav-group", {}, [el("div.nav-group-title", { text: group.title })]);
      group.items.forEach(function (item) {
        block.appendChild(el("button.nav-item" + (state.route === item.key ? ".active" : ""), {
          onclick: function () { go(item.key); }
        }, [
          el("span", { text: item.label }),
          item.accel ? el("span.nav-key", { text: item.accel }) : null
        ]));
      });
      nav.appendChild(block);
    });
  }

  /* The Nepali calendar, from anywhere.

     A month at a time with the Gregorian date under each day, today marked,
     Saturdays in red, and the fiscal year the month falls in. */

  function openCalendar() {
    var todayIso = NP.todayIso();
    var view = NP.adToBs(todayIso);
    var body = el("div");

    function draw() {
      UI.clear(body);
      var days = NP.daysInMonth(view.year, view.month);
      if (!days) { return; }
      var firstAd = NP.bsToAd(view.year, view.month, 1);
      var fy = NP.fiscalYearOf(firstAd);

      body.appendChild(el("div.cal-head", {}, [
        el("button.icon-button", { text: "‹", title: "Previous month",
                                   onclick: function () { step(-1); } }),
        el("div", { style: "text-align:center" }, [
          el("div.cal-month", { text: NP.MONTHS_EN[view.month - 1] + " " + view.year }),
          el("div.cal-sub", { text: firstAd.slice(0, 7) + "  ·  " + days + " days"
            + "  ·  fiscal year " + fy.label })
        ]),
        el("button.icon-button", { text: "›", title: "Next month",
                                   onclick: function () { step(1); } })
      ]));

      var grid = el("div.cal-grid");
      NP.DOW_EN.forEach(function (name) { grid.appendChild(el("div.cal-dow", { text: name })); });
      for (var blank = 0; blank < NP.weekdayIndex(firstAd); blank++) {
        grid.appendChild(el("div"));
      }
      for (var d = 1; d <= days; d++) {
        var iso = NP.bsToAd(view.year, view.month, d);
        var classes = "div.cal-day";
        if (iso === todayIso) { classes += ".today"; }
        if (NP.weekdayIndex(iso) === 6) { classes += ".saturday"; }
        grid.appendChild(el(classes, {}, [
          el("div.cal-bs", { text: String(d) }),
          el("div.cal-ad", { text: iso.slice(8) + " " + monthShort(iso) })
        ]));
      }
      body.appendChild(grid);

      body.appendChild(el("div.cal-foot", {}, [
        el("button.link-button", { text: "Back to this month", onclick: function () {
          view = NP.adToBs(todayIso); draw();
        }}),
        el("span.card-note", { text: "Saturday shown in red. Public holidays are not built in." })
      ]));
    }

    function monthShort(iso) {
      var names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return names[parseInt(iso.slice(5, 7), 10) - 1];
    }

    function step(direction) {
      view.month += direction;
      if (view.month > 12) { view.month = 1; view.year += 1; }
      if (view.month < 1) { view.month = 12; view.year -= 1; }
      if (!NP.daysInMonth(view.year, view.month)) { view.month -= direction; return; }
      draw();
    }

    draw();
    UI.modal("Nepali calendar", body, [
      { label: "Close" },
      { label: "Date converter", action: function () { UI.closeModal(); go("dates"); return false; } }
    ], { slim: true });
  }

  function openUserMenu() {
    var themeChoice = UI.getTheme();
    var segmented = el("div.segmented");
    [["light", "Light"], ["dark", "Dark"], ["system", "Follow the device"]].forEach(function (pair) {
      segmented.appendChild(el("button" + (themeChoice === pair[0] ? ".on" : ""), {
        text: pair[1],
        onclick: function (event) {
          UI.setTheme(pair[0]);
          UI.qsa("button", segmented).forEach(function (b) { b.classList.remove("on"); });
          event.currentTarget.classList.add("on");
        }
      }));
    });

    var body = el("div", {}, [
      el("p", { text: (state.user.full_name || state.user.username)
        + ", signed in as " + (state.roles && state.roles[state.user.role] || state.user.role) + "." }),
      UI.field("Appearance", segmented),
      canInstall() ? el("div.install-bar", {}, [
        el("span", { text: "Install Saphal Book on this device and it gets its own icon." }),
        el("button.primary", { text: "Install", onclick: function () {
          runInstall().then(function (yes) {
            if (yes) { UI.flash("Installed. Look for the icon with your other apps.", "good"); }
            UI.closeModal();
          });
        }})
      ]) : null,
      el("div.row", { style: "margin-top:.8rem" }, [
        el("button.secondary", { text: "Change my password", onclick: function () {
          UI.closeModal(); openPasswordForm();
        }}),
        el("button.secondary", { text: "Switch company", onclick: function () {
          UI.closeModal(); state.company = null; openCompanyChooser();
        }}),
        el("button.secondary", { text: "Sign out", onclick: function () {
          api("/api/logout", { body: {} }).then(function () { location.reload(); });
        }})
      ])
    ]);
    UI.modal("Your account", body, [{ label: "Close" }], { slim: true });
  }

  function openPasswordForm() {
    var current = el("input", { type: "password", autocomplete: "current-password" });
    var fresh = el("input", { type: "password", autocomplete: "new-password" });
    var again = el("input", { type: "password", autocomplete: "new-password" });
    var body = el("div", {}, [
      UI.field("Current password", current),
      UI.field("New password", fresh, "At least eight characters."),
      UI.field("Type the new password again", again)
    ]);
    UI.modal("Change password", body, [
      { label: "Cancel" },
      { label: "Change it", kind: "primary", action: function () {
        if (fresh.value !== again.value) {
          UI.flash("The two new passwords are not the same.", "bad");
          return false;
        }
        return api("/api/change-password", {
          body: { current_password: current.value, new_password: fresh.value }
        }).then(function () { UI.flash("Password changed.", "good"); });
      }}
    ]);
  }

  /* Keeping level with the server without being asked.

     Runs when somebody signs in, a little after anything is entered, when the
     window is brought back to the front, and slowly in the background. It
     stays silent when there is nothing to do, which is almost always, and
     speaks up only when it has moved something or cannot decide. */

  var Sync = (function () {
    var timer = null, settle = null, running = false, last = 0;
    /* A set of books that cannot be settled without somebody choosing is worth
       saying once. It used to be said on every run, so a yellow bar came back
       every two minutes saying the same thing, which is nagging rather than
       telling. The screen carries it from then on. */
    var told = {};

    function run(why) {
      if (running || !state.user) { return Promise.resolve(); }
      running = true;
      return api("/api/cloud/auto", { body: {} })
        .then(function (result) {
          last = Date.now();
          if (!result || !result.ran || result.quiet) { return; }
          var moved = (result.sent || []).length + (result.fetched || []).length;
          if (moved) {
            var parts = [];
            if ((result.sent || []).length) { parts.push("sent " + result.sent.join(", ")); }
            if ((result.fetched || []).length) {
              parts.push("brought down " + result.fetched.join(", "));
            }
            UI.flash("Synced: " + parts.join(", ") + ".", "good");
            // Books that arrived change what is on the screen underneath.
            if ((result.fetched || []).length) { refresh(); }
          }
          var waiting = (result.conflicts || []).filter(function (row) {
            return row.slug && !told[row.slug];
          });
          (result.conflicts || []).forEach(function (row) {
            if (row.slug) { told[row.slug] = true; }
          });
          if (waiting.length) {
            UI.flash(waiting.length === 1
              ? waiting[0].name + " does not match your other device. Open Your account "
                + "and pick which one to keep."
              : waiting.length + " companies do not match your other device. Open Your "
                + "account and pick which ones to keep.", "warn");
          }
          state.conflicts = result.conflicts || [];
        })
        .catch(function () { /* offline, or not signed in. Nothing to say. */ })
        .then(function () { running = false; });
    }

    /* Something was entered. Wait for the typing to stop before sending, so a
       run of ten invoices is one upload and not ten.

       The wait used to be eight seconds. Every second of it is a second in
       which the other device can be opened and the two drift apart, and being
       asked afterwards which copy to keep is far more annoying than an upload
       nobody notices. Two seconds is long enough to gather a run of entries and
       short enough that walking to the other device does not outrun it. */
    function touched() {
      if (settle) { clearTimeout(settle); }
      settle = setTimeout(function () { run("entered"); }, 2000);
    }

    /* When it is safe to go to the network.

       In the browser version the request is made the blocking kind, because
       everything above it is ordinary top to bottom Python that expects an
       answer on the next line. Blocking on the main thread means the page
       really does stop: a click does nothing and nothing repaints until the
       answer comes back. Three sets of books is four or five round trips, so a
       sync landing while somebody is working is a freeze of a second or two,
       and that is the freeze that keeps being reported.

       So it never runs while somebody is using the software. Any key or click
       pushes it back, and it goes only after a few seconds of quiet, when a
       pause costs nobody anything. Pressing Check now is different: that is
       somebody asking for it, and it gets the bar. */

    var lastTouch = Date.now();
    var QUIET_FOR = 4000;

    function busyRightNow() {
      return Date.now() - lastTouch < QUIET_FOR;
    }

    function whenQuiet(why) {
      if (busyRightNow()) { return; }
      run(why);
      checkGoogleOccasionally();
    }

    /* Making this device and the account agree about Google.

       Worth doing, and worth doing nowhere near a click. It reaches Google, so
       in the browser version it stops the page while it waits. Once a day, in
       a quiet moment, is often enough for something that only changes when
       somebody deliberately reconnects a Drive. */

    var A_DAY = 24 * 60 * 60 * 1000;

    function checkGoogleOccasionally() {
      var last = 0;
      try { last = +(localStorage.getItem("cb_google_checked") || 0); } catch (e) { last = 0; }
      if (Date.now() - last < A_DAY) { return; }
      api("/api/backup/check-google", { body: {} }).then(function () {
        try { localStorage.setItem("cb_google_checked", String(Date.now())); } catch (e) {}
        // If the backup screen happens to be open, let it pick up what changed.
        if (App.state.route === "backup") { App.go("backup"); }
      }).catch(function () { /* offline, or no Drive connected. Nothing to say. */ });
    }

    function start() {
      if (timer) { return; }
      ["pointerdown", "keydown", "wheel", "touchstart"].forEach(function (event) {
        document.addEventListener(event, function () { lastTouch = Date.now(); },
                                  { passive: true, capture: true });
      });
      timer = setInterval(function () { whenQuiet("timer"); }, 60000);
      window.addEventListener("focus", function () {
        lastTouch = Date.now();
        if (Date.now() - last > 30000) { setTimeout(function () { whenQuiet("focus"); }, QUIET_FOR); }
      });
      document.addEventListener("visibilitychange", function () {
        if (document.hidden || Date.now() - last <= 30000) { return; }
        setTimeout(function () { whenQuiet("visible"); }, QUIET_FOR);
      });
      // Once, a moment after the screen has settled, rather than during the
      // rush of everything else that happens as the software opens.
      setTimeout(function () { whenQuiet("start"); }, 3000);
    }

    function forget(slug) { delete told[slug]; }

    return { run: run, touched: touched, start: start, forget: forget };
  }());

  /* Finding one thing, without knowing which screen it is on.

     Somebody looking for SI0042, or for Sharma Nirman, or for the ledger they
     call rates and taxes, types it and is taken there. Knowing that an invoice
     lives on the day book and a customer on the records screen is knowledge
     about the software rather than about the books.

     The search waits for typing to stop rather than firing on every key,
     because on a tablet each one crosses to the engine and back, and eight of
     those for a word nobody has finished spelling is work done for nothing. */

  function wireFinder() {
    var box = qs("#finder");
    var results = qs("#finder-results");
    if (!box || !results) { return; }
    var settle = null;
    var picked = -1;
    var rows = [];

    function hide() { results.classList.add("hidden"); picked = -1; rows = []; }

    function draw(found) {
      UI.clear(results);
      rows = [];
      if (found.note && !found.count) {
        results.appendChild(el("div.finder-note", { text: found.note }));
        results.classList.remove("hidden");
        return;
      }
      (found.groups || []).forEach(function (group) {
        results.appendChild(el("div.finder-group", { text: group.title }));
        group.rows.forEach(function (row) {
          var line = el("div.finder-row", {}, [
            el("div.finder-main", {}, [
              el("span", { text: row.label }),
              row.cancelled ? el("span.pill.warn", { text: "cancelled" }) : null
            ]),
            el("div.finder-detail", { text: row.detail || "" }),
            row.amount ? el("div.finder-amount", { text: UI.rs(row.amount) }) : null
          ]);
          line.addEventListener("mousedown", function (event) {
            event.preventDefault();
            open(row);
          });
          rows.push({ node: line, row: row });
          results.appendChild(line);
        });
      });
      results.classList.remove("hidden");
    }

    function highlight(step) {
      if (!rows.length) { return; }
      if (picked >= 0) { rows[picked].node.classList.remove("on"); }
      picked = (picked + step + rows.length) % rows.length;
      rows[picked].node.classList.add("on");
      rows[picked].node.scrollIntoView({ block: "nearest" });
    }

    function open(row) {
      hide();
      box.value = "";
      box.blur();
      // Each of these already has a way in from elsewhere in the software, so
      // the search uses those rather than inventing a second one that would
      // then have to be kept in step.
      if (row.opens === "voucher") { return Vouchers.view(row.id); }
      if (row.opens === "ledger") { return Reports.openLedger(row.id); }
      if (row.opens === "item") { return Reports.openItemMovement(row.id); }
      if (row.opens === "party") {
        App.state.pendingStatement = row.id;
        return go("statement");
      }
    }

    box.addEventListener("input", function () {
      if (settle) { clearTimeout(settle); }
      var text = box.value.trim();
      if (text.length < 2) { return hide(); }
      settle = setTimeout(function () {
        api("/api/find", { query: { q: text } })
          .then(draw)
          .catch(function () { hide(); });
      }, 220);
    });

    box.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); return highlight(1); }
      if (event.key === "ArrowUp") { event.preventDefault(); return highlight(-1); }
      if (event.key === "Escape") { return hide(); }
      if (event.key === "Enter" && picked >= 0) {
        event.preventDefault();
        open(rows[picked].row);
      }
    });

    box.addEventListener("blur", function () { setTimeout(hide, 150); });

    // Ctrl or Command and K, which is where everybody's hands already go.
    document.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        box.focus();
        box.select();
      }
    });
  }

  /* Finishing for the day.

     Closing the window leaves the books being served, which is deliberate: a
     phone on the same wifi goes on reaching them. This is how somebody actually
     stops the software, now that the icon no longer holds a Quit of its own. */

  function wireCloseButton() {
    var button = qs("#btn-close-app");
    if (!button || button.dataset.wired) { return; }
    button.dataset.wired = "1";
    if (window.CHARTERED_BOOK_WEB) { button.style.display = "none"; return; }
    button.onclick = function () {
      UI.confirmAction("Finish for the day",
        "This closes Saphal Book properly, not just the window. A backup is taken "
        + "on the way out. Anybody using it from a phone on the same wifi will lose "
        + "the connection until it is opened again.",
        function () {
          return api("/api/close", { body: {} }).then(function () {
            document.body.innerHTML =
              "<div style=\"display:grid;place-items:center;height:100vh;"
              + "font:16px -apple-system,system-ui,sans-serif;color:#334\">"
              + "<div style=\"text-align:center\"><p><b>Saphal Book is closed.</b></p>"
              + "<p style=\"color:#889\">A backup was taken. Open it again from the "
              + "icon whenever you need it.</p></div></div>";
          });
        }, "Close it");
    };
  }

  /* Routing */

  function go(key) {
    state.route = key;
    // Repainting the menu rebuilds it, which threw away where it was scrolled
    // to. Anybody working in Financial statements, which sits near the bottom,
    // was sent back to the top of the list on every single click.
    var nav = qs("#nav");
    var navScroll = nav ? nav.scrollTop : 0;
    var rail = UI.qs(".sidebar");
    var railScroll = rail ? rail.scrollTop : 0;
    paintChrome();
    nav = qs("#nav");
    if (nav) { nav.scrollTop = navScroll; }
    rail = UI.qs(".sidebar");
    if (rail) { rail.scrollTop = railScroll; }
    UI.qs(".sidebar").classList.remove("open");
    var page = UI.clear(qs("#page"));
    var builder = SCREENS[key];
    var label = "Dashboard";
    buildMenu().forEach(function (group) {
      group.items.forEach(function (item) { if (item.key === key) { label = item.label; } });
    });
    qs("#page-title").textContent = label;
    if (!builder) {
      page.appendChild(el("div.card", {}, [el("div.empty", { text: "That screen is not ready yet." })]));
      return;
    }
    var result = builder(page);
    if (result && typeof result.catch === "function") {
      result.catch(function (error) {
        if (error.status === 409) {
          UI.flash(error.message, "warn");
          refresh();
          return;
        }
        UI.flash(error.message, "bad");
      });
    }
    window.scrollTo(0, 0);
  }

  /* Company chooser and form */

  function openCompanyChooser() {
    var page = UI.clear(qs("#page"));
    qs("#page-title").textContent = "Choose a company";
    var wrap = el("div.chooser");

    wrap.appendChild(el("div", { style: "text-align:center;margin-bottom:1.4rem" }, [
      el("h2", { text: "Which set of books do you want to open?",
                 style: "font-size:1.2rem;margin-bottom:.25rem" }),
      el("p.card-note", { text: "Each business keeps its own books in its own file, so nothing "
        + "can leak from one into another. Switch at any time from the box at the top left." })
    ]));

    var grid = el("div.chooser-grid");
    var typeLabels = { trading: "Goods", service: "Services", both: "Goods and services" };
    state.companies.forEach(function (company) {
      grid.appendChild(el("button.chooser-card", {
        onclick: function () { openCompany(company.id); }
      }, [
        el("div.name", { text: company.name }),
        company.name_np ? el("div.meta", { text: company.name_np }) : null,
        el("div.tags", {}, [
          el("span.pill.brand", { text: typeLabels[company.business_type] || company.business_type })
        ])
      ]));
    });
    if (state.permissions["company.create"]) {
      grid.appendChild(el("button.chooser-card.new", { onclick: openCompanyForm }, [
        el("div", { text: "+", style: "font-size:1.5rem;line-height:1" }),
        el("div", { text: state.companies.length ? "Add another company" : "Create the first company" })
      ]));
    }
    wrap.appendChild(grid);

    if (!state.companies.length) {
      wrap.appendChild(el("div.card", { style: "margin-top:1.2rem" }, [
        el("p.card-note", { text: "Nothing has been set up yet. Creating a company lays out the "
          + "full Nepali chart of accounts, the units a hardware shop uses, the voucher types and "
          + "the tax deduction rates, so you can start entering the same day." })
      ]));
    }

    // Somebody arriving on a second device wants the books they already have,
    // not a new empty set. Being signed in to the software looks like being
    // signed in, so this was easy to miss when the only way to it was a line
    // near the bottom of the menu.
    wrap.appendChild(el("div.card", { style: "margin-top:1.2rem" }, [
      el("div.card-head", {}, [
        el("h2", { text: state.companies.length
          ? "Books kept on another device" : "Already have books on another device?" }),
        el("button.primary", { text: "Bring my books down",
          onclick: function () { go("cloud"); } })
      ]),
      el("p.card-note", { text: "Sign in to your account and fetch whatever is waiting. "
        + "The same username reaches the same books on a computer, a phone or a tablet." })
    ]));
    page.appendChild(wrap);
  }

  function openCompany(companyId) {
    return api("/api/companies/select", { body: { company_id: companyId } })
      .then(function () {
        localStorage.setItem("cb_last_company", String(companyId));
        state.route = "dashboard";
        return refresh();
      })
      .catch(function (error) { UI.flash(error.message, "bad"); });
  }

  function openCompanyForm() {
    var name = el("input", { type: "text" });
    var nameNp = el("input", { type: "text" });

    var chosenType = "trading";
    var typeButtons = {};
    function typeButton(value, label, note) {
      var button = el("button.chooser-card", {
        onclick: function () {
          chosenType = value;
          Object.keys(typeButtons).forEach(function (key) {
            typeButtons[key].style.borderColor = key === value ? "var(--brand)" : "";
            typeButtons[key].style.background = key === value ? "var(--brand-soft)" : "";
          });
        }
      }, [
        el("div.name", { text: label, style: "font-size:.92rem" }),
        el("div.meta", { text: note })
      ]);
      typeButtons[value] = button;
      return button;
    }
    var typeGrid = el("div.chooser-grid", { style: "grid-template-columns:repeat(auto-fit,minmax(190px,1fr))" }, [
      typeButton("trading", "Goods only", "A shop that buys and sells. Stock, items, purchase bills."),
      typeButton("service", "Services only", "A practice that bills its time. No stock to count."),
      typeButton("both", "Goods and services", "Both, with every screen switched on.")
    ]);
    setTimeout(function () { typeButtons.trading.click(); }, 0);

    var entityType = UI.select([
      { value: "proprietorship", label: "Sole proprietorship" },
      { value: "partnership", label: "Partnership firm" },
      { value: "private_limited", label: "Private limited company" },
      { value: "public_limited", label: "Public limited company" },
      { value: "cooperative", label: "Cooperative" },
      { value: "ngo", label: "Non government organisation" },
      { value: "other", label: "Other" }
    ], "proprietorship");
    var pan = el("input", { type: "text", maxlength: "9", inputmode: "numeric" });
    var vat = el("input", { type: "checkbox" });
    pan.addEventListener("input", function () {
      if (pan.value.trim().length === 9) { vat.checked = true; }
    });
    var address = el("input", { type: "text" });
    var city = el("input", { type: "text" });
    var district = el("input", { type: "text" });
    var phone = el("input", { type: "text" });
    var email = el("input", { type: "text" });
    var ird = el("input", { type: "text" });
    var beginField = UI.dateField(NP.fiscalYearOf(NP.todayIso()).startAd);

    var body = el("div", {}, [
      el("div.section-title", { text: "What is it" }),
      el("div.row", {}, [
        UI.field("Company name", name),
        UI.field("Name in Nepali", nameNp, "Printed on the invoice where Nepali is expected")
      ]),
      el("div.field", {}, [
        el("label", { text: "What does this business do" }),
        typeGrid,
        el("div.hint", { text: "This decides which screens appear. It can be changed later." })
      ]),
      el("div.section-title", { text: "Registration" }),
      el("div.row", {}, [
        UI.field("How is it registered", entityType),
        UI.field("PAN or VAT number", pan, "Nine digits"),
        UI.field("Registered for VAT", el("label.check", {}, [vat, el("span", { text: "Yes, charge 13 percent" })]))
      ]),
      UI.field("Inland Revenue office", ird),
      el("div.section-title", { text: "Where it is" }),
      UI.field("Address", address),
      el("div.row", {}, [UI.field("City", city), UI.field("District", district)]),
      el("div.row", {}, [UI.field("Phone", phone), UI.field("Email", email)]),
      el("div.section-title", { text: "When the books start" }),
      UI.field("Books begin on", beginField,
        "Usually 1 Shrawan. Nothing can be posted before this date, so set it to the day you are "
        + "carrying the opening balances in from.")
    ]);

    UI.modal("New company", body, [
      { label: "Cancel" },
      { label: "Create the books", kind: "primary", action: function () {
        if (!name.value.trim()) { UI.flash("Give the company a name.", "bad"); return false; }
        var pn = pan.value.trim();
        if (pn && (pn.length !== 9 || !/^\d+$/.test(pn))) {
          UI.flash("A Nepali PAN is nine digits.", "bad");
          return false;
        }
        return api("/api/companies/create", { body: {
          name: name.value.trim(), name_np: nameNp.value.trim(),
          business_type: chosenType, entity_type: entityType.value,
          pan: pn, vat_registered: vat.checked ? 1 : 0,
          ird_office: ird.value.trim(),
          address: address.value.trim(), city: city.value.trim(),
          district: district.value.trim(), phone: phone.value.trim(),
          email: email.value.trim(), books_begin_ad: beginField.getIso()
        }}).then(function (made) {
          UI.flash("The books are ready. The full Nepali chart of accounts is set up.", "good");
          localStorage.setItem("cb_last_company", String(made.id));
          state.route = "dashboard";
          return refresh();
        });
      }}
    ], { wide: true });
  }

  /* Dashboard */

  register("dashboard", function (page) {
    return api("/api/dashboard").then(function (data) {
      var tiles = el("div.grid.four", {}, [
        tile("Revenue this year", UI.rs(data.revenue), "Sales and service income", "violet"),
        tile("Gross profit", UI.rs(data.gross_profit),
          data.pending_closing_stock ? "Counting stock still on the shelf" : "Revenue less cost of sales",
          "teal"),
        tile("Profit", UI.rs(data.profit), "After every expense", data.profit >= 0 ? "good" : "bad"),
        tile("Stock on hand", UI.rs(data.stock_value), data.counts.items + " items on the list", "amber")
      ]);
      var tiles2 = el("div.grid.four", {}, [
        tile("Receivable", UI.rs(data.receivable), "Owed to you by customers", "violet"),
        tile("Payable", UI.rs(data.payable), "Owed by you to suppliers", "amber"),
        tile("Cash and bank", UI.rs(data.cash_and_bank.total),
             data.cash_and_bank.rows.length + " accounts", "teal"),
        data.vat
          ? tile(data.vat.net >= 0 ? "VAT payable, " + data.vat.month_name : "VAT credit, " + data.vat.month_name,
                 UI.rs(Math.abs(data.vat.net)), "Due by " + data.vat.due_date_bs, "rose")
          : tile("Vouchers posted", String(data.counts.vouchers), "This year", "teal")
      ]);
      page.appendChild(tiles);
      page.appendChild(tiles2);
      if (data.pending_closing_stock) {
        page.appendChild(el("div.card", { style: "border-color:#f0dcb4;background:var(--warn-soft)" }, [
          el("div", { style: "display:flex;gap:.8rem;align-items:center;flex-wrap:wrap" }, [
            el("span", { style: "color:var(--warn);font-size:.86rem", text:
              "The figures above count " + UI.rs(data.pending_closing_stock)
              + " of stock that is on the shelf but not yet brought into the accounts. "
              + "Pass the closing stock entry to make the profit and loss read the same way." }),
            el("button.secondary", { text: "Go to closing stock",
              onclick: function () { go("period-end"); } })
          ])
        ]));
      }

      var actions = el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Start something" })]),
        el("div.row", {}, [
          el("button.primary", { text: "New sales invoice", onclick: function () { go("sales"); } }),
          el("button.secondary", { text: "New purchase bill", onclick: function () { go("purchase"); } }),
          el("button.secondary", { text: "Receipt", onclick: function () { go("receipt"); } }),
          el("button.secondary", { text: "Payment", onclick: function () { go("payment"); } }),
          el("button.secondary", { text: "Add a customer", onclick: function () { Masters.openPartyForm(null, "customer"); } }),
          el("button.secondary", { text: "Add an item", onclick: function () { Masters.openItemForm(null); } })
        ])
      ]);
      page.appendChild(actions);

      var columns = el("div.grid.two");
      var recent = (data.recent_vouchers || []).map(function (row) {
        return el("tr.clickable", { onclick: function () { Vouchers.view(row.id); } }, [
          el("td", { text: UI.bs(row.date_ad, "short") }),
          el("td", { text: row.type_name }),
          el("td", { text: row.number }),
          el("td", { text: row.party_name || "" }),
          el("td.num", { text: UI.rs(row.total_paisa) })
        ]);
      });
      columns.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: "Latest entries" }),
          el("button.link-button", { text: "Open the day book", onclick: function () { go("daybook"); } })
        ]),
        UI.table(["Date", "Type", "Number", "Party", { label: "Amount", num: true }], recent, null,
          { emptyText: "No vouchers yet. Start with a sales invoice or a purchase bill." })
      ]));

      var low = (data.low_stock || []).map(function (row) {
        return el("tr", {}, [
          el("td", { text: row.name }),
          el("td.num", { text: NP.formatQty(row.qty) + " " + row.unit }),
          el("td.num", { text: NP.formatQty(row.reorder_qty) })
        ]);
      });
      columns.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Running low" })]),
        UI.table(["Item", { label: "In stock", num: true }, { label: "Reorder at", num: true }],
          low, null, { emptyText: "Nothing is below its reorder level." })
      ]));
      page.appendChild(columns);
    });
  });

  function tile(label, value, note, kind) {
    return el("div.tile" + (kind ? "." + kind : ""), {}, [
      el("div.tile-label", { text: label }),
      el("div.tile-value", { text: value }),
      note ? el("div.tile-note", { text: note }) : null
    ]);
  }

  /* Company settings */

  register("company", function (page) {
    return api("/api/company").then(function (data) {
      var profile = data.profile;
      var fields = {};
      function text(key, label, hint, attrs) {
        fields[key] = el("input", Object.assign({ type: "text", value: profile[key] || "" }, attrs || {}));
        return UI.field(label, fields[key], hint);
      }

      var vatBox = el("input", { type: "checkbox" });
      vatBox.checked = !!profile.vat_registered;

      var card = el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Company details" }),
          el("span.card-note", { text: "These appear on every invoice and report." })]),
        el("div.row", {}, [text("name", "Name"), text("name_np", "Name in Nepali")]),
        el("div.row", {}, [
          text("pan", "PAN or VAT number", "Nine digits", { maxlength: "9" }),
          UI.field("Registered for VAT", el("div", { style: "padding-top:.3rem" }, [vatBox])),
          text("ird_office", "Inland Revenue office")
        ]),
        el("div.row", {}, [text("address", "Address"), text("address_np", "Address in Nepali")]),
        el("div.row", {}, [text("ward_no", "Ward"), text("city", "City"), text("district", "District"), text("province", "Province")]),
        el("div.row", {}, [text("phone", "Phone"), text("mobile", "Mobile"), text("email", "Email"), text("website", "Website")]),
        el("div.row", {}, [text("registration_no", "Registration number"), text("registration_date", "Registration date")])
      ]);

      var footer = el("input", { type: "text", value: (data.settings || {}).invoice_footer || "" });
      var terms = el("textarea", { rows: "3" });
      terms.value = (data.settings || {}).invoice_terms || "";
      var roundBox = el("input", { type: "checkbox" });
      roundBox.checked = (data.settings || {}).auto_round_invoice !== "0";
      var wordsBox = el("input", { type: "checkbox" });
      wordsBox.checked = (data.settings || {}).show_amount_in_words !== "0";
      var negativeBox = el("input", { type: "checkbox" });
      negativeBox.checked = (data.settings || {}).allow_negative_stock === "1";

      var invoiceCard = el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Invoice settings" })]),
        UI.field("Line printed at the foot of every invoice", footer),
        UI.field("Terms and conditions", terms),
        el("div.row", {}, [
          UI.field("Round invoices to the rupee", el("div", { style: "padding-top:.3rem" }, [roundBox])),
          UI.field("Print the amount in words", el("div", { style: "padding-top:.3rem" }, [wordsBox])),
          UI.field("Allow stock to go negative", el("div", { style: "padding-top:.3rem" }, [negativeBox]))
        ])
      ]);

      var yearRows = (data.fiscal_years || []).map(function (fy) {
        return el("tr", {}, [
          el("td", { text: fy.label }),
          el("td", { text: UI.bs(fy.start_ad, "short") + " to " + UI.bs(fy.end_ad, "short") }),
          el("td", { text: fy.start_ad + " to " + fy.end_ad }),
          el("td", {}, [el("span.pill" + (fy.status === "open" ? ".good" : ""), { text: fy.status })]),
          el("td", {}, [
            data.fiscal_year && fy.id === data.fiscal_year.id
              ? el("span.pill", { text: "in use" })
              : el("button.link-button", { text: "Work in this year", onclick: function () {
                  api("/api/fiscal-years/select", { body: { fiscal_year_id: fy.id } })
                    .then(function () { return refresh(); })
                    .catch(function (error) { UI.flash(error.message, "bad"); });
                }})
          ])
        ]);
      });

      // Years already open, so the buttons offer the ones on either side of
      // what is there rather than blindly offering the next one.
      var openYears = (data.fiscal_years || []).map(function (fy) {
        return +String(fy.label).split("/")[0];
      });
      var thisYear = NP.adToBs(NP.todayIso()).year;
      var nextYear = openYears.length ? Math.max.apply(null, openYears) + 1 : thisYear;
      var earlierYear = openYears.length ? Math.min.apply(null, openYears) - 1 : thisYear - 1;

      function label(year) { return year + "/" + NP.pad((year + 1) % 100, 2); }
      function openYear(year, note) {
        api("/api/fiscal-years/create", { body: { start_bs_year: year } })
          .then(function () { UI.flash(note, "good"); go("company"); })
          .catch(function (error) { UI.flash(error.message, "bad"); });
      }

      var yearCard = el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: "Fiscal years" }),
          el("button.secondary", { text: "Open " + label(earlierYear),
            onclick: function () {
              openYear(earlierYear, "Fiscal year " + label(earlierYear)
                + " opened. The books now begin at the start of it.");
            }}),
          el("button.secondary", { text: "Open " + label(nextYear),
            onclick: function () { openYear(nextYear, "Fiscal year opened."); }})
        ]),
        el("p.card-note", { text: "A Nepali fiscal year runs from 1 Shrawan to the last day "
          + "of Ashadh. Each year keeps its own voucher numbering, so PI0001 in one year and "
          + "PI0001 in the next are two different bills and never mix. Open the year before "
          + "entering vouchers dated in it. Opening an earlier year, to bring last year's "
          + "books in, moves the date the books begin back to the start of that year." }),
        UI.table(["Year", "Bikram Sambat", "Gregorian", "Status", ""], yearRows)
      ]);

      var save = el("button.primary", { text: "Save changes", onclick: function () {
        var body = { settings: {
          invoice_footer: footer.value, invoice_terms: terms.value,
          auto_round_invoice: roundBox.checked ? "1" : "0",
          show_amount_in_words: wordsBox.checked ? "1" : "0",
          allow_negative_stock: negativeBox.checked ? "1" : "0"
        }};
        Object.keys(fields).forEach(function (key) { body[key] = fields[key].value.trim(); });
        body.vat_registered = vatBox.checked ? 1 : 0;
        api("/api/company/update", { body: body })
          .then(function () { UI.flash("Saved.", "good"); return refresh(); })
          .catch(function (error) { UI.flash(error.message, "bad"); });
      }});

      page.appendChild(card);
      page.appendChild(invoiceCard);
      page.appendChild(el("div", { style: "margin:-.3rem 0 1rem" }, [save]));
      page.appendChild(yearCard);
    });
  });

  /* Users */

  register("users", function (page) {
    if (!state.permissions["user.manage"]) {
      page.appendChild(el("div.card", {}, [el("div.empty", { text: "Only an owner can manage users." })]));
      return;
    }
    return api("/api/users").then(function (data) {
      var rows = data.rows.map(function (user) {
        return el("tr", {}, [
          el("td", { text: user.username }),
          el("td", { text: user.full_name }),
          el("td", { text: user.role }),
          el("td", {}, [el("span.pill" + (user.active ? ".good" : ".bad"),
            { text: user.active ? "active" : "disabled" })]),
          el("td", { text: user.last_login_at || "never" }),
          el("td", {}, [
            el("button.link-button", { text: "Edit", onclick: function () { openUserForm(user); } })
          ])
        ]);
      });
      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: "People who can sign in" }),
          el("button.primary", { text: "Add a user", onclick: function () { openUserForm(null); } })
        ]),
        el("p.card-note", { text: "Owner can do everything. Accountant can post, edit and cancel. Operator enters day to day vouchers. View only can read reports and nothing else." }),
        UI.table(["Username", "Name", "Role", "Status", "Last signed in", ""], rows)
      ]));
    });
  });

  function openUserForm(user) {
    var username = el("input", { type: "text", value: user ? user.username : "", readonly: !!user });
    var fullName = el("input", { type: "text", value: user ? user.full_name : "" });
    var password = el("input", { type: "password", autocomplete: "new-password" });
    var role = UI.select(Object.keys({ owner: 1, accountant: 1, operator: 1, viewer: 1 }).map(function (key) {
      return { value: key, label: key.charAt(0).toUpperCase() + key.slice(1) };
    }), user ? user.role : "operator");
    var active = el("input", { type: "checkbox" });
    active.checked = user ? !!user.active : true;

    var body = el("div", {}, [
      UI.field("Username", username),
      UI.field("Full name", fullName),
      UI.field(user ? "New password, leave blank to keep the old one" : "Password", password,
        "At least eight characters."),
      UI.field("Role", role),
      user ? UI.field("Can sign in", el("div", {}, [active])) : null
    ]);

    UI.modal(user ? "Edit user" : "Add a user", body, [
      { label: "Cancel" },
      { label: "Save", kind: "primary", action: function () {
        var payload = { full_name: fullName.value.trim(), role: role.value };
        if (password.value) { payload.password = password.value; }
        if (user) {
          payload.active = active.checked ? 1 : 0;
          return api("/api/users/" + user.id + "/update", { body: payload })
            .then(function () { UI.flash("Saved.", "good"); go("users"); });
        }
        payload.username = username.value.trim();
        return api("/api/users/create", { body: payload })
          .then(function () { UI.flash("User added.", "good"); go("users"); });
      }}
    ]);
  }

  /* Backup */

  /* Carrying books from one device to another.

     Two machines with no way of reaching one another still have to share a set
     of books, and on a tablet there is no folder to reach into. So the file
     travels through the screen: saved out of one device, carried across, and
     brought into the other. */

  function bringBooksIn(onDone) {
    var picker = el("input", { type: "file", accept: ".zip" });
    UI.modal("Bring books in from another device", el("div", {}, [
      el("p", { text: "Choose the backup file the other device saved. It is a .zip whose "
        + "name begins with saphal_book." }),
      picker,
      el("p.card-note", { text: "This only stores the file here. Nothing in these books "
        + "changes until you press Restore on it in the list, and a safety copy is taken "
        + "before that happens." })
    ]), [
      { label: "Cancel" },
      { label: "Bring it in", kind: "primary", action: function () {
        var file = picker.files && picker.files[0];
        if (!file) { UI.flash("Choose the file first.", "bad"); return false; }
        return new Promise(function (resolve, reject) {
          var reader = new FileReader();
          reader.onerror = function () { reject(new Error("That file could not be read.")); };
          reader.onload = function () {
            var text = String(reader.result || "");
            var comma = text.indexOf(",");
            api("/api/backup/upload", { body: {
              filename: file.name, content: comma >= 0 ? text.slice(comma + 1) : text
            }}).then(function (result) {
              UI.flash("Brought in " + result.backup.filename + ". Press Restore on it when "
                       + "you are ready.", "good");
              if (onDone) { onDone(); }
              resolve();
            }).catch(reject);
          };
          reader.readAsDataURL(file);
        });
      }}
    ]);
  }

  /* Backup and restore.

     Two things happen here and nothing else. A copy of the books goes to the
     owner's Google Drive, and a copy comes back. Everything that used to sit on
     this screen about folders on the disk, second copies and carrying files
     between machines has gone: it was four ways of doing one job, and choosing
     between them was work nobody asked for. */

  register("backup", function (page) {
    return load();

    function load() {
      // Nothing but this device. Opening the screen used to go and ask Google
      // which account the backups belong to, right after painting, and in the
      // browser version that request blocks everything for about a second. The
      // screen appeared and then froze exactly as somebody reached for it,
      // which is the lag that kept being reported here.
      //
      // The address does not change on its own, so it is read from what was
      // written down. Checking it against Google is background work now, done
      // once a day when nobody is typing.
      return api("/api/backup/list").then(draw);
    }

    function draw(data) {
      UI.clear(page);
      page.appendChild(where(data));
      page.appendChild(taken(data));
    }

    function where(data) {
      var g = data.google || {};
      return el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: "Backing up to" }),
          el("button.primary", { text: "Back up now", onclick: function () { backUp(data); } })
        ]),
        g.connected
          ? el("div", {}, [
              el("div", { style: "font-size:1.02rem;font-weight:600", text: g.account
                          || "Google Drive" }),
              el("div", { style: "color:var(--ink-faint);font-size:.85rem;margin-top:.15rem",
                          text: g.folder_name || "Saphal Book backups" }),
              // Which account this belongs to, since it follows the person from
              // device to device rather than living on any one machine.
              state.user
                ? el("div", { style: "color:var(--ink-faint);font-size:.8rem;margin-top:.4rem",
                              text: "Linked to " + state.user.username
                                    + ". Signing in with that name on another device "
                                    + "backs up here too." })
                : null
            ])
          : el("div", {}, [
              el("div", { style: "font-size:1.02rem;font-weight:600",
                          text: "This device only" }),
              el("div", { style: "color:var(--ink-faint);font-size:.85rem;margin-top:.15rem",
                          text: data.folder || "" }),
              el("p.card-note", { text: "No Google account is connected here yet. Connect "
                + "one on the computer where Saphal Book is installed and sign in to your "
                + "account on this device, and it will follow you here." })
            ])
      ]);
    }

    function taken(data) {
      // The latest one is the answer to the only question anybody asks here.
      // The rest were a log nobody read, so they are behind a link.
      var all = data.backups || [];
      var latest = all[0];
      var older = all.slice(1);
      var box = el("div.card");

      box.appendChild(el("div.card-head", {}, [el("h2", { text: "Last backup" })]));
      if (!latest) {
        box.appendChild(el("p.card-note", { text: "Nothing has been backed up yet. "
          + "Press Back up now above." }));
        return box;
      }

      box.appendChild(el("div.row", { style: "align-items:center" }, [
        el("div", { style: "flex:1 1 auto" }, [
          el("div", { style: "font-size:1.02rem;font-weight:600",
                      text: latest.taken_bs + " at " + (latest.taken_ad || "").slice(11, 16) }),
          el("div", { style: "color:var(--ink-faint);font-size:.85rem;margin-top:.15rem",
                      text: latest.size_text })
        ]),
        el("button.secondary", { text: "Restore this", onclick: function () {
          restore(latest);
        }})
      ]));

      if (older.length) {
        var list = el("div", { style: "display:none;margin-top:.6rem" }, [
          UI.table(["Date", "Time", { label: "Size", num: true }, ""],
            older.map(function (item) {
              return el("tr", {}, [
                el("td", { text: item.taken_bs }),
                el("td", { text: (item.taken_ad || "").slice(11, 16),
                           style: "color:var(--ink-faint)" }),
                el("td.num", { text: item.size_text }),
                el("td.no-print", {}, [
                  el("button.link-button", { text: "Restore", onclick: function () {
                    restore(item);
                  }})
                ])
              ]);
            }), null, { tall: true })
        ]);
        var toggle = el("button.link-button", {
          text: "Show the " + older.length + " older " + (older.length === 1 ? "one" : "ones"),
          style: "margin-top:.5rem",
          onclick: function () {
            var open = list.style.display !== "none";
            list.style.display = open ? "none" : "block";
            toggle.textContent = open
              ? "Show the " + older.length + " older "
                + (older.length === 1 ? "one" : "ones")
              : "Hide the older ones";
          }
        });
        box.appendChild(toggle);
        box.appendChild(list);
      }
      return box;
    }

    function backUp(data) {
      var g = data.google || {};
      UI.confirmAction("Back up now",
        g.connected
          ? "A copy of every company goes to " + g.account + ", into "
            + (g.folder_name || "Saphal Book backups") + "."
          : "A copy of every company is saved on this computer.",
        function () {
          return api("/api/backup/create", { body: { note: "Taken by hand" } })
            .then(function (result) {
              var up = (result.backup.copies || []).filter(function (c) {
                return c.ok && c.folder === "Google Drive";
              }).length;
              UI.flash(up ? "Backed up, and sent to Google Drive."
                          : "Backed up on this computer.", "good");
              return load();
            });
        }, "Back it up");
    }

    function restore(item) {
      UI.confirmAction("Restore this backup",
        "The books go back to how they were on " + item.taken_bs
        + " at " + (item.taken_ad || "").slice(11, 16) + ".  Anything entered since "
        + "then is gone.  What is here now is saved first, so this can itself be "
        + "undone.",
        function () {
          return api("/api/backup/restore", { body: { filename: item.filename } })
            .then(function () {
              UI.flash("Restored. Reopening the books.", "good");
              setTimeout(function () { location.reload(); }, 900);
            });
        }, "Restore it");
    }
  });

  /* Audit trail */

  register("audit", function (page) {
    return api("/api/audit", { query: { limit: 400 } }).then(function (data) {
      var rows = data.rows.map(function (row) {
        return el("tr", {}, [
          el("td", { text: row.at }),
          el("td", { text: row.username }),
          el("td", {}, [el("span.pill", { text: row.action })]),
          el("td", { text: row.reference }),
          el("td", { text: row.summary })
        ]);
      });
      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Audit trail" })]),
        el("p.card-note", { text: "Every change to the books, with who made it and when. Nothing here can be edited." }),
        UI.table(["When", "Who", "Action", "Reference", "What happened"], rows, null, { tall: true })
      ]));
    });
  });

  /* Date converter */

  register("dates", function (page) {
    var bsInput = el("input", { type: "text", value: NP.formatBs(NP.adToBs(NP.todayIso()), "numeric") });
    var adInput = el("input", { type: "text", value: NP.todayIso() });
    var result = el("div.card-note", { style: "margin-top:.5rem;font-size:.9rem" });

    function fromBs() {
      var bs = NP.parseBs(bsInput.value);
      if (!bs) { result.textContent = "That is not a Bikram Sambat date this software knows."; return; }
      var iso = NP.bsToAd(bs.year, bs.month, bs.day);
      adInput.value = iso;
      show(iso);
    }
    function fromAd() {
      var iso = adInput.value.trim();
      var bs = NP.adToBs(iso);
      if (!bs) { result.textContent = "That is not a Gregorian date this software can convert."; return; }
      bsInput.value = NP.formatBs(bs, "numeric");
      show(iso);
    }
    function show(iso) {
      var bs = NP.adToBs(iso);
      var dow = NP.weekdayIndex(iso);
      var fy = NP.fiscalYearOf(iso);
      result.innerHTML = "";
      [
        NP.formatBs(bs, "long") + ", " + NP.DOW_EN[dow] + "bar",
        "Gregorian: " + new Date(iso + "T00:00:00").toDateString(),
        "Fiscal year " + fy.label + ", from " + fy.startAd + " to " + fy.endAd,
        NP.MONTHS_EN[bs.month - 1] + " " + bs.year + " has " + NP.daysInMonth(bs.year, bs.month) + " days"
      ].forEach(function (line) { result.appendChild(el("div", { text: line })); });
    }

    bsInput.addEventListener("change", fromBs);
    adInput.addEventListener("change", fromAd);

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [el("h2", { text: "Convert a date" })]),
      el("div.row", {}, [
        UI.field("Bikram Sambat", bsInput, "For example 2083-05-17"),
        UI.field("Gregorian", adInput, "For example 2026-09-02")
      ]),
      result
    ]));
    show(NP.todayIso());

    var view = NP.adToBs(NP.todayIso());
    var calendarCard = el("div.card");
    page.appendChild(calendarCard);
    drawMonth(calendarCard, view);
  });

  function drawMonth(card, view) {
    UI.clear(card);
    var head = el("div.card-head", {}, [
      el("h2", { text: NP.MONTHS_EN[view.month - 1] + " " + view.year }),
      el("div.row", {}, [
        el("button.secondary", { text: "Previous", onclick: function () { step(-1); } }),
        el("button.secondary", { text: "Next", onclick: function () { step(1); } })
      ])
    ]);
    function step(direction) {
      view.month += direction;
      if (view.month > 12) { view.month = 1; view.year++; }
      if (view.month < 1) { view.month = 12; view.year--; }
      if (!NP.daysInMonth(view.year, view.month)) { view.month -= direction; return; }
      drawMonth(card, view);
    }
    var grid = el("div.calendar-grid", { style: "gap:2px" });
    NP.DOW_EN.forEach(function (name) { grid.appendChild(el("div.dow", { text: name })); });
    var firstAd = NP.bsToAd(view.year, view.month, 1);
    for (var i = 0; i < NP.weekdayIndex(firstAd); i++) { grid.appendChild(el("div")); }
    var todayIso = NP.todayIso();
    for (var d = 1; d <= NP.daysInMonth(view.year, view.month); d++) {
      var dayIso = NP.bsToAd(view.year, view.month, d);
      var classes = "div.day";
      if (dayIso === todayIso) { classes += ".today"; }
      if (NP.weekdayIndex(dayIso) === 6) { classes += ".holiday"; }
      grid.appendChild(el(classes, {
        style: "padding:.5rem 0;line-height:1.1",
        html: "<strong>" + d + "</strong><br><span style='font-size:.62rem;color:var(--ink-faint)'>"
          + dayIso.slice(5) + "</span>"
      }));
    }
    card.appendChild(head);
    card.appendChild(grid);
    card.appendChild(el("p.card-note", { style: "margin-top:.6rem",
      text: "Saturday is shown in red. Public holidays are not built in yet." }));
  }

  /* Your account, and carrying books between devices.

     One username, held in one place, so the same name cannot be taken twice and
     signing in on a tablet reaches the same books. The books themselves stay on
     this machine; the server only carries a locked copy between devices. */

  register("cloud", function (page) {
    /* Your account.

       This screen used to be the machinery: a row for every set of books, a
       version number here and a version number there, and a Send up and a
       Bring down against each one. All of that is how it works, none of it is
       anything to do. The books go up and come down on their own.

       So there are only two things here now. Who you are signed in as, and
       whether everything is safe. The one time a person genuinely has to
       decide is when the same books were changed in two places at once, and
       that is asked as a plain question with the two answers spelled out. */

    var showWorkings = false;

    return load();

    function load() {
      // The quick answer costs nothing and never leaves this device, so the
      // screen is up straight away. The account is then asked properly, behind
      // the screen, and what it says is drawn in when it arrives.
      // Only the quick answer, which never leaves this device. Checking with
      // the account blocks the page while it waits, so it is not done on the
      // way in to a screen. Check now does it, because that is somebody asking.
      return api("/api/cloud/status", { query: { quick: "1" } }).then(draw);
    }

    function draw(state) {
      UI.clear(page);

      if (!state.configured) {
        page.appendChild(el("div.card", {}, [
          el("div.empty", { text: "No account server has been set up for these books." })
        ]));
        return;
      }
      if (!state.signed_in) { page.appendChild(gate(state)); return; }

      App.state.device = state.device;
      page.appendChild(who(state));

      var split = (App.state.conflicts || []).filter(function (row) { return row.slug; });
      if (split.length) { page.appendChild(toDecide(split, state)); }

      page.appendChild(standing(state, split.length));
      if (showWorkings) { page.appendChild(workings(state)); }
      page.appendChild(places());
    }

    function reload() {
      // After somebody has done something, the fresh answer is the whole point,
      // so this one does ask the account.
      return api("/api/cloud/status").then(draw);
    }

    function lost(error) {
      if (error && /sign in to your account/i.test(error.message || "")) {
        UI.flash("Your account needs signing in to again.", "warn");
        return reload();
      }
      UI.flash((error && error.message) || "That did not work.", "bad");
      return null;
    }

    /* Signing in */

    function gate(state) {
      var username = el("input", { type: "text", value: state.remembered || "",
                                   placeholder: "The name you sign in with" });
      var password = el("input", { type: "password", placeholder: "Your password" });

      function go(making) {
        var name = username.value.trim();
        var secret = password.value;
        if (!name || !secret) { UI.flash("Both boxes are needed.", "bad"); return; }
        if (making && secret.length < 8) {
          UI.flash("Use at least eight characters. This password also unlocks the "
                   + "books, so a short one is the weak link.", "bad");
          return;
        }
        api(making ? "/api/cloud/sign-up" : "/api/cloud/sign-in",
            { body: { username: name, password: secret } })
          .then(function () {
            password.value = "";
            UI.flash(making ? "Account opened." : "Signed in.", "good");
            return Sync.run("signed in").then(reload);
          })
          .catch(function (error) { UI.flash(error.message, "bad"); });
      }

      password.addEventListener("keydown", function (event) {
        if (event.key === "Enter") { go(false); }
      });

      return el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Your account" })]),
        el("p.card-note", { text: "The same name and password you use to open Saphal Book. "
          + "Sign in with it on a computer, a phone or a tablet and the same books are "
          + "there." }),
        el("div.row", {}, [
          el("div", { style: "flex:1 1 220px" }, [UI.field("Username", username)]),
          el("div", { style: "flex:1 1 220px" }, [UI.field("Password", password)])
        ]),
        el("div.row", {}, [
          el("button.primary", { text: "Sign in", onclick: function () { go(false); } }),
          el("button.secondary", { text: "Open a new account",
                                   onclick: function () { go(true); } })
        ]),
        el("p.card-note", { style: "margin-top:.6rem", text: "This password also unlocks "
          + "the books. Nobody can reset it, not the makers of this software and not the "
          + "company holding the copies, because none of them ever see it. Write it down "
          + "somewhere safe." })
      ]);
    }

    function who(state) {
      return el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: "Signed in as " + state.username }),
          el("button.secondary", { text: "Sign out", onclick: function () {
            UI.confirmAction("Sign out of your account",
              "The books stay on this device and go on working. They simply stop going "
              + "to and from your other devices until you sign in again.",
              function () {
                return api("/api/cloud/sign-out", { body: {} })
                  .then(function () { UI.flash("Signed out.", "warn"); return reload(); });
              }, "Sign out");
          }})
        ]),
        el("p.card-note", {}, [
          el("span", { text: "This device is called " }),
          el("strong", { text: state.device }),
          el("span", { text: ". Your other devices are shown that name when they are "
            + "told who wrote last.  " }),
          el("button.link-button", { text: "Rename", onclick: function () {
            UI.promptText("What should this device be called?",
              "Something you will recognise on another screen, like Shop counter "
              + "or Saphal iPad.",
              function (name) {
                if (!(name || "").trim()) { return; }
                return api("/api/device-name", { body: { name: name } })
                  .then(function (result) {
                    UI.flash("This device is now called " + result.device + ".", "good");
                    return reload();
                  })
                  .catch(function (error) { UI.flash(error.message, "bad"); });
              }, { value: state.device });
          }})
        ])
      ]);
    }

    /* Whether everything is safe, in one line */

    function standing(state, splitCount) {
      var books = state.books || [];
      var behind = books.filter(function (b) {
        return b.standing !== "up to date" && b.standing !== "not sent yet";
      }).length;
      var never = books.filter(function (b) { return b.standing === "not sent yet"; }).length;

      var line, tone;
      if (!books.length) {
        line = "No companies on this device yet.";
        tone = "";
      } else if (splitCount >= books.length) {
        line = "Once you have chosen above, everything is saved again.";
        tone = "";
      } else if (splitCount) {
        line = "Everything else is up to date.";
        tone = "";
      } else if (behind || never) {
        line = "Catching up.";
        tone = "";
      } else {
        line = books.length === 1
          ? "Your books are saved to your account."
          : "All " + books.length + " sets of books are saved to your account.";
        tone = "good";
      }

      return el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: "Everything you enter is kept" }),
          el("button.secondary", { text: "Check now", onclick: function () {
            return Sync.run("asked").then(reload);
          }})
        ]),
        el("div.row", { style: "align-items:center;gap:.5rem" }, [
          tone ? el("span.pill.good", { text: "Up to date" }) : null,
          el("span", { text: line })
        ]),
        el("p.card-note", { text: "This happens on its own, a few seconds after you stop "
          + "typing and whenever Saphal Book is opened. There is nothing to press." }),
        el("button.link-button", {
          text: showWorkings ? "Hide the detail" : "Show the detail",
          onclick: function () { showWorkings = !showWorkings; return reload(); }
        })
      ]);
    }

    /* A name a person will recognise.

       Older versions of the software called every browser emscripten, because
       that is the name the accounting engine gives itself inside one. Those
       names are already written down on the account and will stay there until
       that device sends its books up again, so anything that looks like one is
       turned back into plain words rather than shown as it is. */

    function friendlyDevice(name) {
      name = (name || "").trim();
      if (!name || /emscripten/i.test(name) || name === "this device") {
        return "your other device";
      }
      return name;
    }

    /* The one real decision: the same books changed in two places.

       This used to ask which copy to keep and give nothing to decide it with,
       which is not a question anybody can answer. Both copies are counted now,
       so the choice reads as: this one has 47 entries up to 20 Bhadra, that one
       has 52 up to 21 Bhadra. Then it answers itself. */

    function toDecide(split, state) {
      var card = el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: split.length === 1
            ? "One company is in two places"
            : split.length + " companies are in two places" })
        ]),
        el("p.card-note", { text: "Entries were made here and on another device without "
          + "the two meeting in between, so each holds work the other does not. Pick the "
          + "one to keep. The other is saved on this device as a spare file." })
      ]);

      split.forEach(function (row) {
        var book = (state.books || []).filter(function (b) {
          return b.slug === row.slug;
        })[0] || {};
        var block = el("div.decide", {}, [
          el("div.decide-name", { text: row.name }),
          el("div.card-note", { style: "margin:.1rem 0 .5rem", text: "Counting both copies" })
        ]);
        card.appendChild(block);

        api("/api/cloud/compare", { query: { slug: row.slug } })
          .then(function (seen) { paintChoice(block, row, book, seen); })
          .catch(function () { paintChoice(block, row, book, null); });
      });
      return card;
    }

    function describeSide(side) {
      if (!side) { return "could not be counted"; }
      var bits = [side.entries + (side.entries === 1 ? " entry" : " entries")];
      if (side.last_entry_ad) {
        bits.push("last on " + UI.bs(side.last_entry_ad, "short"));
      }
      return bits.join(", ");
    }

    function paintChoice(block, row, book, seen) {
      UI.clear(block);
      var here = seen && seen.here;
      var there = seen && seen.there;
      var other = friendlyDevice((there && there.device) || book.server_device);
      var mine = (here && here.device) || (App.state.device || "this device");

      // Say plainly which one holds more work, because that is the thing being
      // asked and nobody should have to do the subtraction themselves.
      var hint = "";
      if (here && there) {
        if (here.entries > there.entries) {
          hint = "This device has " + (here.entries - there.entries) + " more.";
        } else if (there.entries > here.entries) {
          hint = other + " has " + (there.entries - here.entries) + " more.";
        } else {
          hint = "Both have the same number of entries, so check the dates.";
        }
      }

      block.appendChild(el("div.decide-name", { text: row.name }));
      if (hint) {
        block.appendChild(el("div.card-note", { style: "margin:.1rem 0 .5rem", text: hint }));
      }
      block.appendChild(el("div.decide-pair", {}, [
        el("button.secondary", { onclick: function () { keepHere(row, book); } }, [
          el("div", { text: "Keep this one" }),
          el("small", { text: mine + "  ·  " + describeSide(here) })
        ]),
        el("button.secondary", { onclick: function () { keepThere(row, book, other); } }, [
          el("div", { text: "Keep that one" }),
          el("small", { text: other + "  ·  " + describeSide(there) })
        ])
      ]));
    }

    function keepHere(row, book) {
      UI.confirmAction("Keep this one for " + row.name,
        "What is on this device becomes the copy every device gets. Anything typed on "
        + friendlyDevice(book.server_device) + " and not typed here as well will not be "
        + "in it.",
        function () {
          return api("/api/cloud/send", { body: { slug: row.slug, force: true } })
            .then(function () {
              Sync.forget(row.slug);
              App.state.conflicts = (App.state.conflicts || []).filter(function (c) {
                return c.slug !== row.slug;
              });
              UI.flash(row.name + " is now the copy everybody gets.", "good");
              return reload();
            })
            .catch(function (error) { lost(error); return false; });
        }, "Keep this one");
    }

    function keepThere(row, book, other) {
      UI.confirmAction("Keep that one for " + row.name,
        "The copy from " + other + " replaces what is on this device. Anything typed "
        + "here and not there will not be in it. What is here now is saved as a spare "
        + "file first, so it is not lost.",
        function () {
          return api("/api/cloud/bring", { body: { slug: row.slug } })
            .then(function () {
              Sync.forget(row.slug);
              App.state.conflicts = (App.state.conflicts || []).filter(function (c) {
                return c.slug !== row.slug;
              });
              UI.flash(row.name + " now matches " + other + ". The copy that was here "
                       + "was kept on the disk.", "good");
              return refresh();
            })
            .catch(function (error) { lost(error); return false; });
        }, "Keep that one");
    }

    /* For when somebody wants to see what is actually going on */

    function workings(state) {
      var rows = (state.books || []).map(function (book) {
        var plain = { "up to date": "Saved to your account",
                      "newer on the server": "Coming down",
                      "newer here": "Going up",
                      "not sent yet": "Going up for the first time",
                      "removed from the server": "Going up again" }[book.standing]
                    || book.standing;
        return el("tr", {}, [
          el("td", {}, [
            el("div", { text: book.name }),
            book.server_device
              ? el("div", { style: "font-size:.76rem;color:var(--ink-faint)",
                            text: "last written by " + friendlyDevice(book.server_device) })
              : null
          ]),
          el("td", {}, [el("span.pill" + (book.standing === "up to date" ? ".good" : ""),
                           { text: plain })]),
          el("td.num", { text: book.version ? "v" + book.version : "" }),
          el("td.num", { text: book.server_version ? "v" + book.server_version : "" })
        ]);
      });
      return el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "The detail" })]),
        UI.table(["Books", "Standing", { label: "Here", num: true },
                  { label: "On your account", num: true }], rows, null,
                 { emptyText: "No companies on this device yet." })
      ]);
    }

    /* Where everything actually is.

       Read off the machine every time this is drawn rather than written down
       anywhere, so a folder that moves, a Drive reconnected to another account
       or a destination somebody adds shows up the moment it changes. A path
       that is right today and wrong next month is worse than no path at all. */

    function places() {
      var card = el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Where everything is kept" })]),
        el("p.card-note", { text: "Read from this device each time this screen opens, "
          + "so it is always where things actually are." })
      ]);
      var host = el("div");
      card.appendChild(host);
      host.appendChild(el("p.card-note", { text: "Looking" }));

      api("/api/where").then(function (found) {
        UI.clear(host);
        (found.places || []).forEach(function (spot) {
          var line = el("div.place", {}, [
            el("div.place-what", {}, [
              el("span", { text: spot.what }),
              spot.exists ? null
                : el("span.pill.warn", { text: "not there at the moment" })
            ]),
            el("code.place-where", { text: spot.where })
          ]);
          if (spot.note) {
            line.appendChild(el("div.card-note", { style: "margin:.15rem 0 0",
                                                   text: spot.note }));
          }
          // One row, one kind of control. A button and a link styled to look
          // alike still do not sit alike, because one carries a baseline the
          // other does not, and that is the small crookedness that makes a
          // screen look unfinished.
          var actions = el("div.place-actions.no-print");
          if (spot.can_open && spot.exists) {
            actions.appendChild(el("button.place-action", {
              text: "Show me", onclick: function () {
                return api("/api/where/open", { body: { path: spot.where } })
                  .catch(function (error) { UI.flash(error.message, "bad"); });
              }}));
          }
          if (spot.link) {
            actions.appendChild(el("button.place-action", {
              text: "Open in Drive", onclick: function () {
                window.open(spot.link, "_blank", "noopener");
              }}));
          }
          if (spot.where && (spot.can_open || spot.link)) {
            actions.appendChild(el("button.place-action", {
              text: spot.link ? "Copy the link" : "Copy the path",
              onclick: function (event) {
                UI.copyText(spot.link || spot.where, event.currentTarget);
              }}));
          }
          if (actions.childNodes.length) { line.appendChild(actions); }
          host.appendChild(line);
        });

      }).catch(function (error) {
        UI.clear(host);
        host.appendChild(el("p.card-note", { text: error.message }));
      });
      return card;
    }

  });

  /* Use on your phone */

  register("devices", function (page) {
    // In the browser version there is no server on a wifi, so an address to
    // type would be a fiction. Signing in with the same name is the answer
    // there, and it is the better answer everywhere.
    if (window.CHARTERED_BOOK_WEB) {
      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Use these books on another device" })]),
        el("p.card-note", { text: "Open Saphal Book on the other device and sign in with "
          + "the same name. The books come down by themselves." }),
        el("p.card-note", { text: "Work on one device at a time. A device that has been "
          + "away is told so rather than allowed to write over newer work." })
      ]));
      return;
    }

    return api("/api/network").then(function (net) {
      var address = net.urls.length ? net.urls[0].replace(/\/$/, "") : "";

      var card = el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Use these books on a phone or tablet" })])
      ]);

      if (!address) {
        card.appendChild(el("p.card-note", { text: "This computer is not on a network at "
          + "the moment, so there is no address to give the phone. Connect it to the wifi "
          + "and come back." }));
      } else {
        card.appendChild(el("p.card-note", { text: "On the phone, open Safari or Chrome and "
          + "type this. Once only." }));
        card.appendChild(el("div.address", {}, [
          el("code", { text: address }),
          el("button.secondary", { text: "Copy", onclick: function (event) {
            UI.copyText(address, event.currentTarget);
          }})
        ]));
        if (net.urls.length > 1) {
          card.appendChild(el("p.card-note", { text: "If it does not open, try "
            + net.urls.slice(1).map(function (u) { return u.replace(/\/$/, ""); })
                .join(" or ") + "." }));
        }
        card.appendChild(el("p.card-note", { text: "This computer has to be switched on "
          + "with Saphal Book open. Nothing goes over the internet." }));
      }

      if (address && !net.listening_on_network) {
        card.appendChild(el("div.flash.warn", { style: "margin:.6rem 0 0", text:
          "Saphal Book is only answering this computer. Open it from the Saphal Book icon "
          + "rather than from a terminal and it will answer the wifi too." }));
      }
      page.appendChild(card);

      if (address) {
        page.appendChild(el("div.card", {}, [
          el("div.card-head", {}, [el("h2", { text: "Keep it with the other apps" })]),
          el("p.card-note", { text: "iPhone or iPad: open the address in Safari, tap Share, "
            + "then Add to Home Screen. Chrome on an iPad cannot do this part." }),
          el("p.card-note", { text: "Android: open it in Chrome, tap the three dots, then "
            + "Install app." }),
          el("p.card-note", { text: "Windows: open it in Edge or Chrome and choose Install "
            + "Saphal Book from the menu." })
        ]));
      }

      if (canInstall()) {
        page.appendChild(el("div.card", {}, [
          el("div.install-bar", { style: "margin:0" }, [
            el("span", { text: "This browser can install Saphal Book right now." }),
            el("button.primary", { text: "Install on this device", onclick: function () {
              runInstall().then(function (yes) {
                if (yes) {
                  UI.flash("Installed. Look for the icon with your other apps.", "good");
                }
              });
            }})
          ])
        ]));
      }

      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Who can reach it" })]),
        el("p.card-note", { text: "Anyone on the same wifi reaches the sign in screen and "
          + "no further. Eight wrong attempts locks the account for fifteen minutes." }),
        el("p.card-note", { text: "Give each person their own login under Users. That is "
          + "what makes the audit trail say who did what." })
      ]));
    });
  });

  /* Notes and rules */

  register("guide", function (page) {
    var sections = [
      ["How the books are kept", [
        "Every amount is stored as a whole number of paisa, so the trial balance always ties exactly.",
        "Every voucher must balance before it can be saved. Debit and credit are checked to the paisa.",
        "A posted voucher is never deleted. It is cancelled, keeping the number and recording who cancelled it and why, so a gap in an invoice series can always be explained.",
        "Stock is kept on the periodic basis. A sales invoice does not post cost of goods sold. The stock ledger records every movement, and the closing stock entry brings the value into the accounts at period end."
      ]],
      ["Value added tax", [
        "The standard rate is 13 percent under the Value Added Tax Act, 2052.",
        "Sales VAT collects into account 2241 VAT Output Payable. Purchase VAT collects into 1241 VAT Input Credit.",
        "The monthly return sets input against output. The balance is either payable or carried forward as credit.",
        "A return for a Nepali month is due by the 25th of the following month. The VAT screen shows the date for the month you are looking at.",
        "Registration is compulsory once turnover crosses the threshold set by the Finance Act. Check the current threshold before relying on it."
      ]],
      ["Tax deducted at source", [
        "Rent paid to a natural person, 10 percent under section 88.",
        "Service fee, consultancy and professional fee, 15 percent under section 88.",
        "Service fee paid to a person registered for VAT, 1.5 percent.",
        "Contract or agreement payment above the threshold, 1.5 percent under section 89.",
        "Commission, 15 percent. Dividend paid by a resident company, 5 percent.",
        "Rates change with each Finance Act. Confirm the rate for the year before filing."
      ]],
      ["Dates and the fiscal year", [
        "The fiscal year runs from 1 Shrawan to the last day of Ashadh.",
        "Dates are typed in Bikram Sambat and stored in both calendars. Press plus or minus in a date box to move a day, Page Up or Page Down for a week, and F4 for the calendar.",
        "The calendar covers Bikram Sambat 2000 to 2099."
      ]],
      ["Keeping the data safe", [
        "The books live in the data folder beside this software. One file for each company.",
        "Take a backup regularly and copy the zip somewhere else. A backup on the same disk protects you from a mistake, not from the disk failing.",
        "Restoring takes a safety copy of the present state first, so a restore done by mistake can be undone."
      ]],
      ["Keyboard", [
        "F1 dashboard, F5 sales, F6 purchase, F7 receipt, F8 payment, F9 journal.",
        "F2 opens the calculator. Ctrl and P prints the screen.",
        "Amount boxes accept arithmetic. Type 12*450 and it works the answer out when you leave the box."
      ]]
    ];
    sections.forEach(function (section) {
      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: section[0] })]),
        el("ul", { style: "margin:0;padding-left:1.1rem" }, section[1].map(function (line) {
          return el("li", { text: line, style: "margin-bottom:.3rem" });
        }))
      ]));
    });
  });

  return {
    Sync: Sync,
    start: start, go: go, register: register, state: state, refresh: refresh,
    loadLookups: loadLookups, openCompanyForm: openCompanyForm,
    openCompanyChooser: openCompanyChooser, canInstall: canInstall, runInstall: runInstall,
    buildMenu: buildMenu
  };
}());

// On a computer the screens can start as soon as the page is parsed. In a
// browser build the accounting engine has to finish loading first, so the boot
// script says when.
if (window.CHARTERED_BOOK_WEB) {
  document.addEventListener("saphal-book-ready", App.start);
} else {
  document.addEventListener("DOMContentLoaded", App.start);
}
