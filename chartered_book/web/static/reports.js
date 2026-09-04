/* Reports. Every one of these reads the books and changes nothing. */

var Reports = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  function periodBar(onChange, options) {
    options = options || {};
    var fy = App.state.fiscalYear || {};
    var fromField = UI.dateField(options.from || fy.start_ad || NP.todayIso());
    var toField = UI.dateField(options.to || (fy.end_ad || NP.todayIso()));
    var quick = UI.select([
      { value: "", label: "Choose a period" },
      { value: "fy", label: "This fiscal year" },
      { value: "month", label: "This Nepali month" },
      { value: "quarter", label: "Last three months" },
      { value: "today", label: "Today" }
    ], "");

    quick.addEventListener("change", function () {
      var today = NP.todayIso();
      var bs = NP.adToBs(today);
      if (quick.value === "fy") {
        fromField.setIso(fy.start_ad); toField.setIso(fy.end_ad);
      } else if (quick.value === "month") {
        fromField.setIso(NP.bsToAd(bs.year, bs.month, 1));
        toField.setIso(NP.bsToAd(bs.year, bs.month, NP.daysInMonth(bs.year, bs.month)));
      } else if (quick.value === "quarter") {
        fromField.setIso(NP.addDays(today, -90)); toField.setIso(today);
      } else if (quick.value === "today") {
        fromField.setIso(today); toField.setIso(today);
      }
      if (quick.value) { onChange(); }
    });
    fromField.input.addEventListener("change", function () { setTimeout(onChange, 10); });
    toField.input.addEventListener("change", function () { setTimeout(onChange, 10); });

    var bar = el("div.toolbar", {}, [
      UI.field(options.singleDate ? "As at" : "From", options.singleDate ? toField : fromField),
      options.singleDate ? null : UI.field("To", toField),
      UI.field("Quick pick", quick),
      el("div.spacer"),
      el("button.secondary.no-print", { text: "Print", onclick: UI.printPage }),
      UI.exportButton()
    ]);
    bar.from = fromField;
    bar.to = toField;
    return bar;
  }

  function reportHead(title, subtitle) {
    var company = App.state.company || {};
    return el("div.report-head", {}, [
      el("div.company", { text: company.name || "" }),
      company.address ? el("div.period", { text: [company.address, company.city].filter(Boolean).join(", ") }) : null,
      el("div.title", { text: title }),
      el("div.period", { text: subtitle })
    ]);
  }

  function periodText(from, to) {
    return "For the period " + UI.bs(from, "long") + " to " + UI.bs(to, "long")
      + "   (" + from + " to " + to + ")";
  }

  /* Trial balance */

  App.register("trial-balance", function (page) {
    var box = el("div");
    var drillHost = el("div");
    var includeZero = el("input", { type: "checkbox" });
    var bar = periodBar(load);
    bar.insertBefore(el("label", {
      style: "font-size:.78rem;display:flex;gap:.3rem;align-items:center;padding-bottom:.4rem"
    }, [includeZero, el("span", { text: "Show ledgers with no movement" })]), bar.lastChild);
    includeZero.addEventListener("change", load);

    function load() {
      return api("/api/reports/trial-balance", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso(),
        include_zero: includeZero.checked ? "1" : ""
      }}).then(function (data) {
        var rows = data.rows.map(function (row) {
          return el("tr.openable", {
            onclick: function () { Drill.openLedger(row.account_id, row.name); }
          }, [
            el("td", { text: row.code }),
            el("td", { text: row.name }),
            el("td", { text: row.group_name, style: "font-size:.76rem;color:var(--ink-faint)" }),
            el("td.num", { text: UI.rs(row.opening_dr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(row.opening_cr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(row.period_dr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(row.period_cr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(row.closing_dr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(row.closing_cr, { blankZero: true }) })
          ]);
        });
        var t = data.totals;
        var foot = [el("tr.total-row", {}, [
          el("td", { colspan: "3", text: "Total" }),
          el("td.num", { text: UI.rs(t.opening_dr) }), el("td.num", { text: UI.rs(t.opening_cr) }),
          el("td.num", { text: UI.rs(t.period_dr) }), el("td.num", { text: UI.rs(t.period_cr) }),
          el("td.num", { text: UI.rs(t.closing_dr) }), el("td.num", { text: UI.rs(t.closing_cr) })
        ])];

        UI.clear(box);
        box.appendChild(reportHead("Trial Balance", periodText(data.from_ad, data.to_ad)));
        box.appendChild(el("div" + (data.balanced ? "" : ".flash.bad"), {
          text: data.balanced ? "" : "The trial balance does not tie. Something has bypassed the posting engine. Check the audit trail.",
          style: data.balanced ? "display:none" : "margin-bottom:.6rem;padding:.5rem"
        }));
        box.appendChild(UI.table([
          "Code", "Ledger", "Group",
          { label: "Opening Dr", num: true }, { label: "Opening Cr", num: true },
          { label: "Debit", num: true }, { label: "Credit", num: true },
          { label: "Closing Dr", num: true }, { label: "Closing Cr", num: true }
        ], rows, foot, { tall: true }));
        box.appendChild(el("p.card-note", { style: "margin-top:.6rem",
          text: "Click any ledger to open it month by month, then a month to see the vouchers." }));
        box.appendChild(drillHost);
        Drill.mount(drillHost);
        Drill.setPeriod(data.from_ad, data.to_ad);
        if (data.balanced) {
          box.appendChild(el("p.card-note", { style: "text-align:center;margin-top:.6rem",
            text: "Debit and credit agree exactly." }));
        }
      });
    }

    page.appendChild(el("div.card", {}, [bar, box]));
    return load();
  });

  /* Ledger */

  App.register("ledger", function (page) {
    var accountInput = el("input", { type: "text", placeholder: "Type a ledger name" });
    var accountId = null;
    var box = el("div", {});
    var bar = periodBar(function () { if (accountId) { load(); } else { index(); } });

    UI.attachPicker(accountInput, function (term) {
      return api("/api/accounts", { query: { q: term } }).then(function (d) { return d.rows; });
    }, function (account) {
      accountId = account.id;
      accountInput.value = account.name;
      load();
    }, function (account) { return { main: account.name, side: account.group_name }; });

    /* Every ledger, with what it is carrying, shown straight away.

       Having to know the name of a ledger before being allowed to see anything
       is no use when the whole point is to look through the books. This is the
       list, grouped the way the chart of accounts is grouped, and clicking any
       line opens that ledger. */

    function index() {
      return api("/api/reports/trial-balance", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
      }}).then(function (data) {
        var rows = [];
        var group = null;
        data.rows.forEach(function (row) {
          if (row.group_code !== group) {
            group = row.group_code;
            rows.push(el("tr.group-row", {}, [
              el("td", { colspan: "5", text: row.group_name })
            ]));
          }
          var closing = row.closing_dr - row.closing_cr;
          rows.push(el("tr.clickable", { onclick: function () {
            accountId = row.account_id;
            accountInput.value = row.name;
            load();
          } }, [
            el("td", { text: row.code }),
            el("td", { text: row.name }),
            el("td.num", { text: UI.rs(row.period_dr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(row.period_cr, { blankZero: true }) }),
            el("td.num", { text: closing
              ? UI.rs(Math.abs(closing)) + (closing > 0 ? " Dr" : " Cr") : "" })
          ]));
        });
        UI.clear(box);
        box.appendChild(reportHead("Ledgers",
          periodText(data.from_ad, data.to_ad)
          + "   Click any ledger to open its statement"));
        box.appendChild(UI.table(
          ["Code", "Ledger", { label: "Debit", num: true }, { label: "Credit", num: true },
           { label: "Closing", num: true }],
          rows, [el("tr.total-row", {}, [
            el("td", { colspan: "2", text: "Total" }),
            el("td.num", { text: UI.rs(data.totals.period_dr) }),
            el("td.num", { text: UI.rs(data.totals.period_cr) }),
            el("td.num", { text: "" })
          ])], { tall: true, emptyText: "No ledgers have moved in this period." }));
      });
    }

    function load() {
      return api("/api/reports/ledger", { query: {
        account_id: accountId, from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
      }}).then(function (data) {
        var rows = [el("tr.total-row", {}, [
          el("td", { colspan: "5", text: "Opening balance" }),
          el("td.num", { text: "" }), el("td.num", { text: "" }),
          el("td.num", { text: UI.rs(Math.abs(data.opening)) + (data.opening >= 0 ? " Dr" : " Cr") })
        ])];
        data.lines.forEach(function (line) {
          rows.push(el("tr.clickable", { onclick: function () { Vouchers.view(line.voucher_id); } }, [
            el("td", { text: UI.bs(line.date_ad, "short") }),
            el("td", { text: line.date_ad, style: "font-size:.74rem;color:var(--ink-faint)" }),
            el("td", { text: line.number }),
            el("td", { text: line.particulars || "", style: "max-width:260px" }),
            el("td", { text: line.narration || "", style: "font-size:.76rem;color:var(--ink-faint);max-width:200px" }),
            el("td.num", { text: UI.rs(line.dr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(line.cr, { blankZero: true }) }),
            el("td.num", { text: UI.rs(Math.abs(line.balance)) + (line.balance >= 0 ? " Dr" : " Cr") })
          ]));
        });
        var foot = [el("tr.total-row", {}, [
          el("td", { colspan: "5", text: "Closing balance" }),
          el("td.num", { text: UI.rs(data.total_dr) }),
          el("td.num", { text: UI.rs(data.total_cr) }),
          el("td.num", { text: UI.rs(Math.abs(data.closing)) + (data.closing >= 0 ? " Dr" : " Cr") })
        ])];
        UI.clear(box);
        box.appendChild(el("div.row.no-print", { style: "margin-bottom:.4rem" }, [
          el("button.ghost", { text: "Back to all ledgers", onclick: function () {
            accountId = null;
            accountInput.value = "";
            index();
          } })
        ]));
        box.appendChild(reportHead("Ledger: " + data.account.name, periodText(data.from_ad, data.to_ad)));
        box.appendChild(UI.table([
          "Date (BS)", "Date (AD)", "Voucher", "Particulars", "Note",
          { label: "Debit", num: true }, { label: "Credit", num: true }, { label: "Balance", num: true }
        ], rows, foot, { tall: true, emptyText: "No entries in this period." }));
      });
    }

    page.appendChild(el("div.card", {}, [
      el("div.toolbar", {}, [
        el("div.field", { style: "flex:1 1 260px;margin:0" }, [
          el("label", { text: "Ledger" }), accountInput
        ])
      ]),
      bar, box
    ]));

    if (App.state.pendingLedger) {
      accountId = App.state.pendingLedger;
      App.state.pendingLedger = null;
      return api("/api/accounts/" + accountId).then(function (data) {
        accountInput.value = data.account.name;
        return load();
      });
    }
    return index();
  });

  function openLedger(accountId) {
    App.state.pendingLedger = accountId;
    App.go("ledger");
  }

  /* Profit and loss */

  App.register("profit-loss", function (page) {
    var box = el("div");
    var bar = periodBar(load);

    function load() {
      return api("/api/reports/profit-loss", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
      }}).then(function (data) {
        var rows = [];
        function section(label, key, sign) {
          var bucket = data.sections[key];
          if (!bucket) { return; }
          rows.push(el("tr.group-row", {}, [el("td", { colspan: "2", text: label }), el("td.num")]));
          Object.keys(bucket.groups).sort(function (a, b) {
            return bucket.groups[a].sort - bucket.groups[b].sort;
          }).forEach(function (code) {
            var group = bucket.groups[code];
            group.lines.sort(function (a, b) { return a.code < b.code ? -1 : 1; });
            group.lines.forEach(function (line) {
              rows.push(el("tr.clickable", { onclick: function () { openLedger(line.account_id); } }, [
                el("td", { text: line.code, style: "width:70px;color:var(--ink-faint)" }),
                el("td.indent", { text: line.name }),
                el("td.num", { text: UI.rs(line.amount) })
              ]));
            });
          });
          rows.push(el("tr.total-row", {}, [
            el("td", { colspan: "2", text: "Total " + label.toLowerCase() }),
            el("td.num", { text: UI.rs(bucket.total) })
          ]));
        }
        function summary(label, value, strong) {
          rows.push(el("tr" + (strong ? ".total-row" : ""), {}, [
            el("td", { colspan: "2", text: label, style: strong ? "font-weight:700" : "font-weight:600" }),
            el("td.num", { text: UI.rs(value), style: strong ? "font-weight:700" : "font-weight:600" })
          ]));
        }

        section("Revenue from operations", "revenue");
        section("Cost of sales", "cost_of_sales");
        summary("Gross profit", data.gross_profit, true);
        section("Other income", "other_income");
        section("Employee benefit expenses", "employee");
        section("Administrative expenses", "administrative");
        section("Selling and distribution expenses", "selling");
        summary("Operating profit", data.operating_profit, true);
        section("Finance costs", "finance");
        section("Depreciation and amortisation", "depreciation");
        section("Other expenses", "other_expense");
        summary("Profit before tax", data.profit_before_tax, true);
        section("Tax expense", "tax");
        summary("Profit for the period", data.profit_after_tax, true);

        UI.clear(box);
        box.appendChild(reportHead("Statement of Profit or Loss", periodText(data.from_ad, data.to_ad)));
        box.appendChild(UI.table(["Code", "Particulars", { label: "Amount", num: true }],
          rows, null, { emptyText: "Nothing has been posted in this period." }));
        box.appendChild(el("p.card-note", { style: "margin-top:.7rem", text:
          "Closing stock is not included until the closing stock entry is passed. Until then the cost of sales figure shows purchases in full." }));
      });
    }

    page.appendChild(el("div.card", {}, [bar, box]));
    return load();
  });

  /* Balance sheet */

  App.register("balance-sheet", function (page) {
    var box = el("div");
    var bar = periodBar(load, { singleDate: false });

    function load() {
      return api("/api/reports/balance-sheet", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
      }}).then(function (data) {
        function sideTable(title, side, total) {
          var rows = [];
          Object.keys(side.groups).sort(function (a, b) {
            return side.groups[a].sort - side.groups[b].sort;
          }).forEach(function (code) {
            var group = side.groups[code];
            rows.push(el("tr.group-row", {}, [
              el("td", { colspan: "2", text: group.name }), el("td.num")
            ]));
            group.lines.sort(function (a, b) { return a.code < b.code ? -1 : 1; });
            group.lines.forEach(function (line) {
              rows.push(el("tr" + (line.account_id ? ".clickable" : ""), {
                onclick: line.account_id ? function () { openLedger(line.account_id); } : null
              }, [
                el("td", { text: line.code, style: "width:70px;color:var(--ink-faint)" }),
                el("td.indent", { text: line.name }),
                el("td.num", { text: UI.rs(line.amount) })
              ]));
            });
            rows.push(el("tr", {}, [
              el("td", { colspan: "2", text: "", style: "border:0" }),
              el("td.num", { text: UI.rs(group.total), style: "border-top:1px solid var(--line)" })
            ]));
          });
          return el("div", {}, [
            el("h3", { text: title }),
            UI.table(["Code", "Particulars", { label: "Amount", num: true }], rows,
              [el("tr.total-row", {}, [
                el("td", { colspan: "2", text: "Total " + title.toLowerCase() }),
                el("td.num", { text: UI.rs(total) })
              ])])
          ]);
        }

        UI.clear(box);
        box.appendChild(reportHead("Statement of Financial Position",
          "As at " + UI.bs(data.as_at_ad, "long") + "   (" + data.as_at_ad + ")"));
        if (!data.balanced) {
          box.appendChild(el("div.flash.bad", { style: "margin-bottom:.6rem",
            text: "The balance sheet is out by " + UI.rs(data.difference)
              + ". Check the trial balance and the audit trail." }));
        }
        box.appendChild(el("div.grid.two", {}, [
          sideTable("Assets", data.assets, data.total_assets),
          el("div", {}, [
            sideTable("Equity", data.equity, data.total_equity),
            sideTable("Liabilities", data.liabilities, data.total_liabilities),
            el("div.card", { style: "margin-top:.6rem;background:var(--line-soft)" }, [
              el("div", { style: "display:flex;justify-content:space-between;font-weight:700" }, [
                el("span", { text: "Total equity and liabilities" }),
                el("span.num", { text: UI.rs(data.total_liabilities_and_equity) })
              ])
            ])
          ])
        ]));
        if (data.balanced) {
          box.appendChild(el("p.card-note", { style: "text-align:center;margin-top:.6rem",
            text: "Assets equal equity plus liabilities exactly." }));
        }
      });
    }

    page.appendChild(el("div.card", {}, [bar, box]));
    return load();
  });

  /* Stock */

  App.register("stock", function (page) {
    var box = el("div");
    var bar = periodBar(load);

    function load() {
      return api("/api/reports/stock", { query: { as_at: bar.to.getIso() } }).then(function (data) {
        var currentGroup = null;
        var rows = [];
        data.rows.forEach(function (row) {
          if (row.group_name !== currentGroup) {
            currentGroup = row.group_name;
            rows.push(el("tr.group-row", {}, [
              el("td", { colspan: "6", text: currentGroup || "Ungrouped" })
            ]));
          }
          rows.push(el("tr.clickable", { onclick: function () { openItemMovement(row.item_id); } }, [
            el("td", { text: row.code }),
            el("td.indent", {}, [
              el("span", { text: row.name }),
              row.below_reorder ? el("span.pill.warn", { text: "low", style: "margin-left:.4rem" }) : null
            ]),
            el("td.num", { text: NP.formatQty(row.qty) }),
            el("td", { text: row.unit, style: "font-size:.76rem;color:var(--ink-faint)" }),
            el("td.num", { text: UI.rs(row.average_rate) }),
            el("td.num", { text: UI.rs(row.value) })
          ]));
        });
        UI.clear(box);
        box.appendChild(reportHead("Stock Summary",
          "As at " + UI.bs(bar.to.getIso(), "long") + "   (" + bar.to.getIso() + ")"));
        box.appendChild(UI.table([
          "Code", "Item", { label: "Quantity", num: true }, "Unit",
          { label: "Average rate", num: true }, { label: "Value", num: true }
        ], rows, [el("tr.total-row", {}, [
          el("td", { colspan: "5", text: "Total value of stock" }),
          el("td.num", { text: UI.rs(data.total_value) })
        ])], { tall: true, emptyText: "No stock items yet." }));
        box.appendChild(el("p.card-note", { style: "margin-top:.7rem", text:
          "Valued at weighted average cost. This is the figure to use for the closing stock entry." }));
      });
    }

    page.appendChild(el("div.card", {}, [bar, box]));
    return load();
  });

  function openItemMovement(itemId) {
    api("/api/reports/stock-item", { query: { item_id: itemId } }).then(function (data) {
      var rows = data.history.map(function (move) {
        return el("tr", {}, [
          el("td", { text: UI.bs(move.date_ad, "short") }),
          el("td", { text: move.number }),
          el("td", { text: move.party_name || "" }),
          el("td", {}, [el("span.pill" + (move.direction > 0 ? ".good" : ""),
            { text: move.direction > 0 ? "in" : "out" })]),
          el("td.num", { text: NP.formatQty(move.qty) }),
          el("td.num", { text: UI.rs(move.rate) }),
          el("td.num", { text: UI.rs(move.cost) }),
          el("td.num", { text: NP.formatQty(move.balance_qty) }),
          el("td.num", { text: UI.rs(move.balance_value) })
        ]);
      });
      var body = el("div", {}, [
        el("div.grid.three", {}, [
          el("div.tile", {}, [el("div.tile-label", { text: "In stock" }),
            el("div.tile-value", { text: NP.formatQty(data.qty) })]),
          el("div.tile", {}, [el("div.tile-label", { text: "Value" }),
            el("div.tile-value", { text: UI.rs(data.value) })]),
          el("div.tile", {}, [el("div.tile-label", { text: "Average cost" }),
            el("div.tile-value", { text: UI.rs(data.average_rate) })])
        ]),
        el("div", { style: "margin-top:.8rem" }, [UI.table([
          "Date", "Voucher", "Party", "", { label: "Quantity", num: true },
          { label: "Rate", num: true }, { label: "Cost", num: true },
          { label: "Balance qty", num: true }, { label: "Balance value", num: true }
        ], rows, null, { tall: true, emptyText: "No movement yet." })])
      ]);
      UI.modal(data.item.name, body, [{ label: "Close" },
        { label: "Print", action: function () { UI.printPage(); return false; } }], { wide: true });
    }).catch(function (error) { UI.flash(error.message, "bad"); });
  }

  /* Receivable and payable */

  App.register("outstanding", function (page) {
    var box = el("div");
    var side = UI.select([
      { value: "receivable", label: "Receivable, owed to you" },
      { value: "payable", label: "Payable, owed by you" }
    ], "receivable");
    var bar = periodBar(load);
    bar.insertBefore(UI.field("Which", side), bar.firstChild);
    side.addEventListener("change", load);

    function load() {
      return api("/api/reports/outstanding", { query: {
        side: side.value, as_at: bar.to.getIso()
      }}).then(function (data) {
        var rows = data.rows.map(function (row) {
          var overLimit = row.credit_limit && row.amount > row.credit_limit;
          return el("tr.clickable", { onclick: function () { openLedger(row.account_id); } }, [
            el("td", { text: row.code }),
            el("td", {}, [
              el("span", { text: row.name }),
              overLimit ? el("span.pill.bad", { text: "over limit", style: "margin-left:.4rem" }) : null
            ]),
            el("td", { text: row.pan || "" }),
            el("td", { text: row.phone || "" }),
            el("td.num", { text: row.credit_days ? row.credit_days + " days" : "" }),
            el("td.num", { text: UI.rs(row.amount) })
          ]);
        });
        UI.clear(box);
        box.appendChild(reportHead(
          side.value === "receivable" ? "Statement of Receivables" : "Statement of Payables",
          "As at " + UI.bs(bar.to.getIso(), "long") + "   (" + bar.to.getIso() + ")"));
        box.appendChild(UI.table([
          "Code", "Party", "PAN", "Phone", { label: "Credit terms", num: true },
          { label: "Amount", num: true }
        ], rows, [el("tr.total-row", {}, [
          el("td", { colspan: "5", text: "Total" }),
          el("td.num", { text: UI.rs(data.total) })
        ])], { tall: true, emptyText: "Nothing outstanding." }));
      });
    }

    page.appendChild(el("div.card", {}, [bar, box]));
    return load();
  });

  /* VAT return */

  App.register("vat", function (page) {
    var today = NP.adToBs(NP.todayIso());
    var yearInput = el("input", { type: "number", value: today.year, min: "2000", max: "2099" });
    var monthSelect = UI.select(NP.MONTHS_EN.map(function (name, index) {
      return { value: index + 1, label: name };
    }), today.month);
    var box = el("div");

    function load() {
      return api("/api/reports/vat", { query: {
        bs_year: yearInput.value, bs_month: monthSelect.value
      }}).then(function (data) {
        function register(title, rowsData, isSales) {
          var rows = rowsData.map(function (row) {
            return el("tr.clickable", { onclick: function () { Vouchers.view(row.voucher_id); } }, [
              el("td", { text: row.date_bs }),
              el("td", { text: row.number }),
              el("td", { text: row.party_name }),
              el("td", { text: row.party_pan || "" }),
              el("td.num", { text: UI.rs(row.total) }),
              el("td.num", { text: UI.rs(row.taxable, { blankZero: true }) }),
              el("td.num", { text: UI.rs(row.exempt, { blankZero: true }) }),
              el("td.num", { text: UI.rs(row.vat, { blankZero: true }) })
            ]);
          });
          var totals = isSales ? data.sales : data.purchases;
          return el("div.card", {}, [
            el("div.card-head", {}, [el("h2", { text: title })]),
            UI.table([
              "Date (BS)", "Invoice", "Party", "PAN",
              { label: "Total", num: true }, { label: "Taxable", num: true },
              { label: "Exempt", num: true }, { label: "VAT", num: true }
            ], rows, [el("tr.total-row", {}, [
              el("td", { colspan: "4", text: "Total" }),
              el("td.num", { text: UI.rs(totals.total) }),
              el("td.num", { text: UI.rs(totals.taxable) }),
              el("td.num", { text: UI.rs(totals.exempt) }),
              el("td.num", { text: UI.rs(totals.vat) })
            ])], { emptyText: "No entries this month." })
          ]);
        }

        UI.clear(box);
        box.appendChild(reportHead("Value Added Tax Return",
          data.month_name + " " + data.bs_year + "   (" + data.from_ad + " to " + data.to_ad + ")"));
        box.appendChild(el("div.grid.four", {}, [
          el("div.tile", {}, [el("div.tile-label", { text: "Output tax on sales" }),
            el("div.tile-value", { text: UI.rs(data.output_tax) })]),
          el("div.tile", {}, [el("div.tile-label", { text: "Input tax on purchases" }),
            el("div.tile-value", { text: UI.rs(data.input_tax) })]),
          el("div.tile" + (data.payable ? ".bad" : ".good"), {}, [
            el("div.tile-label", { text: data.payable ? "Payable to the department" : "Credit carried forward" }),
            el("div.tile-value", { text: UI.rs(data.payable || data.credit_carried) })]),
          el("div.tile", {}, [el("div.tile-label", { text: "Return due by" }),
            el("div.tile-value", { text: "", style: "font-size:.95rem" }),
            el("div.tile-note", { text: data.due_date_bs })])
        ]));
        box.appendChild(register("Sales register", data.sales_rows, true));
        box.appendChild(register("Purchase register", data.purchase_rows, false));
        box.appendChild(el("p.card-note", { text:
          "The return for a Nepali month is due by the 25th of the following month. Check the figures against your invoice books before filing." }));
      });
    }

    yearInput.addEventListener("change", load);
    monthSelect.addEventListener("change", load);

    page.appendChild(el("div.card", {}, [
      el("div.toolbar", {}, [
        UI.field("Bikram Sambat year", yearInput),
        UI.field("Month", monthSelect),
        el("div.spacer"),
        el("button.secondary.no-print", { text: "Print", onclick: UI.printPage }),
      UI.exportButton()
      ])
    ]));
    page.appendChild(box);
    return load();
  });

  return {
    openLedger: openLedger, openItemMovement: openItemMovement,
    periodBar: periodBar, reportHead: reportHead, periodText: periodText
  };
}());

