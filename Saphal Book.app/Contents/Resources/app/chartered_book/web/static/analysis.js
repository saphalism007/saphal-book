/* Where the money came from, and whether it was worth selling.

   Sales and purchases read off the invoice lines rather than the ledger,
   because the ledger knows the amount and not the item. Three screens on the
   same shape: by customer or supplier, by item, and what each item made. */

var Analysis = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  /* A Bikram Sambat month, as it is stored on a voucher: 2083-05. Turned into
     something a person reads, Bhadra 2083, rather than left as a number. */
  function bsMonth(period) {
    if (!period) { return ""; }
    var bits = String(period).split("-");
    var year = bits[0], month = parseInt(bits[1], 10);
    var names = UI.getLang() === "np" ? NP.MONTHS_NP : NP.MONTHS_EN;
    return (names[month - 1] || bits[1]) + " " + year;
  }

  function head(title, bar) {
    return Reports.reportHead(title, Reports.periodText(bar.from.getIso(), bar.to.getIso()));
  }

  /* Sales and purchases, by whoever was on the other side of the bill */

  function partyScreen(side, title) {
    return function (page) {
      var monthly = el("input", { type: "checkbox" });
      var box = el("div");
      var bar = Reports.periodBar(load);
      bar.insertBefore(el("label.check", {}, [
        monthly, el("span", { text: "Month by month" })
      ]), bar.lastChild);
      monthly.addEventListener("change", load);

      function load() {
        return api("/api/reports/by-party", { query: {
          side: side, from_ad: bar.from.getIso(), to_ad: bar.to.getIso(),
          monthly: monthly.checked ? "1" : "0"
        }}).then(draw);
      }

      function draw(data) {
        UI.clear(box);
        box.appendChild(head(title, bar));
        var headers = [data.counterparty];
        if (data.monthly) { headers.push("Month"); }
        headers = headers.concat([
          { label: "Bills", num: true },
          { label: "Taxable", num: true },
          { label: "VAT", num: true },
          { label: "Discount", num: true },
          { label: "Total", num: true }
        ]);

        var rows = data.rows.map(function (row) {
          var cells = [el("td", { text: row.party })];
          if (data.monthly) { cells.push(el("td", { text: bsMonth(row.period) })); }
          cells.push(el("td.num", { text: String(row.bills) }));
          cells.push(el("td.num", { text: UI.rs(row.taxable) }));
          cells.push(el("td.num", { text: UI.rs(row.vat, { blankZero: true }) }));
          cells.push(el("td.num", { text: UI.rs(row.discount, { blankZero: true }) }));
          cells.push(el("td.num", { text: UI.rs(row.amount) }));
          return el("tr", {}, cells);
        });

        var footCells = [el("td", { text: "Total" })];
        if (data.monthly) { footCells.push(el("td")); }
        footCells.push(el("td.num", { text: String(data.totals.bills) }));
        footCells.push(el("td.num", { text: UI.rs(data.totals.taxable) }));
        footCells.push(el("td.num", { text: UI.rs(data.totals.vat) }));
        footCells.push(el("td.num", { text: UI.rs(data.totals.discount) }));
        footCells.push(el("td.num", { text: UI.rs(data.totals.amount) }));

        box.appendChild(UI.table(headers, rows, [el("tr.grand-row", {}, footCells)],
                                 { emptyText: "Nothing in this period." }));
        box.appendChild(el("div.row.no-print", { style: "margin-top:.7rem" }, [
          UI.exportButton(box, title),
          el("button.secondary", { text: "Print", onclick: UI.printPage })
        ]));
      }

      page.appendChild(bar);
      page.appendChild(box);
      return load();
    };
  }

  /* The same, item by item */

  function itemScreen(side, title) {
    return function (page) {
      var monthly = el("input", { type: "checkbox" });
      var box = el("div");
      var bar = Reports.periodBar(load);
      bar.insertBefore(el("label.check", {}, [
        monthly, el("span", { text: "Month by month" })
      ]), bar.lastChild);
      monthly.addEventListener("change", load);

      function load() {
        return api("/api/reports/by-item", { query: {
          side: side, from_ad: bar.from.getIso(), to_ad: bar.to.getIso(),
          monthly: monthly.checked ? "1" : "0"
        }}).then(draw);
      }

      function draw(data) {
        UI.clear(box);
        box.appendChild(head(title, bar));
        var headers = ["Item"];
        if (data.monthly) { headers.push("Month"); }
        headers = headers.concat([
          { label: "Quantity", num: true }, "Unit",
          { label: "Average rate", num: true },
          { label: "Discount", num: true },
          { label: "Total", num: true }
        ]);

        var rows = data.rows.map(function (row) {
          var cells = [el("td", {}, [
            el("div", { text: row.item }),
            row.code ? el("div.muted", { style: "font-size:.74rem", text: row.code }) : null
          ])];
          if (data.monthly) { cells.push(el("td", { text: bsMonth(row.period) })); }
          cells.push(el("td.num", { text: NP.formatQty(row.qty) }));
          cells.push(el("td", { text: row.unit || "" }));
          cells.push(el("td.num", { text: UI.rs(row.average_rate) }));
          cells.push(el("td.num", { text: UI.rs(row.discount, { blankZero: true }) }));
          cells.push(el("td.num", { text: UI.rs(row.amount) }));
          return el("tr", {}, cells);
        });

        var footCells = [el("td", { text: "Total" })];
        if (data.monthly) { footCells.push(el("td")); }
        footCells.push(el("td.num"), el("td"), el("td.num"));
        footCells.push(el("td.num", { text: UI.rs(data.totals.discount) }));
        footCells.push(el("td.num", { text: UI.rs(data.totals.amount) }));

        box.appendChild(UI.table(headers, rows, [el("tr.grand-row", {}, footCells)],
                                 { emptyText: "Nothing in this period." }));
        box.appendChild(el("div.row.no-print", { style: "margin-top:.7rem" }, [
          UI.exportButton(box, title),
          el("button.secondary", { text: "Print", onclick: UI.printPage })
        ]));
      }

      page.appendChild(bar);
      page.appendChild(box);
      return load();
    };
  }

  /* What each item actually made */

  App.register("profitability", function (page) {
    var box = el("div");
    var bar = Reports.periodBar(load);

    function load() {
      return api("/api/reports/profitability", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
      }}).then(draw);
    }

    function draw(data) {
      UI.clear(box);
      box.appendChild(head("What each item made", bar));

      if (data.any_missing_cost) {
        box.appendChild(el("div.card-note", {
          style: "border-left:3px solid var(--warn);padding-left:.6rem;margin:.3rem 0",
          text: "Some lines carry no cost, so their margin is left blank rather than "
                + "shown as pure profit. Cost is recorded on a sale from the day "
                + "perpetual inventory was turned on, so sales entered before that "
                + "have none."
        }));
      }

      var rows = data.rows.map(function (row) {
        return el("tr", {}, [
          el("td", {}, [
            el("div", { text: row.item }),
            row.code ? el("div.muted", { style: "font-size:.74rem", text: row.code }) : null
          ]),
          el("td.num", { text: NP.formatQty(row.qty) }),
          el("td.num", { text: UI.rs(row.revenue) }),
          el("td.num", { text: row.known_cost ? UI.rs(row.cost) : "" }),
          el("td.num", { text: row.known_cost ? UI.rs(row.profit) : "" }),
          el("td.num", { text: row.margin_bp === null ? "not known"
                                                      : (row.margin_bp / 100).toFixed(1) + "%" })
        ]);
      });

      box.appendChild(UI.table(
        ["Item", { label: "Quantity", num: true }, { label: "Revenue", num: true },
         { label: "Cost", num: true }, { label: "Profit", num: true },
         { label: "Margin", num: true }],
        rows,
        [el("tr.grand-row", {}, [
          el("td", { text: "Total" }), el("td.num"),
          el("td.num", { text: UI.rs(data.totals.revenue) }),
          el("td.num", { text: data.any_missing_cost ? "" : UI.rs(data.totals.cost) }),
          el("td.num", { text: data.any_missing_cost ? "" : UI.rs(data.totals.profit) }),
          el("td.num", { text: data.totals.margin_bp === null ? "not known"
                               : (data.totals.margin_bp / 100).toFixed(1) + "%" })
        ])],
        { emptyText: "Nothing sold in this period." }));

      // Why this does not equal the profit and loss, said here rather than
      // left for somebody to find and worry about.
      if (data.settlement_discount) {
        box.appendChild(el("div.card", {}, [
          el("div.card-head", {}, [el("h2", { text: "Against the profit and loss" })]),
          UI.table(["", { label: "Amount", num: true }], [
            el("tr", {}, [el("td", { text: "Invoiced, as above" }),
                          el("td.num", { text: UI.rs(data.totals.revenue) })]),
            el("tr", {}, [el("td", { text: "Less discount allowed at settlement" }),
                          el("td.num", { text: "(" + UI.rs(data.settlement_discount) + ")" })])
          ], [el("tr.grand-row", {}, [
            el("td", { text: "Revenue in the profit and loss" }),
            el("td.num", { text: UI.rs(data.revenue_after_settlement) })
          ])]),
          el("p.card-note", { text: "A discount given when the bill is settled is decided "
            + "after the invoice, so it never appears on a line. It still reduces revenue, "
            + "which is why the two differ." })
        ]));
      }

      box.appendChild(el("div.row.no-print", { style: "margin-top:.7rem" }, [
        UI.exportButton(box, "What each item made"),
        el("button.secondary", { text: "Print", onclick: UI.printPage })
      ]));
    }

    page.appendChild(bar);
    page.appendChild(box);
    return load();
  });

  /* The statutory registers.

     Not a management report. The sales book and the purchase book are what the
     Value Added Tax Rules, 2053 require to be kept, and what an inspection asks
     for first, so the columns are the ones on the prescribed form rather than
     the ones that would look tidiest. */

  function registerScreen(side, title, subtitle) {
    return function (page) {
      var box = el("div");
      var bar = Reports.periodBar(load);

      function load() {
        return api("/api/reports/vat-register", { query: {
          side: side, from_ad: bar.from.getIso(), to_ad: bar.to.getIso()
        }}).then(draw);
      }

      function draw(data) {
        UI.clear(box);
        box.appendChild(head(title, bar));
        box.appendChild(el("p.card-note", { style: "text-align:center;margin-top:-.3rem",
                                            text: subtitle }));

        var isPurchase = side === "purchase";
        var headers = ["Date", "Bill no.", isPurchase ? "Supplier" : "Buyer", "PAN",
                       { label: "Total", num: true },
                       { label: "Exempt", num: true },
                       { label: "Taxable", num: true },
                       { label: "VAT", num: true }];
        if (isPurchase) {
          headers = headers.concat([
            { label: "Capital taxable", num: true },
            { label: "Capital VAT", num: true }
          ]);
        }

        var rows = data.rows.map(function (row) {
          var cells = [
            el("td", { text: UI.bs(row.date_ad, "short") }),
            el("td", {}, [
              el("div", { text: row.number }),
              row.voucher_type.indexOf("return") >= 0 || row.voucher_type.indexOf("note") >= 0
                ? el("div.muted", { style: "font-size:.72rem", text: "return or note" })
                : null
            ]),
            el("td", { text: row.party_name }),
            el("td", { text: row.party_pan || "" }),
            el("td.num", { text: UI.rs(row.total) }),
            el("td.num", { text: UI.rs(row.exempt, { blankZero: true }) }),
            el("td.num", { text: UI.rs(row.taxable) }),
            el("td.num", { text: UI.rs(row.vat) })
          ];
          if (isPurchase) {
            cells.push(el("td.num", { text: row.capital ? UI.rs(row.taxable) : "" }));
            cells.push(el("td.num", { text: row.capital ? UI.rs(row.vat) : "" }));
          }
          return el("tr", {}, cells);
        });

        var foot = [
          el("td", { text: "Total" }), el("td"), el("td"), el("td"),
          el("td.num", { text: UI.rs(data.totals.total) }),
          el("td.num", { text: UI.rs(data.totals.exempt) }),
          el("td.num", { text: UI.rs(data.totals.taxable) }),
          el("td.num", { text: UI.rs(data.totals.vat) })
        ];
        if (isPurchase) {
          foot.push(el("td.num", { text: UI.rs(data.totals.capital_taxable || 0) }));
          foot.push(el("td.num", { text: UI.rs(data.totals.capital_vat || 0) }));
        }

        box.appendChild(UI.table(headers, rows, [el("tr.grand-row", {}, foot)],
                                 { emptyText: "Nothing in this period." }));

        if (isPurchase) {
          box.appendChild(el("p.card-note", { text: "A purchase counts as capital where "
            + "it landed on a fixed asset ledger, which the entry already says. Nothing "
            + "has to be marked twice." }));
        }

        box.appendChild(el("div.row.no-print", { style: "margin-top:.7rem" }, [
          UI.exportButton(box, title),
          el("button.secondary", { text: "Print", onclick: UI.printPage })
        ]));
      }

      page.appendChild(bar);
      page.appendChild(box);
      return load();
    };
  }

  App.register("sales-book", registerScreen("sales", "Sales book",
    "Bikri Khata, the register the Value Added Tax Rules, 2053 require"));
  App.register("purchase-book", registerScreen("purchase", "Purchase book",
    "Kharid Khata, the register the Value Added Tax Rules, 2053 require"));

  App.register("sales-by-customer", partyScreen("sales", "Sales by customer"));
  App.register("sales-by-item", itemScreen("sales", "Sales by item"));
  App.register("purchase-by-supplier", partyScreen("purchase", "Purchases by supplier"));
  App.register("purchase-by-item", itemScreen("purchase", "Purchases by item"));

  return {};
}());
