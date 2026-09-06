/* What was offered, before anybody agreed to it.

   A quotation is a promise about a price. Nothing has been sold, no tax is due
   and no stock has moved, so nothing here touches the books. It becomes an
   invoice, and an entry, only when the customer says yes.

   The totals are worked out by the same call the invoice screen makes, so a
   quotation cannot promise one figure and the invoice arrive at another. */

var Quotations = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  App.register("quotations", function (page) {
    var box = el("div");

    function load() {
      return api("/api/quotations").then(draw);
    }

    function draw(data) {
      UI.clear(box);
      var open = data.rows.filter(function (q) {
        return q.status === "open" || q.status === "accepted";
      }).length;

      box.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: open
            ? UI.rs(data.open_total) + " quoted and not yet invoiced"
            : "Nothing outstanding" }),
          el("button.primary", { text: "New quotation",
                                 onclick: function () { editor(); } })
        ]),
        el("p.card-note", { text: "A quotation is a price offered. It is not in the "
          + "books, owes no tax and moves no stock until it becomes an invoice." })
      ]));

      box.appendChild(UI.table(
        ["Number", "Date", "Customer", { label: "Amount", num: true },
         "Standing", ""],
        data.rows.map(function (q) {
          return el("tr", {}, [
            el("td", { text: q.number }),
            el("td", { text: UI.bs(q.date_ad, "short") }),
            el("td", { text: q.party_name }),
            el("td.num", { text: UI.rs(q.total_paisa) }),
            el("td", {}, [
              el("span.pill" + (q.status === "invoiced" ? ".good"
                                : q.status === "declined" ? ".warn" : ""),
                 { text: q.status_label }),
              q.expired ? el("span.pill.warn", { text: "past its date" }) : null,
              q.voucher_number
                ? el("div.muted", { style: "font-size:.74rem",
                                    text: q.voucher_number }) : null
            ]),
            el("td.no-print", {}, [actions(q)])
          ]);
        }), null,
        { emptyText: "No quotations yet. The first one starts with New quotation." }));

      box.appendChild(el("div.row.no-print", { style: "margin-top:.7rem" }, [
        UI.exportButton(box, "Quotations"),
        el("button.secondary", { text: "Print", onclick: UI.printPage })
      ]));
    }

    function actions(q) {
      var row = el("div.place-actions");
      row.appendChild(el("button.place-action", { text: "Open",
        onclick: function () { show(q.id); } }));

      if (q.status !== "invoiced") {
        if (q.status !== "accepted") {
          row.appendChild(el("button.place-action", { text: "Accepted",
            onclick: function () { mark(q.id, "accepted"); } }));
        }
        if (q.status !== "declined") {
          row.appendChild(el("button.place-action", { text: "Declined",
            onclick: function () { mark(q.id, "declined"); } }));
        }
        row.appendChild(el("button.place-action", { text: "Make it an invoice",
          onclick: function () { convert(q); } }));
      }
      return row;
    }

    function mark(id, status) {
      return api("/api/quotations/status", { body: { id: id, status: status } })
        .then(load)
        .catch(function (error) { UI.flash(error.message, "bad"); });
    }

    function convert(q) {
      UI.confirmAction("Turn " + q.number + " into an invoice",
        "This is the point at which it reaches the books: the customer will owe it, "
        + "the tax becomes due and the stock leaves. It is priced again from the "
        + "lines, so if a rate has changed since it was quoted the invoice will show "
        + "the new figure.",
        function () {
          return api("/api/quotations/to-invoice", { body: { id: q.id } })
            .then(function (result) {
              UI.flash("Invoice " + result.voucher.voucher.number + " made.", "good");
              return load();
            })
            .catch(function (error) { UI.flash(error.message, "bad"); return false; });
        }, "Make the invoice");
    }

    /* One quotation, as the customer would read it */

    function show(id) {
      return api("/api/quotations/one", { query: { id: id } }).then(function (q) {
        var body = el("div.doc", {}, [
          el("div.doc-title", { text: "QUOTATION" }),
          el("div.doc-meta", { text: q.number + "   ·   " + UI.bs(q.date_ad, "long") }),
          q.valid_until_ad
            ? el("div.doc-meta", { text: "Valid until "
                                         + UI.bs(q.valid_until_ad, "long") }) : null,
          el("div", { style: "font-weight:600;margin:.6rem 0 .2rem",
                      text: q.party_name }),
          q.narration ? el("div.doc-meta", { text: q.narration }) : null,
          UI.table(
            ["Item", { label: "Quantity", num: true }, { label: "Rate", num: true },
             { label: "Discount", num: true }, { label: "Amount", num: true }],
            q.lines.map(function (line) {
              return el("tr", {}, [
                el("td", { text: line.item_name || line.description }),
                el("td.num", { text: NP.formatQty(line.qty)
                                     + (line.unit_name ? " " + line.unit_name : "") }),
                el("td.num", { text: UI.rs(line.rate_paisa) }),
                el("td.num", { text: UI.rs(line.discount_paisa, { blankZero: true }) }),
                el("td.num", { text: UI.rs(line.amount_paisa) })
              ]);
            }), null, {}),
          el("div.totals-box", {}, [
            totalLine("Taxable", q.taxable_paisa),
            q.exempt_paisa ? totalLine("Exempt", q.exempt_paisa) : null,
            q.vat_paisa ? totalLine("VAT", q.vat_paisa) : null,
            q.other_charges_paisa ? totalLine("Other charges", q.other_charges_paisa) : null,
            totalLine("Total", q.total_paisa, true)
          ]),
          q.terms ? el("div", { style: "margin-top:.8rem" }, [
            el("div.doc-subtitle", { text: "Terms" }),
            el("div.doc-meta", { text: q.terms })
          ]) : null
        ]);

        UI.modal(q.number, body, [
          { label: "Close" },
          { label: "Print", action: function () { UI.printPage(); return false; } }
        ], { wide: true });
      }).catch(function (error) { UI.flash(error.message, "bad"); });
    }

    function totalLine(label, amount, strong) {
      return el("div.total-row" + (strong ? ".grand" : ""), {}, [
        el("span", { text: label }),
        el("span", { text: UI.rs(amount) })
      ]);
    }

    /* Writing one */

    function editor() {
      var dateField = UI.dateField(NP.todayIso());
      var validField = UI.dateField("");
      var numberInput = el("input", { type: "text" });
      var partyInput = el("input", { type: "text", placeholder: "Customer name" });
      var partyId = null;
      var narration = el("input", { type: "text",
        placeholder: "What this quotation is for" });
      var terms = el("input", { type: "text",
        placeholder: "Delivery, payment terms, anything they should know" });
      var otherCharges = UI.amountInput("", { onChange: recalc });
      var billDiscount = el("input.num", { type: "text", placeholder: "0" });
      billDiscount.addEventListener("change", recalc);

      api("/api/quotations/next-number").then(function (d) { numberInput.value = d.number; });

      UI.attachPicker(partyInput, function (term) {
        return api("/api/parties", { query: { q: term, party_type: "customer" } })
          .then(function (d) { return d.rows; });
      }, function (party) {
        partyId = party.id;
        partyInput.value = party.name;
      }, function (p) { return { main: p.name, side: p.city || "" }; });

      var lines = [blank(), blank()];
      function blank() { return { itemId: null, name: "", qty: "", rate: "", discount: "" }; }

      var grid = el("tbody");
      var totals = el("div.totals-box");

      function drawLines() {
        UI.clear(grid);
        lines.forEach(function (line, index) {
          var item = el("input", { type: "text", placeholder: "Item" });
          item.value = line.name;
          UI.attachPicker(item, function (term) {
            return api("/api/items", { query: { q: term } })
              .then(function (d) { return d.rows; });
          }, function (chosen) {
            line.itemId = chosen.id;
            line.name = chosen.name;
            item.value = chosen.name;
            if (!line.rate) { line.rate = UI.rs(chosen.sale_rate_paisa, { plain: true }); }
            drawLines();
            recalc();
          }, function (i) { return { main: i.name, side: i.code }; });

          var qty = el("input.num", { type: "text", value: line.qty });
          var rate = el("input.num", { type: "text", value: line.rate });
          var discount = el("input.num", { type: "text", value: line.discount,
                                           placeholder: "0 or 5%" });
          qty.addEventListener("input", function () { line.qty = qty.value; });
          rate.addEventListener("input", function () { line.rate = rate.value; });
          discount.addEventListener("input", function () { line.discount = discount.value; });
          [qty, rate, discount].forEach(function (field) {
            field.addEventListener("change", recalc);
          });

          grid.appendChild(el("tr", {}, [
            el("td", {}, [item]), el("td", {}, [qty]), el("td", {}, [rate]),
            el("td", {}, [discount]),
            el("td.no-print", {}, [el("button.link", { text: "×", onclick: function () {
              lines.splice(index, 1);
              if (!lines.length) { lines.push(blank()); }
              drawLines(); recalc();
            }})])
          ]));
        });
      }
      drawLines();

      function collect() {
        return {
          date_ad: dateField.getIso(),
          valid_until_ad: validField.getIso() || "",
          number: numberInput.value.trim(),
          party_id: partyId,
          party_name: partyInput.value.trim(),
          narration: narration.value.trim(),
          terms: terms.value.trim(),
          other_charges: otherCharges.value || 0,
          bill_discount: billDiscount.value || 0,
          items: lines.filter(function (l) { return l.itemId; }).map(function (l) {
            var row = { item_id: l.itemId, qty: l.qty || 0, rate: l.rate || 0 };
            var text = String(l.discount || "").trim();
            if (text.slice(-1) === "%") {
              row.discount_bp = Math.round(parseFloat(text) * 100) || 0;
            } else if (text) {
              row.discount = text;
            }
            return row;
          })
        };
      }

      function recalc() {
        var payload = collect();
        if (!payload.items.length) { UI.clear(totals); return; }
        // The very call the invoice screen makes, so the two cannot drift.
        api("/api/vouchers/preview", { body: payload }).then(function (priced) {
          UI.clear(totals);
          totals.appendChild(totalLine("Subtotal", priced.subtotal));
          if (priced.discount) { totals.appendChild(totalLine("Discount", -priced.discount)); }
          totals.appendChild(totalLine("Taxable", priced.taxable));
          if (priced.vat) { totals.appendChild(totalLine("VAT", priced.vat)); }
          if (priced.other_charges) {
            totals.appendChild(totalLine("Other charges", priced.other_charges));
          }
          totals.appendChild(totalLine("Total", priced.total, true));
        }).catch(function () { UI.clear(totals); });
      }

      UI.modal("New quotation", el("div", {}, [
        el("div.row", {}, [
          UI.field("Date", dateField),
          UI.field("Number", numberInput),
          UI.field("Customer", partyInput),
          UI.field("Valid until", validField)
        ]),
        el("div.row", {}, [
          UI.field("What it is for", narration),
          UI.field("Terms", terms)
        ]),
        el("div.table-wrap", {}, [el("table", {}, [
          el("thead", {}, [el("tr", {}, [
            el("th", { text: "Item" }), el("th.num", { text: "Quantity" }),
            el("th.num", { text: "Rate" }), el("th.num", { text: "Discount" }), el("th")
          ])]),
          grid
        ])]),
        el("div.row", {}, [
          el("button.secondary", { text: "Another line", onclick: function () {
            lines.push(blank()); drawLines();
          }}),
          UI.field("Discount on the whole bill", billDiscount),
          UI.field("Other charges", otherCharges)
        ]),
        totals
      ]), [
        { label: "Cancel" },
        { label: "Save the quotation", kind: "primary", action: function () {
            return api("/api/quotations/create", { body: collect() })
              .then(function (result) {
                UI.flash("Quotation " + result.quotation.number + " saved. Nothing has "
                         + "reached the books.", "good");
                return load();
              })
              .catch(function (error) { UI.flash(error.message, "bad"); return false; });
          } }
      ], { wide: true });
    }

    page.appendChild(box);
    return load();
  });

  return {};
}());