/* Period end work: closing stock, opening stock and the depreciation working. */

App.register("period-end", function (page) {
  var el = UI.el, api = UI.api;
  var fy = App.state.fiscalYear || {};
  var dateField = UI.dateField(fy.end_ad || NP.todayIso(), function () { load(); });
  var box = el("div");

  function load() {
    return api("/api/period-end/closing-stock", { query: { date_ad: dateField.getIso() } })
      .then(function (data) {
        UI.clear(box);
        box.appendChild(el("div.grid.three", {}, [
          el("div.tile", {}, [
            el("div.tile-label", { text: "Stock valued at this date" }),
            el("div.tile-value", { text: UI.rs(data.valued_at) }),
            el("div.tile-note", { text: data.item_count + " items, weighted average cost" })
          ]),
          el("div.tile", {}, [
            el("div.tile-label", { text: "Already in the accounts" }),
            el("div.tile-value", { text: UI.rs(data.already_booked) }),
            el("div.tile-note", { text: "Balance of Stock in Trade" })
          ]),
          el("div.tile" + (data.adjustment ? ".bad" : ".good"), {}, [
            el("div.tile-label", { text: "Entry to be passed" }),
            el("div.tile-value", { text: UI.rs(data.adjustment) }),
            el("div.tile-note", { text: data.adjustment
              ? (data.adjustment > 0 ? "Debit Stock in Trade, credit Closing Stock"
                                     : "Credit Stock in Trade, debit Closing Stock")
              : "Nothing to adjust" })
          ])
        ]));
        box.appendChild(el("div.row", { style: "margin-top:.8rem" }, [
          el("button.primary", { text: "Pass the closing stock entry",
            disabled: !data.adjustment,
            onclick: function () {
              api("/api/period-end/closing-stock", { body: { date_ad: dateField.getIso() } })
                .then(function (result) {
                  UI.flash("Closing stock entry posted as " + result.voucher.voucher.number + ".", "good");
                  load();
                })
                .catch(function (error) { UI.flash(error.message, "bad"); });
            }})
        ]));
      });
  }

  page.appendChild(el("div.card", {}, [
    el("div.card-head", {}, [el("h2", { text: "Closing stock" })]),
    el("p.card-note", { text: "Stock is kept on the periodic basis, so purchases sit in cost of sales in full until the closing stock is brought in. Pass this entry at the end of a month or a year and the profit and loss reads correctly. Running it again after a late invoice posts only the difference." }),
    el("div.toolbar", {}, [UI.field("Value the stock as at", dateField)]),
    box
  ]));

  var openingDate = UI.dateField(fy.start_ad || NP.todayIso());
  page.appendChild(el("div.card", {}, [
    el("div.card-head", {}, [el("h2", { text: "Opening stock for a new year" })]),
    el("p.card-note", { text: "On the first day of a new fiscal year, move last year's closing stock into opening stock. Debit Opening Stock, credit Stock in Trade." }),
    el("div.toolbar", {}, [
      UI.field("First day of the new year", openingDate),
      el("button.secondary", { text: "Pass the opening stock entry", onclick: function () {
        api("/api/period-end/opening-stock", { body: { date_ad: openingDate.getIso() } })
          .then(function () { UI.flash("Opening stock entry posted.", "good"); load(); })
          .catch(function (error) { UI.flash(error.message, "bad"); });
      }})
    ])
  ]));

  var depBox = el("div");
  page.appendChild(el("div.card", {}, [
    el("div.card-head", {}, [el("h2", { text: "Fixed assets, for the depreciation working" })]),
    el("p.card-note", { text: "The rate and the pooling method under schedule 2 of the Income Tax Act, 2058 depend on which block an asset belongs to and how long it was in use during the year. These are the balances. Work out the charge and enter it as a journal." }),
    depBox
  ]));
  api("/api/period-end/depreciation", { query: { as_at: dateField.getIso() } })
    .then(function (data) {
      var rows = data.rows.map(function (row) {
        return el("tr.clickable", { onclick: function () { Reports.openLedger(row.account_id); } }, [
          el("td", { text: row.code }),
          el("td", { text: row.name }),
          el("td", { text: row.kind === "contra_asset" ? "accumulated depreciation" : "cost" }),
          el("td.num", { text: UI.rs(Math.abs(row.balance)) })
        ]);
      });
      UI.clear(depBox).appendChild(UI.table(
        ["Code", "Ledger", "", { label: "Balance", num: true }], rows, null,
        { emptyText: "No fixed assets have been recorded yet." }));
    });

  return load();
});

