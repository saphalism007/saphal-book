/* Audit tools.

   The first pass over a set of books: what does not look right, what the
   ratios say, how old the stock is, and the same review run over a trial
   balance somebody has handed over on paper. */

var AuditTools = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  var SEVERITY = {
    high: { label: "Needs attention", cls: "bad" },
    medium: { label: "Worth checking", cls: "warn" },
    low: { label: "Observation", cls: "" },
    info: { label: "Note", cls: "" }
  };

  function findingCard(finding) {
    var meta = SEVERITY[finding.severity] || SEVERITY.info;
    var body = el("div.finding", {}, [
      el("div.finding-head", {}, [
        el("span.pill" + (meta.cls ? "." + meta.cls : ""), { text: meta.label }),
        el("span.finding-area", { text: finding.area }),
        finding.amount
          ? el("span.num.finding-amount", { text: UI.rs(finding.amount) })
          : null
      ]),
      el("div.finding-title", { text: finding.title }),
      el("div.finding-detail", { text: finding.detail }),
      finding.reference
        ? el("div.finding-ref", { text: finding.reference }) : null
    ]);

    if (finding.items && finding.items.length) {
      var rows = finding.items.map(function (item) {
        var cells = [el("td", { text: item.name || item.note || item.code || "" })];
        if (item.note && item.name) { cells.push(el("td.muted", { text: item.note })); }
        else { cells.push(el("td")); }
        cells.push(el("td.num", { text: item.amount ? UI.rs(item.amount) : "" }));
        var clickable = item.voucher_id || item.account_id || item.item_id;
        return el("tr" + (clickable ? ".clickable" : ""), {
          onclick: !clickable ? null : function () {
            if (item.voucher_id) { Vouchers.view(item.voucher_id); }
            else if (item.account_id) { Reports.openLedger(item.account_id); }
            else if (item.item_id) { Reports.openItemMovement(item.item_id); }
          }
        }, cells);
      });
      var open = false;
      var holder = el("div", { style: "display:none;margin-top:.5rem" }, [
        UI.table(["What", "", { label: "Amount", num: true }], rows)
      ]);
      body.appendChild(el("button.link-button", {
        text: "Show the " + finding.items.length + " item"
              + (finding.items.length === 1 ? "" : "s"),
        style: "margin-top:.4rem",
        onclick: function (event) {
          open = !open;
          holder.style.display = open ? "" : "none";
          event.currentTarget.textContent = (open ? "Hide the " : "Show the ")
            + finding.items.length + " item" + (finding.items.length === 1 ? "" : "s");
        }
      }));
      body.appendChild(holder);
    }
    return body;
  }

  App.register("audit-tools", function (page) {
    var chosen = App.state.auditTab || "flags";
    var tabs = el("div.stmt-tabs");
    var box = el("div");
    var bar = Reports.periodBar(function () { load(); });

    [["flags", "Red flags"], ["ratios", "Ratios"], ["stock", "Stock ageing"],
     ["tb", "Review a trial balance"]].forEach(function (pair) {
      tabs.appendChild(el("button" + (chosen === pair[0] ? ".on" : ""), {
        text: pair[1],
        onclick: function (event) {
          chosen = pair[0];
          App.state.auditTab = chosen;
          UI.qsa("button", tabs).forEach(function (b) { b.classList.remove("on"); });
          event.currentTarget.classList.add("on");
          load();
        }
      }));
    });

    function load() {
      UI.clear(box);
      if (chosen === "tb") { return drawTrialBalance(box); }
      if (chosen === "stock") { return drawStockAgeing(box); }
      box.appendChild(el("div.empty", { text: "Going through the books…" }));
      return api("/api/audit/review", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
      }}).then(function (data) {
        UI.clear(box);
        if (chosen === "ratios") { drawRatios(box, data); }
        else { drawFlags(box, data); }
      }).catch(function (error) {
        UI.clear(box).appendChild(el("div.empty", { text: error.message }));
      });
    }

    function drawFlags(target, data) {
      target.appendChild(el("div.grid.four", { style: "margin-bottom:1rem" }, [
        tile("Needs attention", String(data.counts.high), "Deal with these first",
             data.counts.high ? "bad" : "good"),
        tile("Worth checking", String(data.counts.medium), "Ask about each one",
             data.counts.medium ? "amber" : "good"),
        tile("Observations", String(data.counts.low), "Background", "teal"),
        tile("Reviewed to", UI.bs(data.to_ad, "short"), data.to_ad, "violet")
      ]));

      if (!data.findings.length) {
        target.appendChild(el("div.empty", {}, [
          el("strong", { text: "Nothing came back" }),
          el("span", { text: "None of the checks found anything. That is not the same as an "
            + "audit opinion, but it is a good place to start from." })
        ]));
        return;
      }

      var areas = {};
      data.findings.forEach(function (finding) {
        (areas[finding.area] = areas[finding.area] || []).push(finding);
      });
      Object.keys(areas).forEach(function (area) {
        target.appendChild(el("div.card", {}, [
          el("div.card-head", {}, [el("h2", { text: area })])
        ].concat(areas[area].map(findingCard))));
      });

      target.appendChild(el("p.card-note", { text:
        "These are the things a first pass throws up. Each one needs looking at before it "
        + "means anything, and none of it replaces the work an audit actually requires." }));
    }

    function drawRatios(target, data) {
      var r = data.ratios;
      function line(label, value, note, suffix) {
        return el("tr", {}, [
          el("td", {}, [
            el("div", { text: label }),
            note ? el("div.muted", { style: "font-size:.76rem", text: note }) : null
          ]),
          el("td.num", { text: value === null || value === undefined
            ? "not meaningful" : (value + (suffix || "")) })
        ]);
      }
      target.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Liquidity" })]),
        UI.table(["Ratio", { label: "Result", num: true }], [
          line("Current ratio", r.current_ratio,
               "Current assets against current liabilities. Below one means what falls due "
               + "within the year is not covered by what turns into cash within it."),
          line("Quick ratio", r.quick_ratio,
               "The same without stock, since stock has to be sold before it is cash."),
          line("Working capital", UI.rs(r.working_capital),
               "Current assets less current liabilities.")
        ])
      ]));
      target.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "How long money takes to move" })]),
        UI.table(["Measure", { label: "Days", num: true }], [
          line("Receivable days", r.receivable_days,
               "How long customers take to pay. Compare it against the credit terms given."),
          line("Payable days", r.payable_days,
               "How long the business takes to pay suppliers."),
          line("Inventory days", r.inventory_days,
               "How long stock sits before it sells.")
        ])
      ]));
      target.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Profitability and gearing" })]),
        UI.table(["Measure", { label: "Result", num: true }], [
          line("Gross margin", r.gross_margin_pct, "Gross profit as a share of revenue.", "%"),
          line("Net margin", r.net_margin_pct, "Profit after everything, on revenue.", "%"),
          line("Debt to equity", r.debt_to_equity,
               "Borrowings against what the owners have in.")
        ])
      ]));
      target.appendChild(el("p.card-note", { text:
        "A ratio on its own says nothing. It is worth something compared against last year, "
        + "against the terms actually agreed, and against what the trade normally runs at." }));
    }

    function drawStockAgeing(target) {
      target.appendChild(el("div.empty", { text: "Working out how long it has been there…" }));
      return api("/api/reports/stock-ageing", { query: { as_at: bar.to.getIso() } })
        .then(function (data) {
          UI.clear(target);
          target.appendChild(Reports.reportHead("Stock Ageing",
            "As at " + UI.bs(data.as_at_ad, "long") + "   (" + data.as_at_ad + ")"));

          target.appendChild(el("div.grid.four", { style: "margin-bottom:1rem" }, [
            tile("Stock on hand", UI.rs(data.grand_value), "At weighted average cost", "teal"),
            tile("Over 180 days", UI.rs(data.old_value), "Consider whether it is still worth it",
                 data.old_value ? "amber" : "good"),
            tile("Slow moving", String(data.slow_count), "No sale in six months",
                 data.slow_count ? "amber" : "good"),
            tile("Never sold", String(data.never_sold_count), "Bought but never gone out",
                 data.never_sold_count ? "bad" : "good")
          ]));

          var rows = data.rows.map(function (row) {
            var cells = [
              el("td", { text: row.code }),
              el("td", {}, [
                el("div", { text: row.name }),
                row.group_name
                  ? el("div.muted", { style: "font-size:.74rem", text: row.group_name }) : null
              ]),
              el("td.num", { text: NP.formatQty(row.qty) + " " + row.unit })
            ];
            row.bucket_value.forEach(function (amount, index) {
              cells.push(el("td.num" + (index >= 3 && amount ? ".negative" : ""),
                { text: UI.rs(amount, { blankZero: true }) }));
            });
            cells.push(el("td.num", { text: UI.rs(row.value) }));
            cells.push(el("td", {}, [
              row.never_sold ? el("span.pill.bad", { text: "never sold" })
                : row.slow_moving ? el("span.pill.warn", { text: "slow" }) : null
            ]));
            return el("tr.clickable", {
              onclick: function () { Reports.openItemMovement(row.item_id); }
            }, cells);
          });

          var head = ["Code", "Item", { label: "On hand", num: true }].concat(
            data.labels.map(function (l) { return { label: l, num: true }; }),
            [{ label: "Value", num: true }, ""]);
          var foot = [el("tr.total-row", {}, [
            el("td", { colspan: "3", text: "Total" })
          ].concat(
            data.totals_value.map(function (a) { return el("td.num", { text: UI.rs(a) }); }),
            [el("td.num", { text: UI.rs(data.grand_value) }), el("td")]))];

          target.appendChild(UI.table(head, rows, foot,
            { tall: true, emptyText: "No stock on hand." }));
          target.appendChild(el("p.card-note", { style: "margin-top:.6rem", text:
            "Quantity is aged first in first out, because the oldest one on the shelf is the "
            + "one that has been there longest. Value is put against each band at the "
            + "weighted average, so the total agrees with the balance sheet exactly." }));
        }).catch(function (error) {
          UI.clear(target).appendChild(el("div.empty", { text: error.message }));
        });
    }

    /* Someone else's trial balance */

    function drawTrialBalance(target) {
      var paste = el("textarea", { rows: "9", placeholder:
        "Paste the trial balance here. A name column and either a debit and a credit column, "
        + "or one signed amount column. Copying straight out of a spreadsheet works." });
      var fileInput = el("input", { type: "file", accept: ".csv,.txt,.tsv" });
      var resultBox = el("div");

      fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) { return; }
        var reader = new FileReader();
        reader.onload = function () { paste.value = String(reader.result); run(); };
        reader.onerror = function () { UI.flash("That file could not be read.", "bad"); };
        reader.readAsText(file);
      });

      function run() {
        if (!paste.value.trim()) { UI.flash("Paste a trial balance first.", "bad"); return; }
        UI.clear(resultBox).appendChild(el("div.empty", { text: "Reading it…" }));
        api("/api/audit/trial-balance", { body: { text: paste.value } })
          .then(function (data) { drawResult(data); })
          .catch(function (error) {
            UI.clear(resultBox).appendChild(el("div.empty", { text: error.message }));
          });
      }

      function drawResult(data) {
        UI.clear(resultBox);
        var s = data.summary;

        resultBox.appendChild(el("div.grid.four", { style: "margin-bottom:1rem" }, [
          tile("Lines read", String(data.count), "Totals row skipped", "violet"),
          tile("Debit", UI.rs(data.total_debit), "", "teal"),
          tile("Credit", UI.rs(data.total_credit), "", "teal"),
          tile(data.balanced ? "It casts" : "Out by",
               data.balanced ? "Yes" : UI.rs(Math.abs(data.difference)),
               data.balanced ? "Debit equals credit" : "Debit does not equal credit",
               data.balanced ? "good" : "bad")
        ]));

        if (data.review.findings.length) {
          resultBox.appendChild(el("div.card", {}, [
            el("div.card-head", {}, [el("h2", { text: "What stands out" })])
          ].concat(data.review.findings.map(findingCard))));
        }

        var rows = data.lines.map(function (line) {
          var select = UI.select(data.groups.map(function (g) {
            return { value: g.code, label: g.code + "  " + g.name };
          }), line.group_code, function (value) {
            line.group_code = value;
            remap();
          });
          return el("tr", {}, [
            el("td", { text: line.name }),
            el("td.num", { text: UI.rs(line.debit, { blankZero: true }) }),
            el("td.num", { text: UI.rs(line.credit, { blankZero: true }) }),
            el("td", { style: "min-width:230px" }, [select]),
            el("td", {}, [
              line.confidence === "none"
                ? el("span.pill.bad", { text: "not recognised" })
                : line.confidence === "fair"
                ? el("span.pill.warn", { text: "check" })
                : el("span.pill.good", { text: "matched" })
            ])
          ]);
        });

        var summaryBox = el("div");
        function drawSummary(current) {
          UI.clear(summaryBox);
          summaryBox.appendChild(UI.table(["Particulars", { label: "Amount", num: true }], [
            row("Revenue", current.revenue), row("Cost of sales", current.cost_of_sales),
            row("Gross profit", current.gross_profit, true),
            row("Other income", current.other_income),
            row("Operating expenses", current.operating_expense),
            row("Finance cost", current.finance),
            row("Depreciation", current.depreciation),
            row("Other expenses", current.other_expense),
            row("Profit before tax", current.profit_before_tax, true),
            row("Tax", current.tax),
            row("Profit", current.profit, true),
            row("Total assets", current.total_assets),
            row("Total liabilities", current.total_liabilities),
            row("Total equity including the profit", current.total_equity),
            row(current.balanced ? "The statements balance"
                : "The statements are out by", Math.abs(current.difference), true)
          ]));
        }
        function row(label, amount, strong) {
          return el("tr" + (strong ? ".sum-row" : ""), {}, [
            el("td", { text: label }), el("td.num", { text: UI.rs(amount) })
          ]);
        }

        function remap() {
          api("/api/audit/trial-balance/remap", { body: { lines: data.lines } })
            .then(function (result) {
              drawSummary(result.summary);
            }).catch(function (error) { UI.flash(error.message, "bad"); });
        }

        resultBox.appendChild(el("div.card", {}, [
          el("div.card-head", {}, [
            el("h2", { text: "What each line is" }),
            el("span.card-note", { text: "Change anything that has been guessed wrongly." })
          ]),
          UI.table(["Account", { label: "Debit", num: true }, { label: "Credit", num: true },
                    "Mapped to", ""], rows, null, { tall: true })
        ]));

        resultBox.appendChild(el("div.card", {}, [
          el("div.card-head", {}, [el("h2", { text: "What it comes to" })]),
          summaryBox
        ]));
        drawSummary(s);
      }

      target.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Review a trial balance" })]),
        el("p.card-note", { text: "For a set of books kept somewhere else. Paste the trial "
          + "balance or choose a file, and it is matched to the standard chart of accounts, "
          + "cast, drawn up into statements, and looked over. Nothing is saved and nothing "
          + "is posted." }),
        el("div.field", { style: "margin-top:.7rem" }, [paste]),
        el("div.row", {}, [
          el("button.primary", { text: "Read it", onclick: run }),
          el("div.field", { style: "margin:0" }, [fileInput])
        ])
      ]));
      target.appendChild(resultBox);
    }

    function tile(label, value, note, kind) {
      return el("div.tile" + (kind ? "." + kind : ""), {}, [
        el("div.tile-label", { text: label }),
        el("div.tile-value", { text: value }),
        note ? el("div.tile-note", { text: note }) : null
      ]);
    }

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [el("h2", { text: "Audit tools" })]),
      bar, tabs
    ]));
    page.appendChild(box);
    return load();
  });

  /* The reference */

  App.register("reference", function (page) {
    return api("/api/reference").then(function (data) {
      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Law and standards, for reference" })]),
        el("p.card-note", { text: "A working aid, not authority. Rates and thresholds move "
          + "with each Finance Act. Anything with a figure in it should be checked against "
          + "the current law before it is relied on in a return, a set of accounts or an "
          + "opinion. Last gone through in " + data.updated + "." })
      ]));

      data.sections.forEach(function (section) {
        var body = el("div");
        section.items.forEach(function (item) {
          body.appendChild(el("div.ref-item", {}, [
            el("div.ref-heading", { text: item.heading }),
            el("div.ref-body", { text: item.body }),
            el("div.ref-foot", {}, [
              item.reference ? el("span.ref-source", { text: item.reference }) : null,
              item.caution ? el("span.ref-caution", { text: item.caution }) : null
            ])
          ]));
        });
        page.appendChild(el("div.card", {}, [
          el("div.card-head", {}, [
            el("h2", { text: section.title }),
            el("span.card-note", { text: section.summary })
          ]),
          section.caution
            ? el("div.flash.warn", { style: "margin:0 0 .7rem", text: section.caution })
            : null,
          body
        ]));
      });
    });
  });

  return {};
}());
