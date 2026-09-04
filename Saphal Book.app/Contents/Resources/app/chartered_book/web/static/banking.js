/* Cash, bank accounts and reconciliation.

   Reconciling never changes a figure in the books. Ticking a line only records
   that the bank has dealt with it, which is what turns an unexplained
   difference into a list of items anyone can check. */

var Banking = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  /* Cash and bank */

  App.register("banking", function (page) {
    var box = el("div");

    function load() {
      return api("/api/banking/accounts").then(function (data) {
        var cash = data.position.cash;
        var bank = data.position.bank;
        UI.clear(box);
        box.appendChild(el("div.grid.three", {}, [
          tile("Cash in hand", UI.rs(cash), "Across every cash box"),
          tile("At the bank", UI.rs(bank), "Across every account"),
          tile("Total on hand", UI.rs(data.position.total), "As at " + UI.bs(data.as_at, "long"),
               data.position.total >= 0 ? "good" : "bad")
        ]));

        var rows = data.rows.map(function (account) {
          return el("tr.clickable", { onclick: function () { Reports.openLedger(account.id); } }, [
            el("td", { text: account.code }),
            el("td", {}, [
              el("div", { text: account.name }),
              account.bank_name || account.bank_account_no
                ? el("div.muted", { style: "font-size:.75rem", text:
                    [account.bank_name, account.bank_account_no, account.bank_branch]
                      .filter(Boolean).join("  ") })
                : null
            ]),
            el("td", {}, [el("span.pill" + (account.account_kind === "cash" ? ".warn" : ".brand"),
              { text: account.account_kind })]),
            el("td.num", { text: UI.rs(account.balance) }),
            el("td.num", { text: account.uncleared ? UI.rs(account.uncleared) : "" }),
            el("td.no-print", {}, [
              account.account_kind === "bank"
                ? el("button.link-button", { text: "Reconcile", onclick: function (event) {
                    event.stopPropagation();
                    App.state.pendingRecon = account.id;
                    App.go("reconcile");
                  }})
                : null
            ])
          ]);
        });

        box.appendChild(el("div.card", { style: "margin-top:.9rem" }, [
          el("div.card-head", {}, [
            el("h2", { text: "Cash boxes and bank accounts" }),
            el("div.row", {}, [
              el("button.secondary", { text: "Add a cash box",
                onclick: function () { openAccountForm("cash"); } }),
              el("button.secondary", { text: "Add an overdraft",
                onclick: function () { openAccountForm("overdraft"); } }),
              el("button.primary", { text: "Add a bank account",
                onclick: function () { openAccountForm("bank"); } })
            ])
          ]),
          UI.table([
            "Code", "Account", "Kind",
            { label: "Balance in books", num: true },
            { label: "Not yet cleared", num: true },
            { label: "", num: false }
          ], rows, null, {
            emptyText: "No cash or bank accounts yet. Add the ones this business uses."
          })
        ]));
      });
    }

    page.appendChild(box);
    return load();
  });

  function tile(label, value, note, kind) {
    return el("div.tile" + (kind ? "." + kind : ""), {}, [
      el("div.tile-label", { text: label }),
      el("div.tile-value", { text: value }),
      note ? el("div.tile-note", { text: note }) : null
    ]);
  }

  function openAccountForm(kind, options) {
    options = options || {};
    var titles = { bank: "New bank account", cash: "New cash box", overdraft: "New overdraft" };
    var name = el("input", { type: "text", value: options.presetName || "",
      placeholder: kind === "bank" ? "Nabil Bank, current account" : "" });
    var bankName = el("input", { type: "text" });
    var bankAccount = el("input", { type: "text" });
    var bankBranch = el("input", { type: "text" });
    var opening = UI.amountInput("");
    var openingSide = UI.select([
      { value: "dr", label: kind === "overdraft" ? "Debit, in credit" : "Debit, money held" },
      { value: "cr", label: kind === "overdraft" ? "Credit, money owed" : "Credit, overdrawn" }
    ], kind === "overdraft" ? "cr" : "dr");
    var notes = el("textarea", { rows: "2" });

    var bankBlock = el("div", {}, [
      el("div.row", {}, [
        UI.field("Bank name", bankName),
        UI.field("Account number", bankAccount),
        UI.field("Branch", bankBranch)
      ])
    ]);
    if (kind === "cash") { bankBlock.style.display = "none"; }

    UI.modal(titles[kind] || "New account", el("div", {}, [
      el("p.card-note", { text: kind === "cash"
        ? "A cash box is money physically held, such as the counter float or petty cash."
        : kind === "overdraft"
        ? "An overdraft is money the bank has lent, so it sits among the liabilities rather than the assets."
        : "This creates the ledger and puts it under Bank Balances, ready to reconcile." }),
      UI.field("Name", name),
      bankBlock,
      el("div.row", {}, [
        UI.field("Opening balance", opening, "The balance on the day the books begin"),
        UI.field("Side", openingSide)
      ]),
      UI.field("Notes", notes)
    ]), [
      { label: "Cancel" },
      { label: "Add", kind: "primary", action: function () {
        if (!name.value.trim()) { UI.flash("Give the account a name.", "bad"); return false; }
        return api("/api/banking/accounts/create", { body: {
          name: name.value.trim(), kind: kind,
          bank_name: bankName.value.trim(), bank_account_no: bankAccount.value.trim(),
          bank_branch: bankBranch.value.trim(),
          opening: opening.value || 0, opening_side: openingSide.value,
          notes: notes.value.trim()
        }}).then(function (made) {
          UI.flash(name.value.trim() + " added.", "good");
          if (options.onSaved) {
            return api("/api/accounts/" + made.id).then(function (data) {
              options.onSaved(data.account);
            });
          }
          App.go("banking");
        });
      }}
    ]);
  }

  /* Reconciliation */

  App.register("reconcile", function (page) {
    var accountInput = el("input", { type: "text", placeholder: "Choose a bank account" });
    var accountId = App.state.pendingRecon || null;
    App.state.pendingRecon = null;
    var dateField = UI.dateField(NP.todayIso(), function () { if (accountId) { load(); } });
    var statementBalance = UI.amountInput("", { onChange: function () { redrawSummary(); } });
    var box = el("div", {}, [el("div.empty", {}, [
      el("strong", { text: "Choose an account" }),
      el("span", { text: "Pick the bank account, enter the closing balance from the statement, then tick off what the bank has dealt with." })
    ])]);
    var current = null;

    UI.attachPicker(accountInput, function (term) {
      return api("/api/banking/accounts").then(function (data) {
        return data.rows.filter(function (row) {
          return row.account_kind === "bank"
            && (!term || row.name.toLowerCase().indexOf(term.toLowerCase()) >= 0);
        });
      });
    }, function (account) {
      accountId = account.id;
      accountInput.value = account.name;
      load();
    }, function (account) {
      return { main: account.name, side: UI.rs(account.balance) };
    }, {
      createLabel: "Add bank account",
      onCreate: function (typed, done) {
        openAccountForm("bank", { presetName: typed, onSaved: done });
      }
    });

    function load() {
      return api("/api/banking/reconciliation", { query: {
        account_id: accountId, statement_date_ad: dateField.getIso()
      }}).then(function (data) {
        current = data;
        accountInput.value = data.account.name;
        draw();
      });
    }

    function draw() {
      UI.clear(box);
      var data = current;
      box.appendChild(el("div.grid.two", {}, [summaryCard(), historyCard()]));

      var rows = data.lines.map(function (line) {
        var tick = el("input", { type: "checkbox" });
        tick.checked = line.cleared;
        tick.addEventListener("change", function () {
          var body = { entry_ids: [line.entry_id], account_id: data.account.id,
                       cleared_ad: tick.checked ? dateField.getIso() : "" };
          api("/api/banking/clear", { body: body }).then(function () {
            line.cleared = tick.checked;
            line.cleared_ad = tick.checked ? dateField.getIso() : "";
            recompute();
          }).catch(function (error) {
            tick.checked = !tick.checked;
            UI.flash(error.message, "bad");
          });
        });
        var row = el("tr" + (line.cleared ? ".is-cleared" : ""), {}, [
          el("td.mid", {}, [tick]),
          el("td", { text: UI.bs(line.date_ad, "short") }),
          el("td", {}, [el("button.link-button", { text: line.number,
            onclick: function () { Vouchers.view(line.voucher_id); } })]),
          el("td", { text: line.instrument_no || "" }),
          el("td", { text: line.party_name || line.particulars, style: "max-width:260px" }),
          el("td.num", { text: UI.rs(line.dr, { blankZero: true }) }),
          el("td.num", { text: UI.rs(line.cr, { blankZero: true }) })
        ]);
        line.node = row;
        return row;
      });

      box.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: "Entries up to the statement date" }),
          el("div.row.no-print", {}, [
            el("button.secondary", { text: "Tick everything", onclick: function () { bulk(true); } }),
            el("button.secondary", { text: "Untick everything", onclick: function () { bulk(false); } })
          ])
        ]),
        el("p.card-note", { text: "Tick a line once it appears on the bank statement. What stays unticked is exactly what explains the difference." }),
        UI.table([
          { label: "Cleared", mid: true }, "Date", "Voucher", "Cheque or reference", "Particulars",
          { label: "Paid in", num: true }, { label: "Paid out", num: true }
        ], rows, null, { tall: true, emptyText: "Nothing has gone through this account yet." })
      ]));
    }

    function bulk(state) {
      var ids = current.lines
        .filter(function (line) { return line.cleared !== state; })
        .map(function (line) { return line.entry_id; });
      if (!ids.length) { return; }
      api("/api/banking/clear", { body: {
        entry_ids: ids, account_id: current.account.id,
        cleared_ad: state ? dateField.getIso() : ""
      }}).then(function () { load(); })
        .catch(function (error) { UI.flash(error.message, "bad"); });
    }

    function recompute() {
      var depositsOut = 0, paymentsOut = 0;
      current.lines.forEach(function (line) {
        if (line.node) { line.node.className = line.cleared ? "is-cleared" : ""; }
        if (!line.cleared) { depositsOut += line.dr; paymentsOut += line.cr; }
      });
      current.uncleared_deposits = depositsOut;
      current.uncleared_payments = paymentsOut;
      current.implied_statement_balance = current.book_balance - depositsOut + paymentsOut;
      current.cleared_count = current.lines.filter(function (l) { return l.cleared; }).length;
      current.uncleared_count = current.lines.length - current.cleared_count;
      redrawSummary();
    }

    /* The working is built once and then only its numbers are changed. An
       earlier version rebuilt it on every keystroke, which pulled the box being
       typed in out of the page underneath the cursor. */

    var summaryNodes = {};
    var summaryBody = el("div.recon-summary");
    var summaryBuilt = false;

    function buildSummary() {
      UI.clear(summaryBody);
      summaryNodes = {};
      summaryNodes.book = line("Balance as per our books");
      summaryNodes.deposits = line("Less deposits the bank has not credited yet");
      summaryNodes.payments = line("Add cheques issued that are not presented yet");
      summaryNodes.implied = line("Balance the statement should show", "rule");
      summaryBody.appendChild(el("div", { style: "margin:.6rem 0 .2rem" }, [
        UI.field("Closing balance on the bank statement", statementBalance)
      ]));
      summaryNodes.difference = line("Still to be explained");
      summaryNodes.differenceRow = summaryNodes.difference.parentNode;

      summaryNodes.saveButton = el("button.secondary", { text: "Save progress",
        onclick: function () { save(false); } });
      summaryNodes.doneButton = el("button.primary", { text: "Mark it reconciled",
        onclick: function () { save(true); } });
      summaryBody.appendChild(el("div.row", { style: "margin-top:.7rem" }, [
        summaryNodes.saveButton, summaryNodes.doneButton,
        el("button.secondary.no-print", { text: "Print", onclick: UI.printPage }),
      UI.exportButton()
      ]));
      summaryNodes.counts = el("p.card-note", { style: "margin-top:.5rem" });
      summaryBody.appendChild(summaryNodes.counts);
      summaryBuilt = true;
    }

    function line(label, kind) {
      var value = el("span.num");
      summaryBody.appendChild(el("div.line" + (kind ? "." + kind : ""), {}, [
        el("span", { text: label }), value
      ]));
      return value;
    }

    function summaryCard() {
      if (!summaryBuilt) { buildSummary(); }
      redrawSummary();
      return el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "The working" })]),
        summaryBody
      ]);
    }

    function redrawSummary() {
      if (!current || !summaryBuilt) { return; }
      summaryNodes.book.textContent = UI.rs(current.book_balance);
      summaryNodes.deposits.textContent = UI.rs(-current.uncleared_deposits);
      summaryNodes.payments.textContent = UI.rs(current.uncleared_payments);
      summaryNodes.implied.textContent = UI.rs(current.implied_statement_balance);

      var typed = String(statementBalance.value || "").trim();
      var stated = NP.toPaisa(typed || 0);
      var difference = stated - current.implied_statement_balance;
      var row = summaryNodes.differenceRow;
      if (!typed) {
        row.style.display = "none";
      } else {
        row.style.display = "";
        row.className = "line " + (difference === 0 ? "match" : "off");
        row.firstChild.textContent = difference === 0 ? "It agrees" : "Still to be explained";
        summaryNodes.difference.textContent = UI.rs(difference);
      }
      summaryNodes.doneButton.disabled = !typed || difference !== 0;
      summaryNodes.counts.textContent = current.cleared_count + " cleared, "
        + current.uncleared_count + " still outstanding.";
    }

    function historyCard() {
      var wrap = el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Earlier reconciliations" })]),
        el("div.empty", { text: "None yet." })
      ]);
      api("/api/banking/history", { query: { account_id: accountId } }).then(function (data) {
        UI.clear(wrap);
        wrap.appendChild(el("div.card-head", {}, [el("h2", { text: "Earlier reconciliations" })]));
        var rows = data.rows.map(function (row) {
          return el("tr", {}, [
            el("td", { text: UI.bs(row.statement_date_ad, "short") }),
            el("td.num", { text: UI.rs(row.statement_balance) }),
            el("td.num", { text: UI.rs(row.book_balance) }),
            el("td", {}, [el("span.pill" + (row.status === "completed" ? ".good" : ".warn"),
              { text: row.status })]),
            el("td.muted", { text: row.created_by, style: "font-size:.76rem" })
          ]);
        });
        wrap.appendChild(UI.table([
          "Statement date", { label: "Per statement", num: true },
          { label: "Per books", num: true }, "Status", "By"
        ], rows, null, { emptyText: "None yet for this account." }));
      });
      return wrap;
    }

    function save(complete) {
      api("/api/banking/reconciliation/save", { body: {
        account_id: accountId, statement_date_ad: dateField.getIso(),
        statement_balance: statementBalance.value || 0, complete: complete ? 1 : 0
      }}).then(function () {
        UI.flash(complete ? "Reconciled and recorded." : "Progress saved.", "good");
        load();
      }).catch(function (error) { UI.flash(error.message, "bad"); });
    }

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [el("h2", { text: "Bank reconciliation" })]),
      el("div.toolbar", {}, [
        el("div.field", { style: "flex:1 1 250px;margin:0" }, [
          el("label", { text: "Account" }), accountInput
        ]),
        UI.field("Statement date", dateField)
      ])
    ]));
    page.appendChild(box);

    if (accountId) { return load(); }
  });

  return { openAccountForm: openAccountForm };
}());