/* Group summary, the whole chart of accounts as a tree you can open. */

App.register("groups", function (page) {
  var el = UI.el, api = UI.api;
  var box = el("div");
  var drillHost = el("div");
  var bar = Reports.periodBar(load);
  var expanded = {};

  function load() {
    Drill.close();
    Drill.setPeriod(bar.from.getIso(), bar.to.getIso());
    return api("/api/reports/groups", { query: {
      from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
    }}).then(function (data) {
      var byId = {};
      data.nodes.forEach(function (node) { byId[node.id] = node; });
      UI.clear(box);
      box.appendChild(Reports.reportHead("Group Summary",
        Reports.periodText(data.from_ad, data.to_ad)));

      var rows = [];
      function walk(id, depth) {
        var node = byId[id];
        if (!node) { return; }
        var hasChildren = node.children.length > 0 || node.ledger_count > 0;
        var isOpen = expanded[id];
        rows.push(el("tr" + (hasChildren ? ".clickable" : ""), {
          onclick: hasChildren ? function () {
            expanded[id] = !expanded[id];
            draw();
          } : null
        }, [
          el("td", { text: node.code, style: "padding-left:" + (depth * 1.1 + 0.55) + "rem" }),
          el("td", {}, [
            el("span", { text: (hasChildren ? (isOpen ? "−  " : "+  ") : "    ")
              + node.name,
              style: "font-weight:" + (depth === 0 ? "650" : "500") }),
            node.ledger_count
              ? el("span.pill", { text: node.ledger_count + " ledgers",
                                  style: "margin-left:.4rem" })
              : null
          ]),
          el("td.num", { text: UI.rs(node.opening, { blankZero: true }) }),
          el("td.num", { text: UI.rs(node.debit, { blankZero: true }) }),
          el("td.num", { text: UI.rs(node.credit, { blankZero: true }) }),
          el("td.num", { text: Drill.signed(node.closing) }),
          el("td.no-print", {}, [
            el("button.link-button", { text: "Open", onclick: function (event) {
              event.stopPropagation();
              Drill.openGroup(node.id, node.name);
            }})
          ])
        ]));
        if (isOpen) {
          node.children.forEach(function (childId) { walk(childId, depth + 1); });
        }
      }

      function draw() {
        rows = [];
        data.roots.forEach(function (id) { walk(id, 0); });
        UI.clear(tableBox).appendChild(UI.table(
          ["Code", "Group", { label: "Opening", num: true }, { label: "Debit", num: true },
           { label: "Credit", num: true }, { label: "Closing", num: true }, ""],
          rows, null, { tall: true }));
      }

      var tableBox = el("div");
      box.appendChild(tableBox);
      box.appendChild(el("p.card-note", { style: "margin-top:.6rem",
        text: "Click a group to open the ones inside it, or Open to drill all the way down to the vouchers." }));
      draw();
    });
  }

  page.appendChild(el("div.card", {}, [bar, box]));
  page.appendChild(el("div.card", {}, [drillHost]));
  Drill.mount(drillHost);
  return load();
});

