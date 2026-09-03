/* The formal financial statements.

   Statement of Financial Position, Statement of Profit or Loss, Statement of
   Changes in Equity, Statement of Cash Flows, and the notes behind them, laid
   out the way NAS 01 and NAS 07 present them, with last year beside this year.

   Every line on the face of a statement opens into the group behind it. */

var Statements = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  var TABS = [
    ["position", "Balance sheet"],
    ["profit", "Profit and loss"],
    ["equity", "Changes in equity"],
    ["cash", "Cash flows"],
    ["notes", "Notes and schedules"],
    ["ppe", "Fixed asset schedule"],
    ["intangible", "Intangible schedule"],
    ["register", "Asset register"],
    ["taxdep", "Tax depreciation"],
    ["deferred", "Deferred tax"],
    ["instruments", "Financial instruments"],
    ["trading", "Trading account"]
  ];

  App.register("statements", function (page) {
    var chosen = App.state.statementTab || "position";
    var compare = el("input", { type: "checkbox" });
    compare.checked = App.state.statementCompare !== false;
    var bar = Reports.periodBar(load);
    var tabs = el("div.stmt-tabs");
    var box = el("div.stmt");
    var drillHost = el("div");
    var data = null;

    TABS.forEach(function (pair) {
      tabs.appendChild(el("button" + (chosen === pair[0] ? ".on" : ""), {
        text: pair[1],
        onclick: function (event) {
          chosen = pair[0];
          App.state.statementTab = chosen;
          UI.qsa("button", tabs).forEach(function (b) { b.classList.remove("on"); });
          event.currentTarget.classList.add("on");
          Drill.close();
          draw();
        }
      }));
    });

    compare.addEventListener("change", function () {
      App.state.statementCompare = compare.checked;
      load();
    });

    function load() {
      Drill.close();
      Drill.setPeriod(bar.from.getIso(), bar.to.getIso());
      extra = {};
      return api("/api/reports/statements", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso(),
        compare: compare.checked ? "1" : "0"
      }}).then(function (result) {
        data = result;
        draw();
      });
    }

    function draw() {
      UI.clear(box);
      if (!data) { return; }
      var render = { position: drawPosition, profit: drawProfit, equity: drawEquity,
                     cash: drawCash, notes: drawNotes, trading: drawTrading,
                     ppe: drawPpe, intangible: drawIntangible, register: drawRegister,
                     taxdep: drawTaxDepreciation, deferred: drawDeferred,
                     instruments: drawInstruments }[chosen];
      box.appendChild(Reports.reportHead(titleFor(chosen), subtitleFor(chosen)));
      render(box);
    }

    function titleFor(key) {
      return {
        position: "Statement of Financial Position",
        profit: "Statement of Profit or Loss",
        equity: "Statement of Changes in Equity",
        cash: "Statement of Cash Flows",
        notes: "Notes to the Financial Statements",
        trading: "Trading and Profit and Loss Account",
        ppe: "Property, Plant and Equipment",
        intangible: "Intangible Assets",
        register: "Fixed Asset Register",
        taxdep: "Depreciation under Schedule 2 of the Income Tax Act, 2058",
        deferred: "Deferred Tax",
        instruments: "Financial Instruments"
      }[key];
    }

    function subtitleFor(key) {
      if (key === "position" || key === "instruments") {
        return "As at " + data.position.as_at_bs + "   (" + data.position.as_at_ad + ")";
      }
      return "For the period " + data.period_label + "   ("
        + data.from_ad + " to " + data.to_ad + ")";
    }

    function amountCells(amount, previous) {
      var cells = [el("td.num", { text: UI.rs(amount, { blankZero: false }) })];
      if (data.compare) {
        cells.push(el("td.num.muted", {
          text: previous === null || previous === undefined ? "" : UI.rs(previous)
        }));
      }
      return cells;
    }

    function headers(firstLabel) {
      var head = [firstLabel, { label: "Note", num: false },
                  { label: bsYear(data.to_ad), num: true }];
      if (data.compare) {
        head.push({ label: bsYear(data.compare.to_ad), num: true });
      }
      return head;
    }

    function noteHeaders() {
      // A schedule lists ledgers, so the second column is the name of the
      // ledger, not a reference to another note.
      var head = ["Code", "Particulars", { label: bsYear(data.to_ad), num: true }];
      if (data.compare) { head.push({ label: bsYear(data.compare.to_ad), num: true }); }
      return head;
    }

    function bsYear(iso) {
      var bs = NP.adToBs(iso);
      return bs ? NP.formatBs(bs, "numeric") : iso;
    }

    /* Statement of financial position */

    function drawPosition(target) {
      var p = data.position;
      var rows = [];
      var noteByGroup = {};
      data.schedules.notes.forEach(function (note) {
        if (note.statement === "BS") { noteByGroup[note.group_code] = note.number; }
      });

      function section(key, label) {
        var block = p.sections[key];
        if (!block.lines.length) { return; }
        rows.push(el("tr.head-row", {}, [
          el("td", { colspan: data.compare ? "4" : "3", text: label })
        ]));
        block.lines.forEach(function (line) {
          var openable = !!line.group_id;
          rows.push(el("tr" + (openable ? ".openable" : ""), {
            onclick: openable ? function () {
              Drill.openGroup(line.group_id, line.name);
            } : null
          }, [
            el("td", { text: line.name }),
            el("td.note-ref", { text: noteByGroup[line.code] || "" })
          ].concat(amountCells(line.amount, line.previous))));
        });
        rows.push(el("tr.sum-row", {}, [
          el("td", { colspan: "2", text: "Total " + label.toLowerCase() })
        ].concat(amountCells(block.total, block.previous))));
      }

      section("non_current_assets", "Non current assets");
      section("current_assets", "Current assets");
      rows.push(el("tr.grand-row", {}, [
        el("td", { colspan: "2", text: "Total assets" })
      ].concat(amountCells(p.total_assets, p.previous && p.previous.total_assets))));

      section("equity", "Equity");
      section("non_current_liabilities", "Non current liabilities");
      section("current_liabilities", "Current liabilities");
      rows.push(el("tr.grand-row", {}, [
        el("td", { colspan: "2", text: "Total equity and liabilities" })
      ].concat(amountCells(p.total_equity_and_liabilities,
        p.previous && p.previous.total_equity_and_liabilities))));

      target.appendChild(UI.table(headers("Particulars"), rows));
      if (!p.balanced) {
        target.appendChild(el("div.flash.bad", { style: "margin-top:.7rem",
          text: "The statement is out by " + UI.rs(p.difference)
            + ". Check the trial balance and the audit trail." }));
      } else {
        target.appendChild(el("p.card-note", { style: "text-align:center;margin-top:.7rem",
          text: "Assets equal equity plus liabilities exactly. Click any line to open what is behind it." }));
      }
      target.appendChild(drillHost);
      Drill.mount(drillHost);
    }

    /* Statement of profit or loss */

    function drawProfit(target) {
      var pl = data.profit_or_loss;
      var noteByKey = {};
      var sectionForKey = {
        revenue: "revenue", cost_of_sales: "cost_of_sales", other_income: "other_income",
        employee: "employee", administrative: "administrative", selling: "selling",
        finance: "finance", depreciation: "depreciation", other_expense: "other_expense",
        tax: "tax"
      };
      var rows = pl.rows.map(function (row) {
        var isTotal = !!row.total;
        var sectionKey = sectionForKey[row.key];
        var canOpen = !isTotal && sectionKey && pl.detail.sections[sectionKey];
        return el("tr" + (isTotal ? (row.strong ? ".grand-row" : ".sum-row") : "")
                  + (canOpen ? ".openable" : ""), {
          onclick: canOpen ? function () { openSection(sectionKey, row.label); } : null
        }, [
          el("td", { text: row.label }),
          el("td.note-ref", { text: row.note || "" })
        ].concat(amountCells(row.amount, row.previous)));
      });
      target.appendChild(UI.table(headers("Particulars"), rows));
      target.appendChild(el("p.card-note", { style: "text-align:center;margin-top:.7rem",
        text: "Click a line to open the ledgers inside it." }));
      target.appendChild(drillHost);
      Drill.mount(drillHost);
    }

    function openSection(sectionKey, label) {
      var section = data.profit_or_loss.detail.sections[sectionKey];
      if (!section) { return; }
      var codes = Object.keys(section.groups);
      if (codes.length === 1) {
        var only = section.groups[codes[0]];
        if (only.group_id) { Drill.openGroup(only.group_id, only.name); return; }
      }
      // Show the groups inside the section, then let each one open further.
      Drill.close();
      Drill.mount(drillHost);
      UI.clear(drillHost);
      drillHost.appendChild(el("div.crumbs", {}, [el("span.crumb.here", { text: label })]));
      var rows = codes.sort().map(function (code) {
        var group = section.groups[code];
        return el("tr.openable", {
          onclick: function () { Drill.openGroup(lookupGroupId(code), group.name); }
        }, [
          el("td", { text: code }),
          el("td", { text: group.name }),
          el("td.num", { text: UI.rs(group.total) })
        ]);
      });
      drillHost.appendChild(UI.table(
        ["Code", "Group", { label: "Amount", num: true }], rows));
    }

    var groupIdByCode = {};
    function lookupGroupId(code) {
      if (groupIdByCode[code]) { return groupIdByCode[code]; }
      var found = (App.state.lookups && App.state.lookups.account_groups || [])
        .filter(function (g) { return g.code === code; })[0];
      if (found) { groupIdByCode[code] = found.id; }
      return found ? found.id : null;
    }

    /* Changes in equity */

    function drawEquity(target) {
      var eq = data.equity;
      var prior = eq.previous;
      var rows = eq.rows.map(function (row) {
        var cells = [
          el("td", { text: row.name }),
          el("td.num", { text: UI.rs(row.opening) }),
          el("td.num", { text: UI.rs(row.introduced, { blankZero: true }) }),
          el("td.num", { text: UI.rs(row.withdrawn, { blankZero: true }) }),
          el("td.num", { text: UI.rs(row.closing) })
        ];
        if (prior) {
          cells.push(el("td.num.muted", { text: UI.rs(row.previous_closing || 0) }));
        }
        return el("tr.openable", {
          onclick: function () { Drill.openLedger(row.account_id, row.name); }
        }, cells);
      });

      function plainRow(label, opening, added, withdrawn, closing, previous) {
        var cells = [
          el("td", { text: label }),
          el("td.num", { text: opening === null ? "" : UI.rs(opening) }),
          el("td.num", { text: UI.rs(added, { blankZero: true }) }),
          el("td.num", { text: UI.rs(withdrawn, { blankZero: true }) }),
          el("td.num", { text: UI.rs(closing) })
        ];
        if (prior) {
          cells.push(el("td.num.muted", {
            text: previous === null || previous === undefined ? "" : UI.rs(previous) }));
        }
        rows.push(el("tr", {}, cells));
      }

      plainRow("Profit or loss for the period", null,
               eq.profit > 0 ? eq.profit : 0, eq.profit < 0 ? -eq.profit : 0, eq.profit,
               prior && prior.profit);
      if (eq.other_comprehensive || (prior && prior.other_comprehensive)) {
        plainRow("Other comprehensive income", null,
                 eq.other_comprehensive > 0 ? eq.other_comprehensive : 0,
                 eq.other_comprehensive < 0 ? -eq.other_comprehensive : 0,
                 eq.other_comprehensive, prior && prior.other_comprehensive);
      }

      var head = ["Particulars", { label: "Opening", num: true }, { label: "Added", num: true },
                  { label: "Withdrawn", num: true },
                  { label: "Closing " + bsYear(data.to_ad), num: true }];
      if (prior) { head.push({ label: "Closing " + bsYear(data.compare.to_ad), num: true }); }

      var footCells = [
        el("td", { text: "Total equity" }),
        el("td.num", { text: UI.rs(eq.totals.opening) }),
        el("td.num", { text: UI.rs(eq.totals.introduced) }),
        el("td.num", { text: UI.rs(eq.totals.withdrawn) }),
        el("td.num", { text: UI.rs(eq.closing_with_profit) })
      ];
      if (prior) {
        footCells.push(el("td.num.muted", { text: UI.rs(prior.closing_with_profit) }));
      }
      target.appendChild(UI.table(head, rows, [el("tr.grand-row", {}, footCells)]));
      target.appendChild(drillHost);
      Drill.mount(drillHost);
    }

    /* Cash flows */

    function drawCash(target) {
      var cf = data.cash_flows;
      var rows = [];
      var prior = cf.previous;
      function row(label, amount, kind, previous) {
        var cells = [el("td", { text: label }), el("td.num", { text: UI.rs(amount) })];
        if (prior) {
          cells.push(el("td.num.muted", {
            text: previous === null || previous === undefined ? "" : UI.rs(previous) }));
        }
        rows.push(el("tr" + (kind ? "." + kind : ""), {}, cells));
      }
      function movementRow(item, label) {
        var cells = [
          el("td", { text: label }),
          el("td.num", { text: UI.rs(item.effect) })
        ];
        if (prior) {
          cells.push(el("td.num.muted", { text: UI.rs(item.previous || 0) }));
        }
        rows.push(el("tr.openable", {
          onclick: function () { Drill.openLedger(item.account_id, item.name); }
        }, cells));
      }
      function headRow(text) {
        rows.push(el("tr.head-row", {}, [
          el("td", { colspan: prior ? "3" : "2", text: text })]));
      }
      function cashHeaders() {
        var head = ["Particulars", { label: bsYear(data.to_ad), num: true }];
        if (prior) { head.push({ label: bsYear(data.compare.to_ad), num: true }); }
        return head;
      }
      headRow("Cash flows from operating activities");
      row("Profit before tax", cf.profit_before_tax, null,
          prior && prior.profit_before_tax);
      if (cf.depreciation || (prior && prior.depreciation)) {
        row("Add depreciation and amortisation", cf.depreciation, null,
            prior && prior.depreciation);
      }
      if (cf.finance_cost || (prior && prior.finance_cost)) {
        row("Add finance costs", cf.finance_cost, null, prior && prior.finance_cost);
      }
      cf.working_capital.forEach(function (item) {
        movementRow(item, (item.increased ? "Increase in " : "Decrease in ") + item.name);
      });
      if (cf.tax_paid || (prior && prior.tax_paid)) {
        row("Income tax paid", -cf.tax_paid, null, prior && -prior.tax_paid);
      }
      row("Net cash from operating activities", cf.operating, "sum-row",
          prior && prior.operating);

      headRow("Cash flows from investing activities");
      if (!cf.investing_items.length) {
        rows.push(el("tr", {}, [el("td.muted", { colspan: prior ? "3" : "2",
          text: "Nothing bought or sold in the period." })]));
      }
      cf.investing_items.forEach(function (item) {
        movementRow(item, (item.increased ? "Purchase of " : "Disposal of ") + item.name);
      });
      row("Net cash used in investing activities", cf.investing, "sum-row",
          prior && prior.investing);

      headRow("Cash flows from financing activities");
      if (!cf.financing_items.length && !cf.finance_cost) {
        rows.push(el("tr", {}, [el("td.muted", { colspan: prior ? "3" : "2",
          text: "No money borrowed, repaid, introduced or withdrawn." })]));
      }
      cf.financing_items.forEach(function (item) {
        movementRow(item, (item.increased ? "Received from " : "Repaid or withdrawn, ") + item.name);
      });
      if (cf.finance_cost || (prior && prior.finance_cost)) {
        row("Finance costs paid", -cf.finance_cost, null, prior && -prior.finance_cost);
      }
      row("Net cash from financing activities", cf.financing, "sum-row",
          prior && prior.financing);

      row("Net change in cash", cf.net_change, "grand-row", prior && prior.net_change);
      row("Cash and bank at the start", cf.cash_opening, null, prior && prior.cash_opening);
      row("Cash and bank at the end", cf.cash_closing, "grand-row", prior && prior.cash_closing);

      target.appendChild(UI.table(cashHeaders(), rows));
      target.appendChild(el("p.card-note", { style: "margin-top:.7rem", text:
        cf.ties
          ? "Prepared by the indirect method under NAS 07. The statement agrees exactly with the "
            + "movement the cash and bank ledgers show."
          : "The statement is out by " + UI.rs(cf.unexplained)
            + " against the movement the cash and bank ledgers show. Check for a ledger that has "
            + "been put under the wrong group." }));
      target.appendChild(drillHost);
      Drill.mount(drillHost);
    }

    /* Notes */

    function drawNotes(target) {
      var wrap = el("div");
      data.schedules.notes.forEach(function (note) {
        var rows = note.lines.map(function (line) {
          return el("tr.openable", {
            onclick: function () { Drill.openLedger(line.account_id, line.name); }
          }, [
            el("td", { text: line.code }),
            el("td", { text: line.name })
          ].concat(amountCells(line.amount, line.previous)));
        });
        wrap.appendChild(el("div.note-block", {}, [
          el("h3", {}, [
            el("span.note-number", { text: note.number }),
            el("span", { text: note.title })
          ]),
          UI.table(noteHeaders(), rows,
            [el("tr.sum-row", {}, [
              el("td", { colspan: "2", text: "Total" })
            ].concat(amountCells(note.total, note.previous_total)))])
        ]));
      });
      target.appendChild(wrap);
      target.appendChild(drillHost);
      Drill.mount(drillHost);
    }

    /* The schedules behind the accounts.

       Each is fetched the first time its tab is opened and then kept, so
       moving between tabs is instant. */

    var extra = {};

    function lazy(target, key, url, query, render) {
      if (extra[key]) { render(target, extra[key]); return; }
      var holder = el("div.empty", { text: "Working it out…" });
      target.appendChild(holder);
      api(url, { query: query }).then(function (result) {
        extra[key] = result;
        holder.remove();
        render(target, result);
      }).catch(function (error) {
        holder.textContent = error.message;
      });
    }

    function drawPpe(target) {
      lazy(target, "ppe", "/api/schedules/movement", {
        group_code: "1110", from_ad: data.from_ad, to_ad: data.to_ad,
        compare: data.compare ? "1" : "0"
      }, drawMovement);
    }

    function drawIntangible(target) {
      lazy(target, "intangible", "/api/schedules/movement", {
        group_code: "1140", from_ad: data.from_ad, to_ad: data.to_ad,
        compare: data.compare ? "1" : "0"
      }, drawMovement);
    }

    function drawMovement(target, schedule) {
      if (!schedule.cost.length && !schedule.depreciation.length) {
        target.appendChild(el("div.empty", {}, [
          el("strong", { text: "Nothing in this group yet" }),
          el("span", { text: "Once something is bought and posted to these ledgers, the "
            + "movement appears here." })
        ]));
        return;
      }
      var prior = schedule.previous;

      function block(title, rows, columns, totals) {
        var body = rows.map(function (row) {
          return el("tr.openable", {
            onclick: function () { Drill.openLedger(row.account_id, row.name); }
          }, [el("td", { text: row.code }), el("td", { text: row.name })].concat(
            columns.map(function (key) {
              return el("td.num", { text: UI.rs(row[key], { blankZero: true }) });
            })));
        });
        var foot = [el("tr.sum-row", {}, [el("td", { colspan: "2", text: "Total" })].concat(
          columns.map(function (key) {
            return el("td.num", { text: UI.rs(totals[key]) });
          })))];
        return el("div", { style: "margin-bottom:1.2rem" }, [
          el("h3", { text: title }),
          UI.table(["Code", "Particulars"].concat(columns.map(function (key) {
            return { label: LABELS[key] || key, num: true };
          })), body, foot)
        ]);
      }

      var LABELS = {
        opening: "At the start", additions: "Bought", disposals: "Sold or scrapped",
        closing: "At the end", charge: "Charge for the year", on_disposal: "On disposals"
      };

      target.appendChild(block("Cost", schedule.cost,
        ["opening", "additions", "disposals", "closing"], schedule.cost_totals));
      target.appendChild(block("Depreciation", schedule.depreciation,
        ["opening", "charge", "on_disposal", "closing"], schedule.depreciation_totals));

      var carryRows = [
        el("tr", {}, [
          el("td", { text: "At the end of the year" }),
          el("td.num", { text: UI.rs(schedule.carrying_closing) }),
          prior ? el("td.num.muted", { text: UI.rs(prior.carrying_closing) }) : null
        ]),
        el("tr", {}, [
          el("td", { text: "At the start of the year" }),
          el("td.num", { text: UI.rs(schedule.carrying_opening) }),
          prior ? el("td.num.muted", { text: UI.rs(prior.carrying_opening) }) : null
        ])
      ];
      var carryHead = ["Carrying amount", { label: bsYear(data.to_ad), num: true }];
      if (prior) { carryHead.push({ label: bsYear(data.compare.to_ad), num: true }); }
      target.appendChild(el("div", {}, [
        el("h3", { text: "Carrying amount" }),
        UI.table(carryHead, carryRows)
      ]));

      target.appendChild(drillHost);
      Drill.mount(drillHost);
    }

    function drawRegister(target) {
      lazy(target, "register", "/api/assets",
           { from_ad: data.from_ad, to_ad: data.to_ad }, function (t, register) {
        if (!register.rows.length) {
          t.appendChild(el("div.empty", {}, [
            el("strong", { text: "The register is empty" }),
            el("span", { text: "Add what the business owns under Records, Fixed assets, and "
              + "the schedules here fill in by themselves." })
          ]));
          return;
        }
        var currentClass = null;
        var rows = [];
        register.rows.forEach(function (asset) {
          if (asset.tax_class !== currentClass) {
            currentClass = asset.tax_class;
            rows.push(el("tr.group-row", {}, [
              el("td", { colspan: "9", text: "Class " + currentClass + " under Schedule 2" })
            ]));
          }
          rows.push(el("tr" + (asset.disposed ? ".cancelled" : ""), {}, [
            el("td", { text: asset.code }),
            el("td", { text: asset.name }),
            el("td", { text: asset.acquired_bs }),
            el("td.num", { text: UI.rs(asset.cost) }),
            el("td.num", { text: UI.rs(asset.opening_accumulated, { blankZero: true }) }),
            el("td.num", { text: UI.rs(asset.charge, { blankZero: true }) }),
            el("td.num", { text: UI.rs(asset.closing_accumulated, { blankZero: true }) }),
            el("td.num", { text: UI.rs(asset.carrying) }),
            el("td.muted", { text: asset.location || "", style: "font-size:.76rem" })
          ]));
        });
        t.appendChild(UI.table([
          "Code", "Asset", "Bought", { label: "Cost", num: true },
          { label: "Depreciation b/f", num: true }, { label: "Charge", num: true },
          { label: "Depreciation c/f", num: true }, { label: "Carrying amount", num: true },
          "Where it is"
        ], rows, [el("tr.grand-row", {}, [
          el("td", { colspan: "3", text: "Total of assets held" }),
          el("td.num", { text: UI.rs(register.totals.cost) }),
          el("td.num", { text: UI.rs(register.totals.opening_accumulated) }),
          el("td.num", { text: UI.rs(register.totals.charge) }),
          el("td.num", { text: UI.rs(register.totals.closing_accumulated) }),
          el("td.num", { text: UI.rs(register.totals.carrying) }),
          el("td")
        ])], { tall: true }));
      });
    }

    function drawTaxDepreciation(target) {
      lazy(target, "taxdep", "/api/schedules/tax-depreciation", {}, function (t, working) {
        var rows = [];
        var order = ["A", "B", "C", "D", "E"];
        order.forEach(function (code) {
          var pool = working.pools[code];
          if (!pool) { return; }
          var quiet = !pool.opening && !pool.additions && !pool.disposals;
          if (quiet) { return; }
          rows.push(el("tr", {}, [
            el("td", {}, [
              el("div", { text: "Class " + code + "  at " + (pool.rate_bp / 100) + "%" }),
              el("div.muted", { style: "font-size:.74rem;max-width:280px",
                                text: pool.description })
            ]),
            el("td.num", { text: UI.rs(pool.opening) }),
            el("td.num", { text: UI.rs(pool.additions, { blankZero: true }) }),
            el("td.num", { text: UI.rs(pool.absorbed, { blankZero: true }) }),
            el("td.num", { text: UI.rs(pool.disposals, { blankZero: true }) }),
            el("td.num", { text: UI.rs(pool.base) }),
            el("td.num", { text: UI.rs(pool.depreciation) }),
            el("td.num", { text: UI.rs(pool.closing) })
          ]));
          pool.items.forEach(function (item) {
            rows.push(el("tr", {}, [
              el("td.indent.muted", { style: "font-size:.78rem",
                text: item.name + "  ·  " + item.acquired_bs
                      + (item.fraction ? "  ·  " + item.fraction + " absorbed" : "") }),
              el("td.num"), el("td.num.muted", { text: UI.rs(item.cost) }),
              el("td.num.muted", { text: UI.rs(item.absorbed, { blankZero: true }) }),
              el("td.num"), el("td.num"), el("td.num"), el("td.num")
            ]));
          });
          if (pool.small_pool) {
            rows.push(el("tr", {}, [el("td.indent", { colspan: "8",
              style: "color:var(--warn);font-size:.78rem",
              text: "The pool is below two thousand rupees, so the whole balance is allowed "
                    + "as depreciation under Schedule 2, section 2." })]));
          }
        });

        if (!rows.length) {
          t.appendChild(el("div.empty", {}, [
            el("strong", { text: "No depreciable assets on the register" }),
            el("span", { text: "Add them under Records, Fixed assets and this working "
              + "builds itself, year by year, from the first one." })
          ]));
          return;
        }

        t.appendChild(UI.table([
          "Pool", { label: "Brought forward", num: true }, { label: "Bought", num: true },
          { label: "Absorbed", num: true }, { label: "Sold", num: true },
          { label: "Depreciation base", num: true }, { label: "Depreciation", num: true },
          { label: "Carried forward", num: true }
        ], rows, [el("tr.grand-row", {}, [
          el("td", { text: "Total" }),
          el("td.num", { text: UI.rs(working.totals.opening) }),
          el("td.num", { text: UI.rs(working.totals.additions) }),
          el("td.num", { text: UI.rs(working.totals.absorbed) }),
          el("td.num", { text: UI.rs(working.totals.disposals) }),
          el("td.num", { text: UI.rs(working.totals.base) }),
          el("td.num", { text: UI.rs(working.totals.depreciation) }),
          el("td.num", { text: UI.rs(working.totals.closing) })
        ])]));

        t.appendChild(el("div.card", { style: "margin-top:1rem;background:var(--raised)" }, [
          el("h3", { text: "How the absorption works" }),
          el("p.card-note", { text: "Something bought in the first four months of the income "
            + "year, Shrawan to Kartik, goes into the pool in full. In the middle four months, "
            + "Mangsir to Falgun, two thirds of it goes in. In the last four, Chaitra to "
            + "Ashadh, one third. What is not absorbed this year is carried forward and joins "
            + "the pool next year." }),
          el("p.card-note", { text: "A disposal takes what the asset sold for out of the pool, "
            + "not what it cost, so no gain or loss on sale arises for tax while the pool "
            + "still has a balance." }),
          el("p.card-note", { text: "Rates change with the Finance Act. Check the rate for the "
            + "year before this working is used in a return." })
        ]));
      });
    }

    function drawDeferred(target) {
      lazy(target, "deferred", "/api/schedules/deferred-tax", {}, function (t, working) {
        var prior = working.previous;
        var rows = working.lines.map(function (line) {
          var cells = [
            el("td", {}, [
              el("div", { text: line.particular }),
              el("div.muted", { style: "font-size:.74rem;max-width:340px", text: line.note })
            ]),
            el("td.num", { text: UI.rs(line.book) }),
            el("td.num", { text: UI.rs(line.tax) }),
            el("td.num", { text: UI.rs(line.difference) })
          ];
          return el("tr", {}, cells);
        });
        t.appendChild(UI.table([
          "Particulars", { label: "Carried in the books", num: true },
          { label: "Carried for tax", num: true },
          { label: "Temporary difference", num: true }
        ], rows, [el("tr.sum-row", {}, [
          el("td", { text: "Net temporary difference" }),
          el("td.num", { text: UI.rs(working.book_value) }),
          el("td.num", { text: UI.rs(working.tax_value) }),
          el("td.num", { text: UI.rs(working.total_difference) })
        ])]));

        var summary = [
          el("tr", {}, [
            el("td", { text: "Tax rate applied" }),
            el("td.num", { text: (working.rate_bp / 100) + "%" })
          ]),
          el("tr.grand-row", {}, [
            el("td", { text: working.is_liability
              ? "Deferred tax liability" : "Deferred tax asset" }),
            el("td.num", { text: UI.rs(Math.abs(working.deferred_amount)) })
          ])
        ];
        if (prior) {
          summary.push(el("tr", {}, [
            el("td", { text: "Last year" }),
            el("td.num.muted", { text: UI.rs(Math.abs(prior.deferred_amount)) })
          ]));
          summary.push(el("tr", {}, [
            el("td", { text: "Charged or credited for the year" }),
            el("td.num", { text: UI.rs(working.movement) })
          ]));
        }
        t.appendChild(el("div", { style: "margin-top:1.2rem" }, [
          el("h3", { text: "Deferred tax recognised" }),
          UI.table(["Particulars", { label: "Amount", num: true }], summary)
        ]));

        t.appendChild(el("div.card", { style: "margin-top:1rem;background:var(--raised)" }, [
          el("p.card-note", { text: "Prepared under NAS 12. A difference is temporary where it "
            + "will reverse in a later year, which is what makes it recognisable now. Where the "
            + "books carry more than the tax working does, the difference is taxable and gives "
            + "a liability. Where they carry less, it is deductible and gives an asset." }),
          el("p.card-note", { text: "The tax rate is set under Company, and defaults to the "
            + "general rate of twenty five percent for a company in Nepal." })
        ]));
      });
    }

    function drawInstruments(target) {
      lazy(target, "instruments", "/api/schedules/financial-instruments", {
        from_ad: data.from_ad, to_ad: data.to_ad, compare: data.compare ? "1" : "0"
      }, function (t, note) {
        var showPrevious = !!data.compare;
        note.sections.forEach(function (section) {
          var rows = section.lines.map(function (line) {
            var cells = [
              el("td", { text: line.code }),
              el("td", { text: line.name }),
              el("td.num", { text: UI.rs(line.amount) })
            ];
            if (showPrevious) {
              cells.push(el("td.num.muted", { text: UI.rs(line.previous || 0) }));
            }
            return el("tr.openable", {
              onclick: function () { Drill.openLedger(line.account_id, line.name); }
            }, cells);
          });
          var head = ["Code", "Particulars", { label: bsYear(data.to_ad), num: true }];
          if (showPrevious) { head.push({ label: bsYear(data.compare.to_ad), num: true }); }
          var footCells = [el("td", { colspan: "2", text: "Total" }),
                           el("td.num", { text: UI.rs(section.total) })];
          if (showPrevious) {
            footCells.push(el("td.num.muted", { text: UI.rs(section.previous_total || 0) }));
          }
          t.appendChild(el("div", { style: "margin-bottom:1.1rem" }, [
            el("h3", { text: section.title }),
            UI.table(head, rows, [el("tr.sum-row", {}, footCells)])
          ]));
        });

        if (note.maturity && note.maturity.total) {
          var maturityRows = note.maturity.labels.map(function (label, index) {
            return el("tr", {}, [
              el("td", { text: label }),
              el("td.num", { text: UI.rs(note.maturity.amounts[index]) })
            ]);
          });
          t.appendChild(el("div", { style: "margin-bottom:1.1rem" }, [
            el("h3", { text: "When the financial liabilities fall due" }),
            UI.table(["Falling due", { label: "Amount", num: true }], maturityRows,
              [el("tr.sum-row", {}, [
                el("td", { text: "Total" }),
                el("td.num", { text: UI.rs(note.maturity.total) })
              ])])
          ]));
        }

        if (note.credit_concentration.length) {
          var creditRows = note.credit_concentration.map(function (row) {
            return el("tr", {}, [
              el("td", { text: row.name }),
              el("td.num", { text: UI.rs(row.amount) }),
              el("td.num", { text: (row.share_bp / 100).toFixed(1) + "%" })
            ]);
          });
          t.appendChild(el("div", { style: "margin-bottom:1.1rem" }, [
            el("h3", { text: "Where the credit risk sits" }),
            UI.table(["Customer", { label: "Owed", num: true },
                      { label: "Share of receivables", num: true }], creditRows),
            el("p.card-note", { style: "margin-top:.5rem", text:
              "The largest single customer accounts for "
              + (note.largest_share_bp / 100).toFixed(1) + " percent of what is owed to the "
              + "business." })
          ]));
        }

        if (note.excluded.length) {
          var excludedRows = note.excluded.map(function (line) {
            return el("tr", {}, [
              el("td", { text: line.code }),
              el("td", { text: line.name }),
              el("td.num", { text: UI.rs(line.amount) }),
              el("td.muted", { text: line.reason, style: "font-size:.78rem" })
            ]);
          });
          t.appendChild(el("div", {}, [
            el("h3", { text: "Balances that are not financial instruments" }),
            UI.table(["Code", "Particulars", { label: "Amount", num: true }, "Why not"],
                     excludedRows),
            el("p.card-note", { style: "margin-top:.5rem", text:
              "Set out so the reader can see that nothing has been left out by accident." })
          ]));
        }

        t.appendChild(drillHost);
        Drill.mount(drillHost);
      });
    }

    /* Traditional trading account */

    function drawTrading(target) {
      var t = data.trading;
      var pl = data.profit_or_loss.detail;
      var maxRows = Math.max(t.debit.length, t.credit.length);
      var rows = [];
      for (var i = 0; i < maxRows; i++) {
        var left = t.debit[i], right = t.credit[i];
        rows.push(el("tr", {}, [
          el("td", { text: left ? left.name : "" }),
          el("td.num", { text: left ? UI.rs(left.amount) : "" }),
          el("td", { text: right ? right.name : "" }),
          el("td.num", { text: right ? UI.rs(right.amount) : "" })
        ]));
      }
      if (t.gross_profit >= 0) {
        rows.push(el("tr", {}, [
          el("td", { text: "Gross profit carried down" }),
          el("td.num", { text: UI.rs(t.gross_profit) }),
          el("td", { text: "" }), el("td.num", { text: "" })
        ]));
      } else {
        rows.push(el("tr", {}, [
          el("td", { text: "" }), el("td.num", { text: "" }),
          el("td", { text: "Gross loss carried down" }),
          el("td.num", { text: UI.rs(-t.gross_profit) })
        ]));
      }
      var totalSide = Math.max(t.total_debit + Math.max(t.gross_profit, 0),
                               t.total_credit + Math.max(-t.gross_profit, 0));
      target.appendChild(el("h3", { text: "Trading Account", style: "margin-top:.4rem" }));
      target.appendChild(UI.table(
        ["Particulars", { label: "Amount", num: true },
         "Particulars", { label: "Amount", num: true }],
        rows,
        [el("tr.grand-row", {}, [
          el("td", { text: "" }), el("td.num", { text: UI.rs(totalSide) }),
          el("td", { text: "" }), el("td.num", { text: UI.rs(totalSide) })
        ])]));

      target.appendChild(el("h3", { text: "Profit and Loss Account",
                                    style: "margin-top:1.2rem" }));
      var plRows = [];
      [["employee", "Employee benefit expenses"], ["administrative", "Administrative expenses"],
       ["selling", "Selling and distribution expenses"], ["finance", "Finance costs"],
       ["depreciation", "Depreciation and amortisation"],
       ["other_expense", "Other expenses"], ["tax", "Income tax"]].forEach(function (pair) {
        var amount = pl[pair[0]];
        if (!amount) { return; }
        plRows.push(el("tr.openable", {
          onclick: function () { openSection(pair[0], pair[1]); }
        }, [
          el("td", { text: pair[1] }), el("td.num", { text: UI.rs(amount) }),
          el("td", { text: "" }), el("td.num", { text: "" })
        ]));
      });
      plRows.unshift(el("tr", {}, [
        el("td", { text: "" }), el("td.num", { text: "" }),
        el("td", { text: t.gross_profit >= 0 ? "Gross profit brought down" : "Gross loss brought down" }),
        el("td.num", { text: UI.rs(Math.abs(t.gross_profit)) })
      ]));
      if (pl.other_income) {
        plRows.push(el("tr.openable", {
          onclick: function () { openSection("other_income", "Other income"); }
        }, [
          el("td", { text: "" }), el("td.num", { text: "" }),
          el("td", { text: "Other income" }), el("td.num", { text: UI.rs(pl.other_income) })
        ]));
      }
      plRows.push(el("tr.sum-row", {}, [
        el("td", { text: pl.profit_after_tax >= 0 ? "Net profit" : "" }),
        el("td.num", { text: pl.profit_after_tax >= 0 ? UI.rs(pl.profit_after_tax) : "" }),
        el("td", { text: pl.profit_after_tax < 0 ? "Net loss" : "" }),
        el("td.num", { text: pl.profit_after_tax < 0 ? UI.rs(-pl.profit_after_tax) : "" })
      ]));
      target.appendChild(UI.table(
        ["Particulars", { label: "Amount", num: true },
         "Particulars", { label: "Amount", num: true }], plRows));
      target.appendChild(drillHost);
      Drill.mount(drillHost);
    }

    page.appendChild(el("div.card", {}, [
      bar,
      el("div.row", { style: "margin:-.3rem 0 .6rem" }, [
        el("label.check", {}, [compare, el("span", { text: "Show last year beside this year" })])
      ]),
      tabs
    ]));
    page.appendChild(el("div.card", {}, [box]));
    return load();
  });

  return {};
}());
