/* The income tax computation, under the Income Tax Act, 2058.

   Three tabs. The statement itself, which is what gets filed. The rates for
   the year, which Nepal changes every Jestha and which therefore live in the
   books rather than in the program. And the treatments, which say what the Act
   does with each ledger.

   Every figure on the statement comes out of the books. Nothing is typed
   twice, so nothing can disagree with the accounts it came from. */

var IncomeTax = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  // Amounts go into a box as plain rupees, because that is what gets typed
  // back out and what the server reads.
  function rupees(paisa) {
    return ((Math.round(Number(paisa) || 0)) / 100).toFixed(2);
  }

  var TABS = [
    ["statement", "Computation"],
    ["rates", "Rates for the year"],
    ["treatments", "Treatments"]
  ];

  App.register("income-tax", function (page) {
    var chosen = App.state.taxTab || "statement";
    var tabs = el("div.stmt-tabs");
    var box = el("div.stmt");
    var data = null;
    var settings = null;

    TABS.forEach(function (pair) {
      tabs.appendChild(el("button" + (chosen === pair[0] ? ".on" : ""), {
        text: pair[1],
        onclick: function (event) {
          chosen = pair[0];
          App.state.taxTab = chosen;
          UI.qsa("button", tabs).forEach(function (b) { b.classList.remove("on"); });
          event.currentTarget.classList.add("on");
          draw();
        }
      }));
    });

    function load() {
      return Promise.all([
        api("/api/income-tax"),
        api("/api/income-tax/settings")
      ]).then(function (both) {
        data = both[0];
        settings = both[1];
        draw();
      });
    }

    function draw() {
      UI.clear(box);
      if (!data) { return; }
      if (chosen === "statement") { drawStatement(box); }
      else if (chosen === "rates") { drawRates(box); }
      else { drawTreatments(box); }
    }

    /* The statement */

    function drawStatement(target) {
      target.appendChild(Reports.reportHead(
        "Computation of income tax",
        "Income year " + data.label + "   (" + data.from_ad + " to " + data.to_ad + ")"
          + "   ·   assessed as " + (data.assessed_as_label || "").toLowerCase()));

      (data.notices || []).forEach(function (line) {
        target.appendChild(el("div.card-note.no-print", {
          style: "border-left:3px solid var(--warn);padding-left:.6rem;margin:.3rem 0",
          text: line
        }));
      });

      var rows = data.rows.map(function (row) {
        var kind = row.kind || "";
        var cls = kind === "total" ? "tr.total-row"
                : kind === "grand" ? "tr.grand-row"
                : kind === "start" ? "tr.total-row" : "tr";
        return el(cls, {}, [
          el("td", {}, [
            el("div", { text: row.label }),
            row.note ? el("div.muted", { style: "font-size:.74rem;max-width:420px",
                                         text: row.note }) : null
          ]),
          el("td.num", { text: UI.rs(row.amount) })
        ]);
      });

      target.appendChild(UI.table(
        ["Particulars", { label: "Amount", num: true, width: "9rem" }],
        rows, null, {}));

      // What was added back, ledger by ledger. A single lump on a return is
      // the thing an assessing officer asks about first.
      if ((data.added_back || []).length) {
        target.appendChild(el("h3", { text: "What was added back" }));
        target.appendChild(UI.table(
          ["Ledger", "Why", { label: "In the books", num: true },
           { label: "Added back", num: true }],
          data.added_back.map(function (row) {
            return el("tr", {}, [
              el("td", { text: row.code + "  " + row.name }),
              el("td", {}, [
                el("div", { text: row.why || "" }),
                row.note ? el("div.muted", { style: "font-size:.74rem", text: row.note }) : null
              ]),
              el("td.num", { text: UI.rs(row.spent) }),
              el("td.num", { text: UI.rs(row.added_back) })
            ]);
          }),
          [el("tr.grand-row", {}, [
            el("td", { text: "Total added back" }), el("td"),
            el("td.num", { text: "" }),
            el("td.num", { text: UI.rs(data.additions) })
          ])]));
      }

      // How the tax itself was arrived at. Every band is shown, including the
      // ones the income did not reach, because a working that only shows the
      // bands that bit is harder to check than one that shows them all.
      target.appendChild(el("h3", { text: "How the tax was worked out" }));
      target.appendChild(UI.table(
        ["Band", { label: "Rate", num: true }, { label: "Income in the band", num: true },
         { label: "Tax", num: true }],
        (data.bands || []).map(function (band) {
          return el("tr" + (band.amount ? "" : ".muted"), {}, [
            el("td", {}, [
              el("div", { text: band.to === null
                ? "Above " + UI.rs(band.from)
                : UI.rs(band.from) + " to " + UI.rs(band.to) }),
              band.note ? el("div.muted", { style: "font-size:.74rem", text: band.note }) : null
            ]),
            el("td.num", { text: (band.rate_bp / 100) + "%" }),
            el("td.num", { text: UI.rs(band.amount, { blankZero: true }) }),
            el("td.num", { text: UI.rs(band.tax, { blankZero: true }) })
          ]);
        }),
        [el("tr.grand-row", {}, [
          el("td", { text: "Tax on taxable income" }), el("td.num"), el("td.num"),
          el("td.num", { text: UI.rs(data.tax) })
        ])]));

      if (data.loss_carried_forward) {
        target.appendChild(el("div.card-note", {
          text: "Loss carried forward to the next year: "
                + UI.rs(data.loss_carried_forward)
                + ".  Enter it under Rates for the year as the loss brought forward "
                + "once " + (data.start_bs_year + 1) + " is opened."
        }));
      }

      target.appendChild(el("div.row.no-print", { style: "margin-top:.8rem" }, [
        UI.exportButton(target, "Income tax " + data.label),
        el("button.secondary", { text: "Print", onclick: UI.printPage })
      ]));
    }

    /* The rates, and what has already been paid */

    function drawRates(target) {
      var who = el("select");
      (settings.rate_sets || []).forEach(function (set) {
        who.appendChild(el("option", { value: set.key, text: set.label }));
      });
      who.value = settings.assessed_as;

      var special = el("input", { type: "checkbox" });
      special.checked = !!settings.special_industry;
      var advance = UI.amountInput(rupees(settings.advance_tax_paid));
      var loss = UI.amountInput(rupees(settings.brought_forward_loss));

      target.appendChild(Reports.reportHead(
        "Rates and settings for " + data.label,
        "Nepal sets the rates afresh in the Finance Act each Jestha, so they are "
          + "kept here against the year they belong to rather than inside the program."));

      if (settings.rates_were_seeded) {
        target.appendChild(el("div.card-note", {
          style: "border-left:3px solid var(--warn);padding-left:.6rem",
          text: "Nobody has confirmed the rates for " + data.label + " yet. What is "
                + "shown below is a starting point. Check it against the Finance Act "
                + "for the year and press Save the rates."
        }));
      }

      var howBox = el("div.card", {}, [
        el("h3", { text: "How this year is assessed" }),
        el("div.row", {}, [
          UI.field("Assessed as", who),
          UI.field("Advance tax paid, if not in the books", advance),
          UI.field("Loss brought forward", loss),
          el("div.field", {}, [
            el("label.check", {}, [special,
              el("span", { text: "Special industry, section 11" })])
          ])
        ]),
        el("p.card-note", {
          text: "Advance tax is read off the Advance Income Tax ledger where it has "
                + "been posted there. The box above is only for a payment that has not "
                + "reached the books yet, and is ignored once the ledger has a figure." }),
        el("div.row", {}, [
          el("button.primary", { text: "Save", onclick: function () {
            return api("/api/income-tax/settings", { body: {
              assessed_as: who.value,
              special_industry: special.checked ? 1 : 0,
              advance_tax_paid: advance.value || 0,
              brought_forward_loss: loss.value || 0
            }}).then(function () {
              UI.flash("Saved.", "good");
              return load();
            }).catch(function (error) { UI.flash(error.message, "bad"); });
          }})
        ])
      ]);
      target.appendChild(howBox);

      // The bands themselves, editable.
      var bandRows = (settings.bands || []).map(bandRow);

      function bandRow(band) {
        var from = el("input.num", { type: "text",
          value: rupees(band.band_from) });
        var upto = el("input.num", { type: "text",
          value: band.band_to === null || band.band_to === undefined
            ? "" : rupees(band.band_to) });
        var rate = el("input.num", { type: "text", value: String(band.rate_bp / 100) });
        var note = el("input", { type: "text", value: band.note || "" });
        var tr = el("tr", {}, [
          el("td", {}, [from]),
          el("td", {}, [upto]),
          el("td", {}, [rate]),
          el("td", {}, [note]),
          el("td.no-print", {}, [el("button.link-button", { text: "Remove", onclick: function () {
            tr.parentNode.removeChild(tr);
          }})])
        ]);
        tr._read = function () {
          return { band_from: from.value || 0,
                   band_to: upto.value.trim() === "" ? null : upto.value,
                   rate_bp: rate.value || 0,
                   note: note.value };
        };
        return tr;
      }

      var bandTable = UI.table(
        [{ label: "From", width: "8rem" }, { label: "Up to", width: "8rem" },
         { label: "Rate %", width: "6rem" }, "What this band is", { label: "", width: "5rem" }],
        bandRows, null, {});

      target.appendChild(el("div.card", {}, [
        el("h3", { text: "Bands" }),
        el("p.card-note", { text: "Lowest band first. Each band starts where the one "
          + "below it ended, and the top band is left with its upper end blank." }),
        bandTable,
        el("div.row.no-print", {}, [
          el("button.secondary", { text: "Add a band", onclick: function () {
            UI.qs("tbody", bandTable).appendChild(bandRow(
              { band_from: 0, band_to: null, rate_bp: 0, note: "" }));
          }}),
          el("button.primary", { text: "Save the rates", onclick: function () {
            var bands = UI.qsa("tbody tr", bandTable).map(function (tr) { return tr._read(); });
            return api("/api/income-tax/rates", { body: {
              applies_to: who.value, bands: bands
            }}).then(function () {
              UI.flash("Rates saved for " + data.label + ".", "good");
              return load();
            }).catch(function (error) { UI.flash(error.message, "bad"); });
          }})
        ])
      ]));
    }

    /* What the Act does with each ledger */

    function drawTreatments(target) {
      target.appendChild(Reports.reportHead(
        "How each ledger is treated",
        "The computation applies what is set here. Nothing is decided on anybody's "
          + "behalf, and every line it acts on is shown on the statement."));

      var ledgers = null;
      var host = el("div");
      target.appendChild(host);

      api("/api/income-tax/ledgers").then(function (result) {
        ledgers = result.rows;
        drawList();
      }).catch(function (error) { UI.flash(error.message, "bad"); });

      function drawList() {
        UI.clear(host);
        var search = el("input", { type: "search", placeholder: "Find a ledger" });
        var onlyMarked = el("input", { type: "checkbox" });
        onlyMarked.checked = true;
        var listBox = el("div");

        function render() {
          UI.clear(listBox);
          var needle = (search.value || "").toLowerCase();
          var shown = ledgers.filter(function (row) {
            if (onlyMarked.checked && row.tax_treatment === "allowed") { return false; }
            if (!needle) { return true; }
            return (row.code + " " + row.name).toLowerCase().indexOf(needle) >= 0;
          });
          listBox.appendChild(UI.table(
            [{ label: "Ledger", width: "22rem" }, { label: "Treatment", width: "14rem" },
             { label: "Allowed %", num: true, width: "7rem" }, "Note"],
            shown.map(function (row) {
              var pick = el("select");
              (settings.treatments || []).forEach(function (t) {
                pick.appendChild(el("option", { value: t.key, text: t.label }));
              });
              pick.value = row.tax_treatment;
              var share = el("input.num", { type: "text",
                value: String((row.tax_allowed_bp || 10000) / 100) });
              var note = el("input", { type: "text", value: row.tax_note || "" });
              share.disabled = row.tax_treatment !== "partial";
              pick.addEventListener("change", function () {
                share.disabled = pick.value !== "partial";
                save();
              });
              share.addEventListener("change", save);
              note.addEventListener("change", save);

              function save() {
                return api("/api/income-tax/treatment", { body: {
                  account_id: row.id, treatment: pick.value,
                  allowed_bp: share.value || 100, note: note.value
                }}).then(function () {
                  row.tax_treatment = pick.value;
                  row.tax_allowed_bp = Math.round(parseFloat(share.value || 100) * 100);
                  row.tax_note = note.value;
                  UI.flash(row.code + " " + row.name + ": " + pick.options[pick.selectedIndex].text,
                           "good");
                }).catch(function (error) { UI.flash(error.message, "bad"); });
              }

              return el("tr", {}, [
                el("td", { text: row.code + "  " + row.name }),
                el("td", {}, [pick]),
                el("td", {}, [share]),
                el("td", {}, [note])
              ]);
            }), null,
            { tall: true, emptyText: onlyMarked.checked
                ? "No ledger is treated differently yet. Untick the box to see them all."
                : "No ledger matches that." }));
        }

        search.addEventListener("input", render);
        onlyMarked.addEventListener("change", render);
        host.appendChild(el("div.row.no-print", {}, [
          search,
          el("label.check", {}, [onlyMarked,
            el("span", { text: "Only the ones treated differently" })])
        ]));
        host.appendChild(listBox);
        render();
      }
    }

    page.appendChild(tabs);
    page.appendChild(box);
    return load();
  });

  return {};
}());