/* Ageing of what is owed */

App.register("ageing", function (page) {
  var el = UI.el, api = UI.api;
  var side = UI.select([
    { value: "receivable", label: "Receivable, owed to you" },
    { value: "payable", label: "Payable, owed by you" }
  ], App.state.ageingSide || "receivable");
  var bar = Reports.periodBar(load, { singleDate: true });
  var box = el("div");

  side.addEventListener("change", function () {
    App.state.ageingSide = side.value;
    load();
  });

  function load() {
    return api("/api/reports/ageing", { query: {
      side: side.value, as_at: bar.to.getIso()
    }}).then(function (data) {
      UI.clear(box);
      box.appendChild(Reports.reportHead(
        data.side === "receivable" ? "Ageing of Receivables" : "Ageing of Payables",
        "As at " + UI.bs(data.as_at_ad, "long") + "   (" + data.as_at_ad + ")"));

      box.appendChild(el("div.grid.three", { style: "margin-bottom:.9rem" }, [
        tile("Total outstanding", UI.rs(data.grand_total), data.rows.length + " parties"),
        tile("Not yet due", UI.rs(data.totals[0]), "Inside the credit period", "good"),
        tile("Overdue", UI.rs(data.grand_total - data.totals[0]),
             "Past the agreed terms",
             (data.grand_total - data.totals[0]) ? "bad" : "good")
      ]));

      var rows = data.rows.map(function (row) {
        var cells = [
          el("td", { text: row.code }),
          el("td", {}, [
            el("div", { text: row.name }),
            row.phone ? el("div.muted", { text: row.phone, style: "font-size:.74rem" }) : null
          ]),
          el("td.muted", { text: row.credit_days ? row.credit_days + " d" : "",
                           style: "font-size:.76rem" })
        ];
        row.buckets.forEach(function (amount, index) {
          cells.push(el("td.num" + (index > 1 && amount ? ".negative" : ""),
            { text: UI.rs(amount, { blankZero: true }) }));
        });
        cells.push(el("td.num", { text: UI.rs(row.total) }));
        return el("tr.clickable", {
          onclick: function () { showDetail(row, data.labels); }
        }, cells);
      });

      var head = ["Code", "Party", "Terms"].concat(
        data.labels.map(function (label) { return { label: label, num: true }; }),
        [{ label: "Total", num: true }]);
      var foot = [el("tr.total-row", {}, [el("td", { colspan: "3", text: "Total" })].concat(
        data.totals.map(function (amount) { return el("td.num", { text: UI.rs(amount) }); }),
        [el("td.num", { text: UI.rs(data.grand_total) })]))];

      box.appendChild(UI.table(head, rows, foot,
        { tall: true, emptyText: "Nothing outstanding." }));
      box.appendChild(el("p.card-note", { style: "margin-top:.6rem",
        text: "Where nothing has been set against a particular bill, receipts are matched to the "
          + "oldest invoice first. Click a party to see the bills behind the figure." }));
    });
  }

  function tile(label, value, note, kind) {
    return el("div.tile" + (kind ? "." + kind : ""), {}, [
      el("div.tile-label", { text: label }),
      el("div.tile-value", { text: value }),
      note ? el("div.tile-note", { text: note }) : null
    ]);
  }

  function showDetail(row, labels) {
    var rows = row.details.map(function (item) {
      return el("tr" + (item.voucher_id ? ".clickable" : ""), {
        onclick: item.voucher_id ? function () { Vouchers.view(item.voucher_id); } : null
      }, [
        el("td", { text: item.number }),
        el("td", { text: item.date_bs || "" }),
        el("td.muted", { text: item.date_ad || "", style: "font-size:.76rem" }),
        el("td.num", { text: item.age_days === null || item.age_days === undefined
          ? "" : (item.age_days <= 0 ? "not due" : item.age_days + " days") }),
        el("td.num", { text: UI.rs(item.amount) })
      ]);
    });
    UI.modal(row.name, el("div", {}, [
      el("p.card-note", { text: (row.pan ? "PAN " + row.pan + "   " : "")
        + (row.credit_days ? "Credit " + row.credit_days + " days" : "") }),
      UI.table(["Bill", "Date (BS)", "Date (AD)", { label: "Age", num: true },
                { label: "Amount", num: true }], rows,
        [el("tr.total-row", {}, [
          el("td", { colspan: "4", text: "Total" }),
          el("td.num", { text: UI.rs(row.total) })
        ])])
    ]), [
      { label: "Close" },
      { label: "Open the ledger", action: function () {
        UI.closeModal();
        Reports.openLedger(row.account_id);
        return false;
      }},
      { label: "Print", action: function () { UI.printPage(); return false; } }
    ], { wide: true });
  }

  page.appendChild(el("div.card", {}, [
    el("div.toolbar", {}, [UI.field("Which", side)]),
    bar, box
  ]));
  return load();
});

/* Statement of account.

   What to send a customer who asks what they owe, or to check against a
   supplier's own statement before paying it. Every movement in date order with
   a running balance, and what is still open set out bill by bill underneath. */

App.register("statement", function (page) {
  var el = UI.el, api = UI.api;
  var partyInput = el("input", { type: "text", placeholder: "Customer or supplier name" });
  var partyId = App.state.pendingStatement || null;
  App.state.pendingStatement = null;
  var box = el("div", {}, [el("div.empty", {}, [
    el("strong", { text: "Choose a customer or supplier" }),
    el("span", { text: "Their statement appears here, ready to print or hand over." })
  ])]);
  var bar = Reports.periodBar(function () { if (partyId) { load(); } });

  UI.attachPicker(partyInput, function (term) {
    return api("/api/parties", { query: { q: term } }).then(function (d) { return d.rows; });
  }, function (party) {
    partyId = party.id;
    partyInput.value = party.name;
    load();
  }, function (party) {
    return { main: party.name, side: party.party_type };
  });

  function load() {
    return api("/api/statement", { query: {
      party_id: partyId, from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
    }}).then(function (data) {
      var party = data.party;
      partyInput.value = party.name;
      UI.clear(box);

      box.appendChild(Reports.reportHead("Statement of Account",
        Reports.periodText(data.from_ad, data.to_ad)));

      box.appendChild(el("div.doc-parties", { style: "margin-bottom:1rem" }, [
        el("div", {}, [
          el("div.muted", { style: "font-size:.74rem", text: "Statement for" }),
          el("div", { text: party.name, style: "font-weight:650;font-size:1rem" }),
          party.address ? el("div.muted", { style: "font-size:.8rem",
            text: [party.address, party.city, party.district].filter(Boolean).join(", ") }) : null,
          party.pan ? el("div.muted", { style: "font-size:.8rem", text: "PAN " + party.pan }) : null,
          party.mobile || party.phone
            ? el("div.muted", { style: "font-size:.8rem", text: party.mobile || party.phone })
            : null
        ]),
        el("div", { style: "text-align:right" }, [
          el("div.muted", { style: "font-size:.74rem",
            text: data.side === "receivable" ? "Owed to us" : "Owed by us" }),
          el("div.num", { text: UI.rs(Math.abs(data.closing)),
                          style: "font-size:1.3rem;font-weight:650" }),
          party.credit_days
            ? el("div.muted", { style: "font-size:.78rem",
                                text: "Terms " + party.credit_days + " days" })
            : null
        ])
      ]));

      var rows = [el("tr.total-row", {}, [
        el("td", { colspan: "4", text: "Balance brought forward" }),
        el("td.num"), el("td.num"),
        el("td.num", { text: UI.rs(Math.abs(data.opening))
          + (data.opening >= 0 ? " Dr" : " Cr") })
      ])];
      data.lines.forEach(function (line) {
        rows.push(el("tr.clickable", {
          onclick: function () { Vouchers.view(line.voucher_id); }
        }, [
          el("td", { text: UI.bs(line.date_ad, "short") }),
          el("td.muted", { text: line.date_ad, style: "font-size:.74rem" }),
          el("td", { text: line.number }),
          el("td", { text: line.particulars || line.narration || "" }),
          el("td.num", { text: UI.rs(line.dr, { blankZero: true }) }),
          el("td.num", { text: UI.rs(line.cr, { blankZero: true }) }),
          el("td.num", { text: UI.rs(Math.abs(line.balance))
            + (line.balance >= 0 ? " Dr" : " Cr") })
        ]));
      });

      box.appendChild(UI.table([
        "Date (BS)", "Date (AD)", "Voucher", "Particulars",
        { label: "Debit", num: true }, { label: "Credit", num: true },
        { label: "Balance", num: true }
      ], rows, [el("tr.grand-row", {}, [
        el("td", { colspan: "4", text: "Balance carried forward" }),
        el("td.num", { text: UI.rs(data.total_dr) }),
        el("td.num", { text: UI.rs(data.total_cr) }),
        el("td.num", { text: UI.rs(Math.abs(data.closing))
          + (data.closing >= 0 ? " Dr" : " Cr") })
      ])], { tall: true, emptyText: "Nothing moved on this account in the period." }));

      if (data.open_bills.length) {
        var billRows = data.open_bills.map(function (bill) {
          return el("tr" + (bill.age_days > 0 ? ".overdue" : ""), {}, [
            el("td", { text: bill.number }),
            el("td", { text: bill.date_bs || "" }),
            el("td.num", { text: bill.age_days === null || bill.age_days === undefined
              ? "" : (bill.age_days <= 0 ? "not due" : bill.age_days + " days") }),
            el("td.num", { text: UI.rs(bill.amount) })
          ]);
        });
        box.appendChild(el("div", { style: "margin-top:1.2rem" }, [
          el("h3", { text: "What is still open" }),
          UI.table(["Bill", "Date", { label: "Age", num: true },
                    { label: "Amount", num: true }], billRows,
            [el("tr.sum-row", {}, [
              el("td", { colspan: "3", text: "Total outstanding" }),
              el("td.num", { text: UI.rs(data.open_bills.reduce(
                function (sum, b) { return sum + b.amount; }, 0)) })
            ])])
        ]));
      }

      box.appendChild(el("p.card-note", { style: "margin-top:1rem",
        text: "Please check this against your own records and tell us of anything that does "
          + "not agree." }));
    });
  }

  page.appendChild(el("div.card", {}, [
    el("div.card-head", {}, [
      el("h2", { text: "Statement of account" }),
      el("button.secondary.no-print", { text: "Print", onclick: UI.printPage }),
      UI.exportButton()
    ]),
    el("div.toolbar", {}, [
      el("div.field", { style: "flex:1 1 260px;margin:0" }, [
        el("label", { text: "Party" }), partyInput
      ])
    ]),
    bar, box
  ]));

  if (partyId) { return load(); }
});
