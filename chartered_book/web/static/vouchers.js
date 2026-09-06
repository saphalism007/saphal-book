/* Voucher entry: sales, purchase, receipt, payment, contra, journal,
   plus the day book and the printed voucher. */

var Vouchers = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  var GENERIC = {
    receipt: { title: "Receipt", hint: "Money coming in. Debit where it went, credit who paid." },
    payment: { title: "Payment", hint: "Money going out. Debit who was paid, credit where it came from." },
    contra: { title: "Contra", hint: "Movement between your own cash and bank accounts." },
    journal: { title: "Journal", hint: "Any adjustment that is not a receipt, payment or invoice." }
  };

  /* Shared pieces */

  /* Each picker can create what it cannot find, without losing the voucher
     being typed. The new record comes straight back to the line. */

  function partyPicker(input, type, onPick) {
    var label = type === "supplier" ? "Add supplier" : type === "customer" ? "Add customer" : "Add party";
    return UI.attachPicker(input, function (term) {
      return api("/api/parties", { query: { q: term, type: type } })
        .then(function (data) { return data.rows; });
    }, onPick, function (party) {
      return { main: party.name, side: (party.pan ? "PAN " + party.pan + "  " : "") + party.code };
    }, {
      createLabel: label,
      onCreate: function (typed, done) {
        Masters.openPartyForm(null, type || "customer", { presetName: typed, onSaved: done });
      }
    });
  }

  function accountPicker(input, onPick) {
    return UI.attachPicker(input, function (term) {
      return api("/api/accounts", { query: { q: term } })
        .then(function (data) { return data.rows; });
    }, onPick, function (account) {
      return { main: account.name, side: account.group_name };
    }, {
      createLabel: "Add ledger",
      onCreate: function (typed, done) {
        Masters.openAccountForm(null, { presetName: typed, onSaved: done });
      }
    });
  }

  function itemPicker(input, onPick, wanted) {
    return UI.attachPicker(input, function (term) {
      return api("/api/items", { query: { q: term, type: wanted || "", with_stock: "1" } })
        .then(function (data) { return data.rows; });
    }, onPick, function (item) {
      var rate = item.sale_rate_paisa || item.purchase_rate_paisa;
      return {
        main: item.name,
        side: item.code + (item.maintain_stock ? "   " + NP.formatQty(item.stock_qty || 0) + " in stock" : "")
              + (rate ? "   " + UI.rs(rate) : "")
      };
    }, {
      createLabel: wanted === "service" ? "Add service" : "Add item",
      onCreate: function (typed, done) {
        Masters.openItemForm(null, wanted || null, { presetName: typed, onSaved: done });
      }
    });
  }

  function loadNextNumber(voucherType, dateIso, target) {
    return api("/api/next-number", { query: { voucher_type: voucherType, date_ad: dateIso } })
      .then(function (data) { target.value = data.number; })
      .catch(function () { target.value = ""; });
  }

  /* Sales and purchase invoice */

  var INVOICE_KINDS = {
    sales: { endpoint: "sales", party: "customer", side: "sales",
             title: "What is being sold", numberLabel: "Invoice number",
             partyLabel: "Customer", refLabel: "Order or challan reference",
             saved: "Invoice" },
    purchase: { endpoint: "purchase", party: "supplier", side: "purchase",
                title: "What is being bought", numberLabel: "Our bill number",
                partyLabel: "Supplier", refLabel: "Supplier bill number",
                saved: "Bill", theirDate: true },
    sales_return: { endpoint: "sales-return", party: "customer", side: "sales",
                    title: "What is coming back", numberLabel: "Return number",
                    partyLabel: "Customer", refLabel: "Against invoice number",
                    saved: "Sales return", pullFrom: "sales",
                    note: "Goods a customer sends back. They go into stock again at what they "
                          + "cost, and the output tax on them is reversed in this month's return." },
    purchase_return: { endpoint: "purchase-return", party: "supplier", side: "purchase",
                       title: "What is going back", numberLabel: "Return number",
                       partyLabel: "Supplier", refLabel: "Against bill number",
                       saved: "Purchase return", pullFrom: "purchase", theirDate: true,
                       note: "Goods going back to a supplier. They leave stock and the input tax "
                             + "claimed on them is reversed." }
  };

  function invoiceScreen(kind) {
    var spec = INVOICE_KINDS[kind];
    return function (page) {
      var isSales = spec.side === "sales";
      var lookups = App.state.lookups || { units: [] };
      var settings = {};

      var dateField = UI.dateField(NP.todayIso(), function () { refreshNumber(); });
      var numberInput = el("input", { type: "text" });
      var partyInput = el("input", { type: "text",
        placeholder: spec.partyLabel + " name" });
      var partyId = null;
      var partyNote = el("div.hint");
      var paymentMode = UI.select([
        { value: "credit", label: "On credit" },
        { value: "cash", label: "Cash" },
        { value: "bank", label: "Bank transfer" },
        { value: "cheque", label: "Cheque" }
      ], "credit");
      var referenceInput = el("input", { type: "text", placeholder: spec.refLabel });
      var refDateField = UI.dateField(NP.todayIso());
      var narration = el("input", { type: "text", placeholder: "What this invoice is for" });

      /* Money that changes hands while the invoice is being written.

         Somebody billing a customer who pays part of it at the counter should
         not have to save the invoice, leave it, open a receipt, find the bill
         again and allocate against it. The amount goes here and the receipt is
         written with the invoice, allocated to it. Leave it empty and nothing
         happens, so an ordinary credit invoice is untouched. */
      var settleAmount = UI.amountInput("", { onChange: recalc });
      var settleMode = UI.select([
        { value: "cash", label: "Cash" },
        { value: "cheque", label: "Cheque" },
        { value: "bank", label: "Bank transfer" },
        { value: "card", label: "Card" },
        { value: "wallet", label: "Mobile wallet" }
      ], "cash");
      var settleAccountInput = el("input", { type: "text",
        placeholder: "Cash box or bank account" });
      var settleAccountId = null;
      var settleRef = el("input", { type: "text", placeholder: "Cheque or reference number" });
      var settleNote = el("div.hint");

      accountPicker(settleAccountInput, function (account) {
        settleAccountId = account.id;
        settleAccountInput.value = account.name;
      });
      api("/api/banking/accounts").then(function (data) {
        var preferred = (data.rows || []).filter(function (a) {
          return a.account_kind === (isSales ? "cash" : "bank");
        })[0] || (data.rows || [])[0];
        if (preferred && !settleAccountId) {
          settleAccountId = preferred.id;
          settleAccountInput.value = preferred.name;
        }
      });
      var priceIncludes = el("input", { type: "checkbox" });
      var otherCharges = UI.amountInput("", { onChange: recalc });
      // A discount agreed on the bill as a whole rather than line by line.
      // Either a rupee figure or a percentage written with a per cent sign.
      var billDiscount = UI.amountInput("", { onChange: recalc });
      billDiscount.placeholder = "Amount or 5%";
      var roundBox = el("input", { type: "checkbox" });
      roundBox.checked = true;

      // Both of these change every figure on the invoice, and neither of them
      // was telling anything to work the figures out again. Ticking Round to
      // the rupee did nothing at all until a quantity was retyped, which made
      // the rounding look broken when what was broken was the checkbox.
      [priceIncludes, roundBox].forEach(function (box) {
        box.addEventListener("change", recalc);
      });

      partyPicker(partyInput, spec.party, function (party) {
        partyId = party.id;
        partyInput.value = party.name;
        partyNote.textContent = (party.pan ? "PAN " + party.pan + ".  " : "")
          + (party.credit_days ? "Credit " + party.credit_days + " days." : "");
      });
      partyInput.addEventListener("input", function () {
        if (!partyInput.value.trim()) { partyId = null; partyNote.textContent = ""; }
      });

      var lines = [];
      var grid = el("tbody");
      var totalsBox = el("div.totals-box");

      function blankLine() {
        return { itemId: null, name: "", unit: "", qty: "", rate: "", discount: "", vat: 13 };
      }

      function addLine(focus) {
        var line = blankLine();
        lines.push(line);
        drawLines();
        if (focus) {
          var inputs = UI.qsa(".item-name", grid);
          if (inputs.length) { inputs[inputs.length - 1].focus(); }
        }
      }

      function drawLines() {
        UI.clear(grid);
        lines.forEach(function (line, index) {
          var nameInput = el("input", { type: "text", class: "item-name", value: line.name });
          var qtyInput = UI.amountInput(line.qty, { onChange: function (v) { line.qty = v; recalc(); } });
          var rateInput = UI.amountInput(line.rate, { onChange: function (v) { line.rate = v; recalc(); } });
          var discountInput = UI.amountInput(line.discount, { onChange: function (v) { line.discount = v; recalc(); } });
          var vatInput = UI.amountInput(line.vat, { onChange: function (v) { line.vat = v; recalc(); } });
          qtyInput.classList.add("qty");
          line.nodes = { qty: qtyInput, rate: rateInput };

          var unitCell = el("td", { text: line.unit,
            style: "width:52px;font-size:.78rem;color:var(--ink-faint)" });

          itemPicker(nameInput, function (item) {
            line.itemId = item.id;
            line.name = item.name;
            line.unit = item.unit_symbol || "";
            line.vat = item.vat_applicable ? (item.vat_rate_bp / 100) : 0;
            nameInput.value = item.name;
            nameInput.classList.remove("unlinked");
            unitCell.textContent = line.unit;
            vatInput.value = line.vat;
            if (!line.rate) {
              line.rate = ((isSales ? item.sale_rate_paisa : item.purchase_rate_paisa) || 0) / 100;
              rateInput.value = line.rate || "";
            }
            drawTotals();
            qtyInput.focus();
          });
          nameInput.addEventListener("input", function () {
            line.name = nameInput.value;
            if (!nameInput.value.trim()) {
              line.itemId = null;
              line.unit = "";
              unitCell.textContent = "";
            }
            nameInput.classList.toggle("unlinked",
              !!nameInput.value.trim() && !line.itemId);
          });
          [qtyInput, rateInput].forEach(function (input) {
            input.addEventListener("keydown", function (event) {
              if (event.key === "Enter") {
                event.preventDefault();
                if (input === rateInput && index === lines.length - 1) { addLine(true); }
                else if (input === qtyInput) { rateInput.focus(); }
              }
            });
          });

          var amount = el("td.num", { text: "" });
          line.amountCell = amount;

          grid.appendChild(el("tr", {}, [
            el("td", { text: String(index + 1), style: "color:var(--ink-faint);width:24px" }),
            el("td", {}, [nameInput]),
            unitCell,
            el("td", { style: "width:88px" }, [qtyInput]),
            el("td", { style: "width:104px" }, [rateInput]),
            el("td", { style: "width:78px" }, [discountInput]),
            el("td", { style: "width:66px" }, [vatInput]),
            amount,
            el("td", { style: "width:26px" }, [
              el("button.line-remove", { text: "×", title: "Remove this line", onclick: function () {
                lines.splice(index, 1);
                if (!lines.length) { addLine(); } else { drawLines(); }
                recalc();
              }})
            ])
          ]));
        });
        recalc();
      }

      var computed = blankTotals();

      function blankTotals() {
        return { subtotal: 0, lineDiscount: 0, billDiscount: 0, discount: 0,
                 taxable: 0, exempt: 0, vat: 0, total: 0, roundOff: 0 };
      }

      // This has to work out the same figures the server does, in the same
      // order, or the screen would show one total and the books would hold
      // another. Lines are priced first, then the discount on the whole bill is
      // shared back over them, and only then is tax worked out. Tax is charged
      // on what the customer actually pays, so it cannot be settled until every
      // line knows its share of that discount.
      function recalc() {
        computed = blankTotals();
        var priced = [];
        lines.forEach(function (line) {
          if (!line.itemId) { if (line.amountCell) { line.amountCell.textContent = ""; } return; }
          var qty = NP.toQty(line.qty || 0);
          var rate = NP.toPaisa(line.rate || 0);
          var vatBp = Math.round((parseFloat(line.vat) || 0) * 100);
          var gross = NP.roundHalfUp(qty * rate, 1000);
          if (priceIncludes.checked && vatBp) {
            gross = NP.roundHalfUp(gross * 10000, 10000 + vatBp);
          }
          var discountText = String(line.discount || "").trim();
          var discount = 0;
          if (discountText.slice(-1) === "%") {
            discount = NP.applyRate(gross, Math.round(parseFloat(discountText) * 100) || 0);
          } else if (discountText) {
            discount = NP.toPaisa(discountText);
          }
          if (discount > gross) { discount = gross; }
          priced.push({ line: line, gross: gross, discount: discount,
                        taxable: gross - discount, vatBp: vatBp });
        });

        var base = 0;
        priced.forEach(function (row) { base += row.taxable; });
        var billText = String(billDiscount.value || "").trim();
        var offTheBill = 0;
        if (billText.slice(-1) === "%") {
          offTheBill = NP.applyRate(base, Math.round(parseFloat(billText) * 100) || 0);
        } else if (billText) {
          offTheBill = NP.toPaisa(billText);
        }
        if (offTheBill < 0) { offTheBill = 0; }
        if (offTheBill > base) { offTheBill = base; }
        if (offTheBill && priced.length) {
          var shares = NP.allocate(offTheBill, priced.map(function (row) { return row.taxable; }));
          priced.forEach(function (row, index) { row.taxable -= shares[index]; });
        }

        computed.billDiscount = offTheBill;
        priced.forEach(function (row) {
          var vat = NP.applyRate(row.taxable, row.vatBp);
          computed.subtotal += row.gross;
          computed.lineDiscount += row.discount;
          if (row.vatBp) { computed.taxable += row.taxable; } else { computed.exempt += row.taxable; }
          computed.vat += vat;
          if (row.line.amountCell) { row.line.amountCell.textContent = UI.rs(row.taxable + vat); }
        });
        computed.discount = computed.lineDiscount + computed.billDiscount;
        var charges = NP.toPaisa(otherCharges.value || 0);
        var gross = computed.taxable + computed.exempt + computed.vat + charges;
        var rounded = gross;
        if (roundBox.checked) {
          var remainder = ((gross % 100) + 100) % 100;
          if (remainder) { rounded = gross - remainder + (remainder >= 50 ? 100 : 0); }
        }
        computed.roundOff = rounded - gross;
        computed.charges = charges;
        computed.total = rounded;
        drawTotals();
      }

      function drawTotals() {
        UI.clear(totalsBox);
        function row(label, value, cls) {
          totalsBox.appendChild(el("div" + (cls ? "." + cls : ""), {}, [
            el("span", { text: label }), el("span.num", { text: UI.rs(value) })
          ]));
        }
        row("Subtotal", computed.subtotal);
        if (computed.lineDiscount) { row("Less discount on the lines", -computed.lineDiscount); }
        if (computed.billDiscount) { row("Less discount on the bill", -computed.billDiscount); }
        if (computed.exempt) { row("Exempt", computed.exempt); }
        row("Taxable", computed.taxable);
        if (computed.vat) { row("VAT 13 percent", computed.vat); }
        if (computed.charges) { row("Other charges", computed.charges); }
        if (computed.roundOff) {
          // Without this the line reads 22,601.11 and the total reads
          // 22,601.00, and the invoice looks as though it does not add up.
          row("Before rounding", computed.total - computed.roundOff);
          row(computed.roundOff > 0 ? "Rounded up to the rupee"
                                    : "Rounded down to the rupee", computed.roundOff);
        }
        row("Total", computed.total, "grand");
        totalsBox.appendChild(el("div.in-words", { text: inWords(computed.total) }));
      }

      function inWords(paisa) {
        return paisa ? "" : "";
      }

      function refreshNumber() { loadNextNumber(kind, dateField.getIso(), numberInput); }

      function collect(status) {
        var payload = {
          date_ad: dateField.getIso(),
          number: numberInput.value.trim(),
          party_id: partyId,
          payment_mode: paymentMode.value === "credit" ? "" : paymentMode.value,
          reference_no: referenceInput.value.trim(),
          narration: narration.value.trim(),
          other_charges: otherCharges.value || 0,
          round_invoice: roundBox.checked,
          price_includes_vat: priceIncludes.checked,
          status: status || "posted",
          settle: {
            amount: settleAmount.value || 0,
            mode: settleMode.value,
            bank_account_id: settleAccountId,
            reference: settleRef.value.trim()
          },
          items: lines.filter(function (line) { return line.itemId; }).map(function (line) {
            var discountText = String(line.discount || "").trim();
            var row = {
              item_id: line.itemId,
              qty: line.qty || 0,
              rate: line.rate || 0,
              vat_bp: Math.round((parseFloat(line.vat) || 0) * 100)
            };
            if (discountText.slice(-1) === "%") {
              row.discount_bp = Math.round(parseFloat(discountText) * 100) || 0;
            } else if (discountText) {
              row.discount = discountText;
            }
            return row;
          })
        };
        var billText = String(billDiscount.value || "").trim();
        if (billText.slice(-1) === "%") {
          payload.bill_discount_bp = Math.round(parseFloat(billText) * 100) || 0;
        } else if (billText) {
          payload.bill_discount = billText;
        }
        if (spec.theirDate) { payload.reference_date_ad = refDateField.getIso(); }
        return payload;
      }

      function save(andPrint) {
        var stray = lines.filter(function (line) {
          return !line.itemId && String(line.name || "").trim();
        });
        if (stray.length) {
          UI.flash("\"" + stray[0].name.trim() + "\" is not on the item list. Pick it from the "
            + "list, or add it as a new item first.", "bad");
          return;
        }
        var payload = collect("posted");
        if (!payload.items.length) { UI.flash("Add at least one line.", "bad"); return; }
        if (!partyId && paymentMode.value === "credit") {
          UI.flash("Choose a " + spec.partyLabel.toLowerCase()
                   + ", or change the payment to cash.", "bad");
          return;
        }
        api("/api/vouchers/" + spec.endpoint, { body: payload })
          .then(function (data) {
            UI.flash(spec.saved + " " + data.voucher.voucher.number + " saved.", "good");
            if (andPrint) { view(data.id, true); }
            App.go(kind);
          })
          .catch(function (error) { UI.flash(error.message, "bad"); });
      }

      addLine();
      refreshNumber();

      var pullButton = spec.pullFrom
        ? el("button.secondary", { text: "Pull the lines from an invoice",
                                   onclick: function () { openPull(); } })
        : null;

      function openPull() {
        api("/api/vouchers/returnable", { query: { kind: spec.pullFrom, party_id: partyId } })
          .then(function (data) {
            if (!data.rows.length) {
              UI.flash("Nothing found to return against. Choose the party first.", "warn");
              return;
            }
            var listRows = data.rows.map(function (row) {
              return el("tr.clickable", { onclick: function () { pull(row.id); } }, [
                el("td", { text: row.number }),
                el("td", { text: UI.bs(row.date_ad, "short") }),
                el("td", { text: row.party_name || "Cash" }),
                el("td.num", { text: UI.rs(row.total_paisa) })
              ]);
            });
            UI.modal("Which one is it against", el("div", {}, [
              el("p.card-note", { text: "The lines are copied in and can then be cut down to "
                + "whatever is actually coming back." }),
              UI.table(["Number", "Date", "Party", { label: "Amount", num: true }],
                       listRows, null, { tall: true })
            ]), [{ label: "Cancel" }], { wide: true });
          })
          .catch(function (error) { UI.flash(error.message, "bad"); });
      }

      function pull(voucherId) {
        api("/api/vouchers/" + voucherId).then(function (data) {
          UI.closeModal();
          var voucher = data.voucher;
          referenceInput.value = voucher.number;
          if (voucher.party_id) {
            partyId = voucher.party_id;
            partyInput.value = voucher.party_name || "";
          }
          lines.length = 0;
          data.items.forEach(function (row) {
            // Goods sold at a discount have to come back at the same discount,
            // or the credit given would be larger than the sale ever was. It is
            // carried over as a percentage rather than an amount so it still
            // holds when only part of the delivery is coming back. A discount
            // that was given on the whole bill is part of this too, since by
            // now it has been shared out over the lines it was given on.
            var off = (row.discount_paisa || 0) + (row.bill_discount_paisa || 0);
            var percent = row.gross_paisa
              ? Math.round(off * 10000 / row.gross_paisa) / 100 : 0;
            lines.push({
              itemId: row.item_id, name: row.item_name, unit: row.unit_symbol || "",
              qty: NP.formatQty(row.qty), rate: String(row.rate_paisa / 100),
              discount: percent ? percent + "%" : "", vat: row.vat_bp / 100
            });
          });
          if (!lines.length) { addLine(); }
          drawLines();
          UI.flash("Lines copied from " + voucher.number + ". Change the quantities to what "
                   + "is actually coming back.", "good");
        }).catch(function (error) { UI.flash(error.message, "bad"); });
      }

      var header = el("div.card", {}, [
        spec.note ? el("p.card-note", { style: "margin-bottom:.7rem", text: spec.note }) : null,
        el("div.row", {}, [
          UI.field("Date", dateField),
          UI.field(spec.numberLabel, numberInput),
          UI.field(spec.partyLabel, el("div", {}, [partyInput, partyNote])),
          UI.field("Payment", paymentMode)
        ]),
        el("div.row", {}, [
          UI.field(spec.refLabel, referenceInput),
          spec.theirDate ? UI.field("Their document date", refDateField) : null,
          UI.field("Narration", narration)
        ]),
        pullButton ? el("div.row", { style: "margin-top:.5rem" }, [pullButton]) : null
      ]);

      var settleCard = el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: isSales ? "Money received now" : "Money paid now" })
        ]),
        el("p.card-note", { text: isSales
          ? "Leave this empty for an ordinary credit sale. Put an amount here and the "
            + "receipt is written with the invoice and set against it, so there is no "
            + "second entry to make."
          : "Leave this empty for an ordinary credit purchase. Put an amount here and the "
            + "payment is written with the bill and set against it." }),
        el("div.row", {}, [
          UI.field(isSales ? "Received" : "Paid", settleAmount),
          UI.field("How", settleMode),
          UI.field("Into", el("div", {}, [settleAccountInput, settleNote])),
          UI.field("Reference", settleRef)
        ])
      ]);

      var gridCard = el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: spec.title }),
          el("div.row", {}, [
            el("label", { style: "font-size:.78rem;display:flex;gap:.3rem;align-items:center" }, [
              priceIncludes, el("span", { text: "Rates already include VAT" })
            ]),
            el("label", { style: "font-size:.78rem;display:flex;gap:.3rem;align-items:center" }, [
              roundBox, el("span", { text: "Round to the rupee" })
            ])
          ])
        ]),
        el("div.table-wrap", {}, [
          el("table.entry-grid", {}, [
            el("thead", {}, [el("tr", {}, [
              el("th", { text: "" }),
              el("th", { text: "Item" }),
              el("th", { text: "Unit" }),
              el("th.num", { text: "Quantity" }),
              el("th.num", { text: "Rate" }),
              el("th.num", { text: "Discount" }),
              el("th.num", { text: "VAT %" }),
              el("th.num", { text: "Amount" }),
              el("th", { text: "" })
            ])]),
            grid
          ])
        ]),
        el("div.row", { style: "margin-top:.5rem" }, [
          el("button.secondary", { text: "Add a line", onclick: function () { addLine(true); } }),
          el("div.spacer"),
          el("div", { style: "flex:0 0 200px" }, [
            UI.field("Discount on the whole bill", billDiscount)]),
          el("div", { style: "flex:0 0 200px" }, [UI.field("Other charges", otherCharges)])
        ]),
        el("div", { style: "display:flex;margin-top:.6rem" }, [totalsBox])
      ]);

      var actions = el("div.card", {}, [
        el("div.row", {}, [
          el("button.primary", { text: "Save", onclick: function () { save(false); } }),
          el("button.secondary", { text: "Save and print", onclick: function () { save(true); } }),
          el("button.ghost", { text: "Clear the form", onclick: function () { App.go(kind); } }),
          el("div.spacer"),
          el("span.card-note", { text: "Press Enter in the rate box to start a new line." })
        ])
      ]);

      page.appendChild(header);
      page.appendChild(gridCard);
      page.appendChild(settleCard);
      page.appendChild(actions);
      setTimeout(function () { partyInput.focus(); }, 60);
    };
  }

  App.register("sales", invoiceScreen("sales"));
  App.register("purchase", invoiceScreen("purchase"));
  App.register("sales_return", invoiceScreen("sales_return"));
  App.register("purchase_return", invoiceScreen("purchase_return"));

  /* Receipt, payment, contra and journal */

  function genericScreen(kind) {
    return function (page) {
      var spec = GENERIC[kind];
      var dateField = UI.dateField(NP.todayIso(), function () { refreshNumber(); });
      var numberInput = el("input", { type: "text" });
      var partyInput = el("input", { type: "text", placeholder: "Optional" });
      var partyId = null;
      var narration = el("input", { type: "text", placeholder: "What this is for" });
      var referenceInput = el("input", { type: "text", placeholder: "Cheque number or reference" });
      var grid = el("tbody");
      var summary = el("div.totals-box");
      var lines = [];

      partyPicker(partyInput, null, function (party) {
        partyId = party.id;
        partyInput.value = party.name;
        if (lines.length && !lines[0].accountId) {
          lines[0].accountId = party.account_id;
          lines[0].name = party.name;
          drawLines();
        }
      });
      partyInput.addEventListener("input", function () {
        if (!partyInput.value.trim()) { partyId = null; }
      });

      function addLine(focus) {
        lines.push({ accountId: null, name: "", dr: "", cr: "", narration: "" });
        drawLines();
        if (focus) {
          var inputs = UI.qsa(".account-name", grid);
          if (inputs.length) { inputs[inputs.length - 1].focus(); }
        }
      }

      function drawLines() {
        UI.clear(grid);
        lines.forEach(function (line, index) {
          var nameInput = el("input", { type: "text", class: "account-name", value: line.name });
          var drInput = UI.amountInput(line.dr, { onChange: function (v) {
            line.dr = v; if (v) { line.cr = ""; crInput.value = ""; } recalc();
          }});
          var crInput = UI.amountInput(line.cr, { onChange: function (v) {
            line.cr = v; if (v) { line.dr = ""; drInput.value = ""; } recalc();
          }});
          var noteInput = el("input", { type: "text", value: line.narration });
          noteInput.addEventListener("input", function () { line.narration = noteInput.value; });

          accountPicker(nameInput, function (account) {
            line.accountId = account.id;
            line.name = account.name;
            nameInput.value = account.name;
            nameInput.classList.remove("unlinked");
            drInput.focus();
          });
          nameInput.addEventListener("input", function () {
            line.name = nameInput.value;
            if (!nameInput.value.trim()) { line.accountId = null; }
            nameInput.classList.toggle("unlinked",
              !!nameInput.value.trim() && !line.accountId);
          });
          crInput.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && index === lines.length - 1) {
              event.preventDefault(); addLine(true);
            }
          });

          grid.appendChild(el("tr", {}, [
            el("td", { text: String(index + 1), style: "color:var(--ink-faint);width:24px" }),
            el("td", {}, [nameInput]),
            el("td", { style: "width:120px" }, [drInput]),
            el("td", { style: "width:120px" }, [crInput]),
            el("td", {}, [noteInput]),
            el("td", { style: "width:26px" }, [
              el("button.line-remove", { text: "×", onclick: function () {
                lines.splice(index, 1);
                if (lines.length < 2) { addLine(); } else { drawLines(); }
                recalc();
              }})
            ])
          ]));
        });
        recalc();
      }

      function totals() {
        var dr = 0, cr = 0;
        lines.forEach(function (line) {
          if (!line.accountId) { return; }
          dr += NP.toPaisa(line.dr || 0);
          cr += NP.toPaisa(line.cr || 0);
        });
        return { dr: dr, cr: cr, difference: dr - cr };
      }

      function recalc() {
        var sums = totals();
        UI.clear(summary);
        summary.appendChild(el("div", {}, [el("span", { text: "Total debit" }),
          el("span.num", { text: UI.rs(sums.dr) })]));
        summary.appendChild(el("div", {}, [el("span", { text: "Total credit" }),
          el("span.num", { text: UI.rs(sums.cr) })]));
        summary.appendChild(el("div.grand", {}, [
          el("span", { text: sums.difference === 0 ? "In balance" : "Out by" }),
          el("span.num" + (sums.difference === 0 ? "" : ".negative"),
            { text: sums.difference === 0 ? "0.00" : UI.rs(Math.abs(sums.difference)) })
        ]));
      }

      function refreshNumber() { loadNextNumber(kind, dateField.getIso(), numberInput); }

      function save(keepGoing) {
        var stray = lines.filter(function (line) {
          return !line.accountId && String(line.name || "").trim();
        });
        if (stray.length) {
          UI.flash("\"" + stray[0].name.trim() + "\" is not a ledger in the chart of accounts. "
            + "Pick it from the list, or create the ledger first.", "bad");
          return;
        }
        var sums = totals();
        var used = lines.filter(function (line) {
          return line.accountId && (NP.toPaisa(line.dr || 0) || NP.toPaisa(line.cr || 0));
        });
        if (used.length < 2) { UI.flash("A voucher needs at least one debit and one credit.", "bad"); return; }
        if (sums.difference !== 0) {
          UI.flash("Debit and credit do not agree. Out by " + UI.rs(Math.abs(sums.difference)) + ".", "bad");
          return;
        }
        api("/api/vouchers/create", { body: {
          voucher_type: kind,
          date_ad: dateField.getIso(),
          number: numberInput.value.trim(),
          party_id: partyId,
          reference_no: referenceInput.value.trim(),
          narration: narration.value.trim(),
          entries: used.map(function (line) {
            return { account_id: line.accountId, dr: line.dr || 0, cr: line.cr || 0,
                     narration: line.narration || "" };
          })
        }}).then(function (data) {
          UI.flash(spec.title + " " + data.voucher.voucher.number + " saved.", "good");
          if (keepGoing) { App.go(kind); } else { view(data.id); }
        }).catch(function (error) { UI.flash(error.message, "bad"); });
      }

      addLine();
      addLine();
      refreshNumber();

      page.appendChild(el("div.card", {}, [
        el("p.card-note", { text: spec.hint }),
        el("div.row", {}, [
          UI.field("Date", dateField),
          UI.field("Number", numberInput),
          UI.field("Party", partyInput),
          UI.field("Reference", referenceInput)
        ]),
        UI.field("Narration", narration)
      ]));

      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Entries" })]),
        el("div.table-wrap", {}, [
          el("table.entry-grid", {}, [
            el("thead", {}, [el("tr", {}, [
              el("th", { text: "" }), el("th", { text: "Ledger" }),
              el("th.num", { text: "Debit" }), el("th.num", { text: "Credit" }),
              el("th", { text: "Note" }), el("th", { text: "" })
            ])]),
            grid
          ])
        ]),
        el("div.row", { style: "margin-top:.5rem" }, [
          el("button.secondary", { text: "Add a line", onclick: function () { addLine(true); } }),
          el("div.spacer")
        ]),
        el("div", { style: "display:flex;margin-top:.6rem" }, [summary])
      ]));

      page.appendChild(el("div.card", {}, [
        el("div.row", {}, [
          el("button.primary", { text: "Save", onclick: function () { save(false); } }),
          el("button.secondary", { text: "Save and enter another", onclick: function () { save(true); } }),
          el("button.ghost", { text: "Clear the form", onclick: function () { App.go(kind); } })
        ])
      ]));
    };
  }

  // Contra and journal stay on the free grid. Receipts and payments get a
  // screen of their own, because what they are really doing is settling bills.
  App.register("contra", genericScreen("contra"));
  App.register("journal", genericScreen("journal"));
  App.register("receipt_free", genericScreen("receipt"));
  App.register("payment_free", genericScreen("payment"));

  /* Day book */

  App.register("daybook", function (page) {
    var fy = App.state.fiscalYear || {};
    var fromField = UI.dateField(fy.start_ad || NP.todayIso());
    var toField = UI.dateField(fy.end_ad || NP.todayIso());
    var typeFilter = UI.select([{ value: "", label: "Every kind" }].concat(
      (App.state.lookups && App.state.lookups.voucher_types || []).map(function (t) {
        return { value: t.code, label: t.name };
      })), "");
    var showCancelled = el("input", { type: "checkbox" });
    var listBox = el("div");

    function load() {
      return api("/api/daybook", { query: {
        from_ad: fromField.getIso(), to_ad: toField.getIso(),
        voucher_type: typeFilter.value, include_cancelled: showCancelled.checked ? "1" : ""
      }}).then(function (data) {
        var total = 0;
        var rows = data.rows.map(function (row) {
          if (row.status !== "cancelled") { total += row.total_paisa; }
          return el("tr.clickable" + (row.status === "cancelled" ? ".cancelled" : ""), {
            onclick: function () { view(row.id); }
          }, [
            el("td", { text: UI.bs(row.date_ad, "short") }),
            el("td", { text: row.date_ad, style: "font-size:.76rem;color:var(--ink-faint)" }),
            el("td", { text: row.type_name }),
            el("td", { text: row.number }),
            el("td", { text: row.party_name || "" }),
            el("td", { text: row.narration || "", style: "max-width:280px" }),
            el("td.num", { text: UI.rs(row.total_paisa) }),
            el("td", {}, [row.status === "posted" ? null
              : el("span.pill" + (row.status === "draft" ? ".warn" : ".bad"), { text: row.status })])
          ]);
        });
        UI.clear(listBox).appendChild(UI.table(
          ["Date (BS)", "Date (AD)", "Type", "Number", "Party", "Narration",
           { label: "Amount", num: true }, ""],
          rows,
          rows.length ? [el("tr", {}, [
            el("td", { colspan: "6", text: "Total of " + rows.length + " vouchers" }),
            el("td.num", { text: UI.rs(total) }), el("td")
          ])] : null,
          { tall: true, emptyText: "No vouchers in this period." }));
      });
    }

    [typeFilter, showCancelled].forEach(function (node) { node.addEventListener("change", load); });
    fromField.input.addEventListener("change", function () { setTimeout(load, 10); });
    toField.input.addEventListener("change", function () { setTimeout(load, 10); });

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [
        el("h2", { text: "Day book" }),
        el("button.secondary.no-print", { text: "Print", onclick: UI.printPage }),
      UI.exportButton()
      ]),
      el("div.toolbar", {}, [
        UI.field("From", fromField), UI.field("To", toField),
        UI.field("Kind", typeFilter),
        el("label", { style: "font-size:.78rem;display:flex;gap:.3rem;align-items:center;padding-bottom:.4rem" }, [
          showCancelled, el("span", { text: "Show cancelled" })
        ]),
        el("div.spacer")
      ]),
      listBox
    ]));
    return load();
  });

  /* Viewing and printing one voucher */

  /* The paper behind the entry.

     A voucher on its own is an assertion; the bill behind it is the evidence,
     and on an audit the two living in different places is most of the work.
     Kept with the books, so a backup, a copy sent to the account and a tablet
     all carry them. That costs size, which is why the limit is said here
     rather than discovered when a file is refused. */

  function papersFor(voucherId) {
    var box = el("div.papers");
    var list = el("div");
    var chooser = el("input", { type: "file" });
    chooser.accept = "image/*,application/pdf,.csv,.txt,.xlsx,.docx,.xls,.doc";
    chooser.style.display = "none";

    function draw(data) {
      UI.clear(list);
      (data.rows || []).forEach(function (paper) {
        var row = el("div.paper", {}, [
          el("div.paper-what", {}, [
            el("span.paper-name", { text: paper.filename }),
            el("span.muted", { text: paper.size_text })
          ]),
          paper.note ? el("div.card-note", { style: "margin:.1rem 0", text: paper.note }) : null,
          el("div.place-actions", {}, [
            el("button.place-action", { text: paper.shows_in_place ? "Look at it" : "Save it",
              onclick: function () { openPaper(paper); } }),
            App.state.permissions["voucher.cancel"]
              ? el("button.place-action", { text: "Take it away", onclick: function () {
                  UI.confirmAction("Take away " + paper.filename,
                    "The entry stays. Only the paper behind it goes, and who took it "
                    + "away is recorded.",
                    function () {
                      return api("/api/papers/remove",
                                 { body: { id: paper.id, voucher_id: voucherId } })
                        .then(draw)
                        .catch(function (error) { UI.flash(error.message, "bad"); });
                    }, "Take it away");
                }})
              : null
          ])
        ]);
        list.appendChild(row);
      });
      if (!(data.rows || []).length) {
        list.appendChild(el("p.card-note", { text: "Nothing kept against this entry yet." }));
      }
      var totals = data.totals || {};
      if (totals.heavy) {
        list.appendChild(el("p.card-note", {
          style: "border-left:3px solid var(--warn);padding-left:.6rem",
          text: "The papers in these books now come to " + totals.size_text
                + ". They are backed up and sent to your account along with everything "
                + "else, so that is what each copy carries." }));
      }
    }

    function openPaper(paper) {
      return api("/api/papers/open", { query: { id: paper.id } })
        .then(function (got) {
          if (paper.shows_in_place) { return showPaper(got); }
          UI.downloadFile(got.filename, got.content, got.mime || "application/octet-stream");
        })
        .catch(function (error) { UI.flash(error.message, "bad"); });
    }

    function showPaper(got) {
      var source = "data:" + (got.mime || "application/octet-stream")
                   + ";base64," + got.content;
      var shown = got.mime === "application/pdf"
        ? el("iframe", { style: "width:100%;height:70vh;border:0" })
        : el("img", { style: "max-width:100%;max-height:70vh;display:block;margin:0 auto" });
      shown.src = source;
      UI.modal(got.filename, el("div", {}, [shown]), [
        { label: "Close" },
        { label: "Save it", action: function () {
            UI.downloadFile(got.filename, got.content,
                            got.mime || "application/octet-stream");
            return false;
          } }
      ], { wide: true });
    }

    chooser.addEventListener("change", function () {
      var file = chooser.files && chooser.files[0];
      if (!file) { return; }
      var reader = new FileReader();
      reader.onload = function () {
        // A data URL is "data:<mime>;base64,<the bytes>". Only the bytes go.
        var text = String(reader.result || "");
        var comma = text.indexOf(",");
        api("/api/papers", { body: {
          voucher_id: voucherId, filename: file.name,
          mime: file.type || "", content: comma >= 0 ? text.slice(comma + 1) : ""
        }}).then(function (data) {
          UI.flash("Kept " + file.name + " with this entry.", "good");
          draw(data);
        }).catch(function (error) { UI.flash(error.message, "bad"); });
        chooser.value = "";
      };
      reader.readAsDataURL(file);
    });

    box.appendChild(el("div.doc-subtitle", { text: "The paper behind this entry" }));
    box.appendChild(list);
    box.appendChild(el("div.row.no-print", { style: "margin-top:.4rem" }, [
      el("button.secondary", { text: "Keep a bill or photograph",
                               onclick: function () { chooser.click(); } }),
      chooser
    ]));

    api("/api/papers", { query: { voucher_id: voucherId } })
      .then(draw)
      .catch(function () { UI.clear(list); });
    return box;
  }

  function view(voucherId, printNow) {
    api("/api/vouchers/" + voucherId).then(function (data) {
      var body = renderVoucher(data);
      body.appendChild(papersFor(voucherId));
      var buttons = [
        { label: "Close" },
        { label: "Print", action: function () { UI.printPage(); return false; } }
      ];
      if (data.voucher.status === "posted" && App.state.permissions["voucher.cancel"]) {
        buttons.push({ label: "Cancel this voucher", kind: "danger", action: function () {
          UI.closeModal();
          UI.promptText("Cancel " + data.voucher.number,
            "Why is it being cancelled? This becomes part of the record.",
            function (reason) {
              if (!reason) { UI.flash("A reason is needed.", "bad"); return false; }
              return api("/api/vouchers/" + voucherId + "/cancel", { body: { reason: reason } })
                .then(function () { UI.flash("Cancelled.", "warn"); App.go(App.state.route); });
            }, { submitLabel: "Cancel the voucher" });
          return false;
        }});
      }
      UI.modal(data.voucher.number, body, buttons, { wide: true });
      if (printNow) { setTimeout(UI.printPage, 400); }
    }).catch(function (error) { UI.flash(error.message, "bad"); });
  }

  /* The double entry behind a voucher, laid out the way a journal is read.

     This goes on every printed voucher, whatever kind it is, so a purchase
     bill, a receipt and a contra all come off the printer in the same shape. */

  function entryTable(data, heading) {
    var rows = data.entries.map(function (entry) {
      return el("tr", {}, [
        el("td", { text: entry.account_code }),
        el("td", {}, [
          el("div", { text: entry.account_name }),
          entry.narration
            ? el("div", { text: entry.narration,
                          style: "font-size:.76rem;color:var(--ink-faint)" })
            : null
        ]),
        el("td.num", { text: entry.dr_paisa ? UI.rs(entry.dr_paisa) : "" }),
        el("td.num", { text: entry.cr_paisa ? UI.rs(entry.cr_paisa) : "" })
      ]);
    });
    var totalDr = data.entries.reduce(function (sum, e) { return sum + e.dr_paisa; }, 0);
    var totalCr = data.entries.reduce(function (sum, e) { return sum + e.cr_paisa; }, 0);
    return el("div.doc-entries", {}, [
      heading ? el("div.doc-subtitle", { text: heading }) : null,
      el("div.table-wrap", {}, [el("table.doc-table", {}, [
        el("thead", {}, [el("tr", {}, [
          el("th", { text: "Code" }), el("th", { text: "Ledger" }),
          el("th.num", { text: "Debit" }), el("th.num", { text: "Credit" })
        ])]),
        el("tbody", {}, rows),
        el("tfoot", {}, [el("tr.total-row", {}, [
          el("td", { colspan: "2", text: "Total" }),
          el("td.num", { text: UI.rs(totalDr) }),
          el("td.num", { text: UI.rs(totalCr) })
        ])])
      ])])
    ]);
  }

  function renderVoucher(data) {
    var voucher = data.voucher;
    var company = App.state.company || {};
    var settings = App.state.settings || {};
    var settingsFooter = settings.invoice_footer || "";
    var showWords = settings.show_amount_in_words !== "0";
    var isInvoice = data.items.length > 0;
    /* The Value Added Tax Rules, 2053 set out what a tax invoice must carry:
       the words tax invoice, both parties with their registration numbers, a
       serial number and date, the goods, the value, the tax shown separately,
       and which copy the sheet is. */
    var titles = {
      sales: company.vat_registered ? "Tax Invoice" : "Sales Invoice",
      purchase: "Purchase Bill", sales_return: "Sales Return",
      purchase_return: "Purchase Return", receipt: "Receipt Voucher",
      payment: "Payment Voucher", contra: "Contra Voucher", journal: "Journal Voucher",
      debit_note: "Debit Note", credit_note: "Credit Note",
      stock_adjust: "Stock Adjustment", opening: "Opening Balance"
    };
    var titlesNp = {
      sales: company.vat_registered ? "कर बीजक" : "बिक्री बीजक",
      purchase: "खरिद बीजक", sales_return: "बिक्री फिर्ता",
      purchase_return: "खरिद फिर्ता", receipt: "रसिद", payment: "भुक्तानी",
      contra: "कन्ट्रा", journal: "जर्नल", debit_note: "डेबिट नोट",
      credit_note: "क्रेडिट नोट", stock_adjust: "मौज्दात मिलान", opening: "प्रारम्भिक"
    };
    var isTaxInvoice = voucher.voucher_type === "sales"
      && company.vat_registered && voucher.is_vat_invoice;

    var head = el("div.doc-head", {}, [
      el("div", {}, [
        el("div.doc-company", { text: company.name || "" }),
        company.name_np ? el("div", { text: company.name_np }) : null,
        el("div.doc-meta", { text: [company.address, company.city, company.district]
          .filter(Boolean).join(", ") }),
        el("div.doc-meta", { text: [company.phone && "Phone " + company.phone,
          company.email].filter(Boolean).join("  ") }),
        company.pan ? el("div.doc-meta", { text: (company.vat_registered ? "VAT " : "PAN ") + company.pan }) : null
      ]),
      el("div", { style: "text-align:right" }, [
        el("div.doc-meta", { text: "Number" }),
        el("div", { text: voucher.number, style: "font-weight:600" }),
        el("div.doc-meta", { style: "margin-top:.3rem", text: "Date" }),
        el("div", { text: UI.bs(voucher.date_ad, "long") }),
        el("div.doc-meta", { text: voucher.date_ad }),
        voucher.status !== "posted"
          ? el("div", { style: "margin-top:.3rem" }, [el("span.pill.bad", { text: voucher.status })])
          : null
      ])
    ]);

    var isPurchaseSide = voucher.voucher_type === "purchase"
      || voucher.voucher_type === "purchase_return";
    var partyAddress = [voucher.party_address, voucher.party_city, voucher.party_district]
      .filter(Boolean).join(", ");
    var parties = el("div.doc-parties", {}, [
      el("div", {}, [
        el("div.doc-meta", { text: isPurchaseSide ? "Supplier" : "Customer" }),
        el("div", { text: voucher.party_name || "Cash", style: "font-weight:600" }),
        voucher.party_name_np ? el("div", { text: voucher.party_name_np }) : null,
        partyAddress ? el("div.doc-meta", { text: partyAddress }) : null,
        voucher.party_pan ? el("div.doc-meta", { text: "PAN " + voucher.party_pan }) : null,
        (voucher.party_mobile || voucher.party_phone)
          ? el("div.doc-meta", { text: voucher.party_mobile || voucher.party_phone }) : null,
        voucher.reference_no ? el("div.doc-meta", { text: "Reference " + voucher.reference_no }) : null
      ]),
      el("div", { style: "text-align:right" }, [
        voucher.payment_mode ? el("div.doc-meta", { text: "Paid by " + voucher.payment_mode }) : null,
        voucher.due_date_ad ? el("div.doc-meta", { text: "Due " + UI.bs(voucher.due_date_ad, "short") }) : null
      ])
    ]);

    var content;
    if (isInvoice) {
      // The Harmonised System heading is only worth a column when the goods
      // actually carry one. An empty column on every bill helps nobody.
      var anyHsCode = data.items.some(function (item) { return item.hs_code; });
      var itemRows = data.items.map(function (item, index) {
        return el("tr", {}, [
          el("td.mid", { text: String(index + 1) }),
          el("td", {}, [
            el("div", { text: item.item_name }),
            item.description ? el("div", { text: item.description, style: "font-size:.76rem;color:var(--ink-faint)" }) : null
          ]),
          anyHsCode ? el("td.mid", { text: item.hs_code || "" }) : null,
          el("td.num", { text: NP.formatQty(item.qty) + " " + (item.unit_symbol || "") }),
          el("td.num", { text: UI.rs(item.rate_paisa) }),
          el("td.num", { text: (item.discount_paisa + (item.bill_discount_paisa || 0))
            ? UI.rs(item.discount_paisa + (item.bill_discount_paisa || 0)) : "" }),
          el("td.num", { text: UI.rs(item.taxable_paisa) }),
          el("td.num", { text: item.vat_paisa ? UI.rs(item.vat_paisa) : "" }),
          el("td.num", { text: UI.rs(item.amount_paisa) })
        ]);
      });
      var footRows = [];
      function totalRow(label, value, strong) {
        footRows.push(el("tr" + (strong ? ".total-row" : ""), {}, [
          el("td", { colspan: anyHsCode ? "8" : "7", text: label,
                     style: "text-align:right" }),
          el("td.num", { text: UI.rs(value) })
        ]));
      }
      totalRow("Subtotal", voucher.subtotal_paisa);
      if (voucher.discount_paisa - (voucher.bill_discount_paisa || 0)) {
        totalRow("Discount on the lines",
                 -(voucher.discount_paisa - (voucher.bill_discount_paisa || 0)));
      }
      if (voucher.bill_discount_paisa) {
        totalRow("Discount on the bill", -voucher.bill_discount_paisa);
      }
      if (voucher.exempt_paisa) { totalRow("Exempt", voucher.exempt_paisa); }
      totalRow("Taxable amount", voucher.taxable_paisa);
      if (voucher.vat_paisa) { totalRow("VAT 13 percent", voucher.vat_paisa); }
      if (voucher.other_charges_paisa) { totalRow("Other charges", voucher.other_charges_paisa); }
      if (voucher.tds_paisa) { totalRow("Tax deducted at source", -voucher.tds_paisa); }
      if (voucher.round_off_paisa) {
        totalRow("Before rounding", voucher.total_paisa - voucher.round_off_paisa);
        totalRow(voucher.round_off_paisa > 0 ? "Rounded up to the rupee"
                                             : "Rounded down to the rupee",
                 voucher.round_off_paisa);
      }
      totalRow("Total", voucher.total_paisa, true);

      content = el("div", {}, [
        el("div.table-wrap", {}, [el("table.doc-table", {}, [
          el("thead", {}, [el("tr", {}, [
            el("th.mid", { text: "SN" }), el("th", { text: "Particulars" }),
            anyHsCode ? el("th.mid", { text: "HS code" }) : null,
            el("th.num", { text: "Quantity" }), el("th.num", { text: "Rate" }),
            el("th.num", { text: "Discount" }), el("th.num", { text: "Taxable" }),
            el("th.num", { text: "VAT" }), el("th.num", { text: "Amount" })
          ])]),
          el("tbody", {}, itemRows),
          el("tfoot", {}, footRows)
        ])]),
        showWords ? el("p.in-words", { text: "In words: " + data.in_words }) : null,
        showWords ? el("p.in-words", { text: data.in_words_np }) : null
      ]);
      // Every voucher shows the entry it made, an invoice included. An
      // accountant checking a bill wants to see which ledgers moved and by how
      // much, not only what the customer was charged.
      content.appendChild(entryTable(data, "How it was posted"));
    } else {
      content = el("div", {}, [
        entryTable(data, null),
        el("p.in-words", { text: "In words: " + data.in_words })
      ]);
    }

    var sheet = el("div.doc-sheet", {}, [
      head,
      el("div.doc-title", {}, [
        el("div", { text: titles[voucher.voucher_type] || voucher.voucher_type }),
        titlesNp[voucher.voucher_type]
          ? el("div", { text: titlesNp[voucher.voucher_type],
                        style: "font-weight:600;letter-spacing:normal;margin-top:.05rem" })
          : null,
        isTaxInvoice
          ? el("div", { style: "font-size:.71rem;font-weight:500;letter-spacing:.03em;"
              + "text-transform:none;margin-top:.28rem;color:#55636f",
              text: "Original Copy  ( मूल प्रति )  for the buyer" })
          : null
      ]),
      parties,
      content,
      voucher.narration ? el("p", { text: voucher.narration, style: "font-size:.84rem;margin-top:.6rem" }) : null,
      settings.invoice_terms && isInvoice
        ? el("p.doc-meta", { style: "margin-top:.6rem;white-space:pre-wrap", text: settings.invoice_terms })
        : null,
      voucher.status === "cancelled"
        ? el("p", { style: "color:var(--bad);font-weight:600", text:
            "Cancelled by " + voucher.cancelled_by + " on " + voucher.cancelled_at
            + ". Reason: " + voucher.cancel_reason })
        : null,
      el("div.doc-foot", {}, [
        el("div.sign-line", { text: "Prepared by" }),
        el("div.sign-line", { text: "Checked by" }),
        el("div.sign-line", { text: voucher.voucher_type === "sales"
          ? "Received by, with seal" : "Authorised by" })
      ]),
      settingsFooter
        ? el("p.doc-meta", { style: "text-align:center;margin-top:.8rem", text: settingsFooter })
        : null,
      isTaxInvoice
        ? el("p.doc-meta", { style: "text-align:center;margin-top:.3rem;font-size:.69rem",
            text: "Issued under the Value Added Tax Act, 2052 and the Value Added Tax Rules, 2053." })
        : null
    ]);
    return sheet;
  }

  return {
    view: view, renderVoucher: renderVoucher,
    // Shared with the screens defined below, which sit outside this closure.
    partyPicker: partyPicker, accountPicker: accountPicker, itemPicker: itemPicker,
    loadNextNumber: loadNextNumber
  };
}());

/* Credit and debit notes.

   No goods move. These are for a rate agreed after the invoice went out, a
   discount allowed later, a short delivery claimed against a supplier, or any
   other adjustment to what is owed. The tax on the adjustment goes into the
   month the note is dated, which is what the Value Added Tax Act requires. */

(function () {
  "use strict";
  var el = UI.el, api = UI.api;
  var partyPicker = Vouchers.partyPicker;
  var accountPicker = Vouchers.accountPicker;
  var itemPicker = Vouchers.itemPicker;
  var loadNextNumber = Vouchers.loadNextNumber;
  var view = Vouchers.view;

  var NOTE_KINDS = {
    credit_note: {
      endpoint: "credit-note", party: "customer", title: "Credit note",
      partyLabel: "Customer", defaultAccount: "4132",
      effect: "The customer will owe less.",
      note: "Issued to a customer. Use it for a rate agreed after the invoice, a discount "
            + "allowed later, or an allowance for goods that were not right. Output tax is "
            + "adjusted in the month this note is dated."
    },
    debit_note: {
      endpoint: "debit-note", party: "supplier", title: "Debit note",
      partyLabel: "Supplier", defaultAccount: "5105",
      effect: "You will owe the supplier less.",
      note: "Raised on a supplier. Use it to claim a short delivery, a rate difference or a "
            + "discount agreed after their bill. Input tax claimed is adjusted with it."
    }
  };

  function noteScreen(kind) {
    var spec = NOTE_KINDS[kind];
    return function (page) {
      var dateField = UI.dateField(NP.todayIso(), function () { refreshNumber(); });
      var numberInput = el("input", { type: "text" });
      var partyInput = el("input", { type: "text", placeholder: spec.partyLabel + " name" });
      var partyId = null;
      var partyNote = el("div.hint");
      var referenceInput = el("input", { type: "text", placeholder: "Against invoice or bill number" });
      var amountInput = UI.amountInput("", { onChange: recalc });
      var vatBox = el("input", { type: "checkbox" });
      vatBox.checked = !!(App.state.company && App.state.company.vat_registered);
      var vatRate = el("input", { type: "number", step: "0.01", value: 13 });
      var accountInput = el("input", { type: "text", placeholder: "Which account it goes to" });
      var accountId = null;
      var reasonInput = el("input", { type: "text", placeholder: "Why the note is being raised" });
      var summary = el("div.totals-box");

      partyPicker(partyInput, spec.party, function (party) {
        partyId = party.id;
        partyInput.value = party.name;
        partyNote.textContent = party.pan ? "PAN " + party.pan : "";
      });
      partyInput.addEventListener("input", function () {
        if (!partyInput.value.trim()) { partyId = null; partyNote.textContent = ""; }
      });
      accountPicker(accountInput, function (account) {
        accountId = account.id;
        accountInput.value = account.name;
        recalc();
      });
      vatBox.addEventListener("change", function () {
        vatRate.disabled = !vatBox.checked;
        recalc();
      });
      vatRate.addEventListener("input", recalc);
      vatRate.disabled = !vatBox.checked;

      // Start on the account this kind of note usually goes to.
      api("/api/accounts", { query: { q: spec.defaultAccount } }).then(function (data) {
        var found = data.rows.filter(function (a) { return a.code === spec.defaultAccount; })[0];
        if (found && !accountId) {
          accountId = found.id;
          accountInput.value = found.name;
        }
      });

      function recalc() {
        var amount = NP.toPaisa(amountInput.value || 0);
        var bp = vatBox.checked ? Math.round((parseFloat(vatRate.value) || 0) * 100) : 0;
        var vat = NP.applyRate(amount, bp);
        UI.clear(summary);
        function row(label, value, cls) {
          summary.appendChild(el("div" + (cls ? "." + cls : ""), {}, [
            el("span", { text: label }), el("span.num", { text: UI.rs(value) })
          ]));
        }
        row("Amount of the adjustment", amount);
        if (vat) { row("Tax at " + (bp / 100) + " percent", vat); }
        row("Total on the note", amount + vat, "grand");
        summary.appendChild(el("div.in-words", { text: spec.effect }));
      }

      function refreshNumber() { loadNextNumber(kind, dateField.getIso(), numberInput); }

      function save() {
        if (!partyId) { UI.flash("Choose the " + spec.partyLabel.toLowerCase() + ".", "bad"); return; }
        if (!NP.toPaisa(amountInput.value || 0)) { UI.flash("Enter the amount.", "bad"); return; }
        api("/api/vouchers/" + spec.endpoint, { body: {
          date_ad: dateField.getIso(), number: numberInput.value.trim(),
          party_id: partyId, reference_no: referenceInput.value.trim(),
          amount: amountInput.value,
          vat_bp: vatBox.checked ? Math.round((parseFloat(vatRate.value) || 0) * 100) : 0,
          account_id: accountId, reason: reasonInput.value.trim()
        }}).then(function (data) {
          UI.flash(spec.title + " " + data.voucher.voucher.number + " saved.", "good");
          view(data.id);
        }).catch(function (error) { UI.flash(error.message, "bad"); });
      }

      recalc();
      refreshNumber();

      page.appendChild(el("div.card", {}, [
        el("p.card-note", { text: spec.note }),
        el("div.row", { style: "margin-top:.7rem" }, [
          UI.field("Date", dateField),
          UI.field("Number", numberInput),
          UI.field(spec.partyLabel, el("div", {}, [partyInput, partyNote])),
          UI.field("Against", referenceInput)
        ]),
        el("div.row", {}, [
          UI.field("Amount before tax", amountInput),
          UI.field("Tax applies", el("label.check", {}, [vatBox, el("span", { text: "Adjust VAT too" })])),
          UI.field("Rate percent", vatRate),
          UI.field("Post the adjustment to", accountInput)
        ]),
        UI.field("Reason", reasonInput,
          "This appears on the note and in the audit trail, so make it specific.")
      ]));

      page.appendChild(el("div.card", {}, [
        el("div", { style: "display:flex" }, [summary])
      ]));

      page.appendChild(el("div.card", {}, [
        el("div.row", {}, [
          el("button.primary", { text: "Save the note", onclick: save }),
          el("button.ghost", { text: "Clear the form", onclick: function () { App.go(kind); } })
        ])
      ]));

      setTimeout(function () { partyInput.focus(); }, 60);
    };
  }

  App.register("credit_note", noteScreen("credit_note"));
  App.register("debit_note", noteScreen("debit_note"));

  /* Stock adjustment.

     What the shelf actually holds against what the book says. Each line is
     valued at weighted average cost, so the difference lands on its own line in
     the profit and loss instead of disappearing into cost of sales. */

  App.register("stock_adjust", function (page) {
    var dateField = UI.dateField(NP.todayIso(), function () { refreshNumber(); repriceAll(); });
    var numberInput = el("input", { type: "text" });
    var referenceInput = el("input", { type: "text", placeholder: "Count sheet reference" });
    var narration = el("input", { type: "text", value: "Physical stock count" });
    var grid = el("tbody");
    var summary = el("div.totals-box");
    var reasons = [];
    var lines = [];

    function blank() { return { itemId: null, name: "", unit: "", onHand: 0,
                                qty: "", reason: "shortage", rate: 0, value: 0,
                                direction: -1 }; }

    var focusAfterDraw = null;

    function addLine(focus) {
      lines.push(blank());
      if (focus) { focusAfterDraw = { index: lines.length - 1, field: "item" }; }
      drawLines();
    }

    function directionOf(reasonCode) {
      var found = reasons.filter(function (r) { return r.code === reasonCode; })[0];
      return found ? found.direction : -1;
    }

    function drawLines() {
      UI.clear(grid);
      lines.forEach(function (line, index) {
        var nameInput = el("input", { type: "text", class: "adj-item", value: line.name });
        var onHand = el("td.num", { text: line.itemId ? NP.formatQty(line.onHand) : "",
                                    style: "color:var(--ink-soft)" });
        var reasonSelect = UI.select(reasons.map(function (r) {
          return { value: r.code, label: r.label };
        }), line.reason, function (value) { line.reason = value; reprice(line); });
        var qtyInput = UI.amountInput(line.qty, { onChange: function (v) {
          line.qty = v; reprice(line);
        }});
        var rateCell = el("td.num", { text: line.rate ? UI.rs(line.rate) : "" });
        var valueCell = el("td.num", { text: "" });
        line.cells = { onHand: onHand, rate: rateCell, value: valueCell };

        itemPicker(nameInput, function (item) {
          line.itemId = item.id;
          line.name = item.name;
          line.unit = item.unit_symbol || "";
          nameInput.value = item.name;
          // Ask the server once what this item is carried at, then everything
          // after that is worked out here so typing never waits on a request.
          lookupCost(line, function () {
            focusAfterDraw = { index: index, field: "qty" };
            drawLines();
          });
        }, "goods");
        nameInput.addEventListener("input", function () {
          line.name = nameInput.value;
          if (!nameInput.value.trim()) { line.itemId = null; }
        });

        qtyInput.classList.add("adj-qty");
        grid.appendChild(el("tr", {}, [
          el("td.muted", { text: String(index + 1), style: "width:24px" }),
          el("td", {}, [nameInput]),
          el("td.muted", { text: line.unit, style: "width:48px;font-size:.78rem" }),
          onHand,
          el("td", { style: "width:180px" }, [reasonSelect]),
          el("td", { style: "width:88px" }, [qtyInput]),
          rateCell,
          valueCell,
          el("td", { style: "width:26px" }, [
            el("button.line-remove", { text: "×", onclick: function () {
              lines.splice(index, 1);
              if (!lines.length) { addLine(); } else { drawLines(); }
              recalc();
            }})
          ])
        ]));
      });
      recalc();
      if (focusAfterDraw) {
        var selector = focusAfterDraw.field === "qty" ? ".adj-qty" : ".adj-item";
        var found = UI.qsa(selector, grid)[focusAfterDraw.index];
        focusAfterDraw = null;
        if (found) { found.focus(); found.select && found.select(); }
      }
    }

    function lookupCost(line, done) {
      // One request per item, asking with a quantity of one so the rate and the
      // quantity on hand come back even before anything has been counted.
      api("/api/vouchers/stock-adjust/preview", { body: {
        date_ad: dateField.getIso(),
        items: [{ item_id: line.itemId, qty: "1", reason: line.reason }]
      }}).then(function (data) {
        var priced = data.lines[0];
        line.rate = priced.rate;
        line.onHand = priced.on_hand_before;
        reprice(line);
        if (done) { done(); }
      }).catch(function (error) {
        UI.flash(error.message, "bad");
        if (done) { done(); }
      });
    }

    function reprice(line) {
      line.direction = directionOf(line.reason);
      var qty = NP.toQty(line.qty || 0);
      line.value = line.rate ? NP.roundHalfUp(qty * line.rate, 1000) : 0;
      if (line.cells) {
        line.cells.onHand.textContent = line.itemId ? NP.formatQty(line.onHand) : "";
        line.cells.rate.textContent = line.rate ? UI.rs(line.rate) : "";
        line.cells.value.textContent = line.value
          ? (line.direction < 0 ? "-" : "") + UI.rs(line.value) : "";
        if (line.direction < 0 && qty > line.onHand) {
          line.cells.onHand.classList.add("negative");
        } else {
          line.cells.onHand.classList.remove("negative");
        }
      }
      recalc();
    }

    function repriceAll() {
      lines.forEach(function (line) {
        if (line.itemId) { lookupCost(line); }
      });
    }

    function recalc() {
      var down = 0, up = 0;
      lines.forEach(function (line) {
        if (!line.itemId || !line.value) { return; }
        if (line.direction < 0) { down += line.value; } else { up += line.value; }
      });
      UI.clear(summary);
      function row(label, value, cls) {
        summary.appendChild(el("div" + (cls ? "." + cls : ""), {}, [
          el("span", { text: label }), el("span.num", { text: UI.rs(value) })
        ]));
      }
      if (up) { row("Found on counting", up); }
      if (down) { row("Short on counting", -down); }
      row("Net effect on stock", up - down, "grand");
      summary.appendChild(el("div.in-words", {
        text: "Valued at weighted average cost on the date of the count." }));
    }

    function refreshNumber() { loadNextNumber("stock_adjust", dateField.getIso(), numberInput); }

    function save() {
      var used = lines.filter(function (line) {
        return line.itemId && NP.toQty(line.qty || 0);
      });
      if (!used.length) { UI.flash("Add at least one line.", "bad"); return; }
      api("/api/vouchers/stock-adjust", { body: {
        date_ad: dateField.getIso(), number: numberInput.value.trim(),
        reference_no: referenceInput.value.trim(), narration: narration.value.trim(),
        items: used.map(function (line) {
          return { item_id: line.itemId, qty: line.qty, reason: line.reason };
        })
      }}).then(function (data) {
        UI.flash("Adjustment " + data.voucher.voucher.number + " saved.", "good");
        view(data.id);
      }).catch(function (error) { UI.flash(error.message, "bad"); });
    }

    page.appendChild(el("div.card", {}, [
      el("p.card-note", { text: "Enter what the count found against what the book says. Each "
        + "line is valued at weighted average cost, and the reason decides which account the "
        + "difference goes to, so a shortage, a breakage and goods taken for the house are never "
        + "mixed together." }),
      el("div.row", { style: "margin-top:.7rem" }, [
        UI.field("Date of the count", dateField),
        UI.field("Number", numberInput),
        UI.field("Count sheet reference", referenceInput),
        UI.field("Narration", narration)
      ])
    ]));

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [el("h2", { text: "What the count found" })]),
      el("div.table-wrap", {}, [
        el("table.entry-grid", {}, [
          el("thead", {}, [el("tr", {}, [
            el("th", { text: "" }), el("th", { text: "Item" }), el("th", { text: "Unit" }),
            el("th.num", { text: "On hand" }), el("th", { text: "Reason" }),
            el("th.num", { text: "Quantity" }), el("th.num", { text: "Cost rate" }),
            el("th.num", { text: "Value" }), el("th", { text: "" })
          ])]),
          grid
        ])
      ]),
      el("div.row", { style: "margin-top:.5rem" }, [
        el("button.secondary", { text: "Add a line", onclick: function () { addLine(true); } })
      ]),
      el("div", { style: "display:flex;margin-top:.6rem" }, [summary])
    ]));

    page.appendChild(el("div.card", {}, [
      el("div.row", {}, [
        el("button.primary", { text: "Save the adjustment", onclick: save }),
        el("button.ghost", { text: "Clear the form", onclick: function () { App.go("stock_adjust"); } })
      ])
    ]));

    return api("/api/adjustment-reasons").then(function (data) {
      reasons = data.rows;
      addLine();
      refreshNumber();
    });
  });
}());

/* Receipts and payments.

   Money almost never arrives on its own. It arrives against particular
   invoices, sometimes with something allowed off for settling early. This
   screen shows what is open, lets the amount and the discount be put against
   each bill, and posts the three sided entry that results.

   Anything that is not against a bill, paying the electricity for instance,
   goes on the free grid instead, one click away. */

(function () {
  "use strict";
  var el = UI.el, api = UI.api;
  var partyPicker = Vouchers.partyPicker;
  var accountPicker = Vouchers.accountPicker;
  var loadNextNumber = Vouchers.loadNextNumber;
  var view = Vouchers.view;

  var SETTLE = {
    receipt: {
      title: "Receipt", party: "customer", side: "receivable",
      partyLabel: "Customer", moneyLabel: "Received into",
      amountLabel: "Received", discountLabel: "Discount allowed",
      discountAccount: "4132", freeScreen: "receipt_free",
      note: "Money coming in. Tick the bills it settles. Anything allowed off for "
            + "paying early goes in the discount column and is posted to Discount Allowed."
    },
    payment: {
      title: "Payment", party: "supplier", side: "payable",
      partyLabel: "Supplier", moneyLabel: "Paid from",
      amountLabel: "Paid", discountLabel: "Discount received",
      discountAccount: "5105", freeScreen: "payment_free",
      note: "Money going out against a supplier's bills. Anything they allow off for "
            + "paying early goes in the discount column and is taken off the cost of "
            + "purchase, which is where NAS 02 puts it."
    }
  };

  function settlementScreen(kind) {
    var spec = SETTLE[kind];
    return function (page) {
      var dateField = UI.dateField(NP.todayIso(), function () { refreshNumber(); reload(); });
      var numberInput = el("input", { type: "text" });
      var partyInput = el("input", { type: "text", placeholder: spec.partyLabel + " name" });
      var partyId = null;
      var partyNote = el("div.hint");
      var bankInput = el("input", { type: "text", placeholder: "Cash box or bank account" });
      var bankId = null;
      var paymentMode = UI.select([
        { value: "cash", label: "Cash" },
        { value: "cheque", label: "Cheque" },
        { value: "bank", label: "Bank transfer" },
        { value: "card", label: "Card" },
        { value: "wallet", label: "Mobile wallet" }
      ], "cash");
      var referenceInput = el("input", { type: "text", placeholder: "Cheque or reference number" });
      var narration = el("input", { type: "text" });
      var onAccount = UI.amountInput("", { onChange: recalc });
      var discountAccountInput = el("input", { type: "text" });
      var discountAccountId = null;
      var billsBox = el("div");
      var summary = el("div.totals-box");
      var bills = [];

      partyPicker(partyInput, spec.party, function (party) {
        partyId = party.id;
        partyInput.value = party.name;
        partyNote.textContent = (party.pan ? "PAN " + party.pan + ".  " : "")
          + (party.credit_days ? "Credit " + party.credit_days + " days." : "");
        reload();
      });
      partyInput.addEventListener("input", function () {
        if (!partyInput.value.trim()) {
          partyId = null; partyNote.textContent = ""; bills = []; drawBills();
        }
      });

      accountPicker(bankInput, function (account) {
        bankId = account.id;
        bankInput.value = account.name;
      });
      api("/api/banking/accounts").then(function (data) {
        var preferred = data.rows.filter(function (a) {
          return a.account_kind === (kind === "receipt" ? "cash" : "bank");
        })[0] || data.rows[0];
        if (preferred && !bankId) { bankId = preferred.id; bankInput.value = preferred.name; }
      });

      accountPicker(discountAccountInput, function (account) {
        discountAccountId = account.id;
        discountAccountInput.value = account.name;
      });
      api("/api/accounts", { query: { q: spec.discountAccount } }).then(function (data) {
        var found = data.rows.filter(function (a) { return a.code === spec.discountAccount; })[0];
        if (found && !discountAccountId) {
          discountAccountId = found.id;
          discountAccountInput.value = found.name;
        }
      });

      function reload() {
        if (!partyId) { bills = []; drawBills(); return; }
        api("/api/open-bills", { query: {
          party_id: partyId, side: spec.side, as_at: dateField.getIso()
        }}).then(function (data) {
          bills = data.bills.map(function (bill) {
            return { voucher_id: bill.voucher_id, number: bill.number,
                     date_bs: bill.date_bs, date_ad: bill.date_ad,
                     age: bill.age_days, outstanding: bill.amount,
                     amount: "", discount: "" };
          });
          drawBills();
        }).catch(function (error) { UI.flash(error.message, "bad"); });
      }

      function drawBills() {
        UI.clear(billsBox);
        if (!partyId) {
          billsBox.appendChild(el("div.empty", {}, [
            el("strong", { text: "Choose a " + spec.partyLabel.toLowerCase() }),
            el("span", { text: "Their open bills appear here, oldest first." })
          ]));
          recalc();
          return;
        }
        if (!bills.length) {
          billsBox.appendChild(el("div.empty", {}, [
            el("strong", { text: "Nothing open" }),
            el("span", { text: "There is no unpaid bill for this party. Anything entered "
              + "below will sit on account until a bill is raised." })
          ]));
          recalc();
          return;
        }

        var rows = bills.map(function (bill, index) {
          var amountInput = UI.amountInput(bill.amount, { onChange: function (v) {
            bill.amount = v; recalc();
          }});
          var discountInput = UI.amountInput(bill.discount, { onChange: function (v) {
            bill.discount = v; recalc();
          }});
          var tick = el("input", { type: "checkbox" });
          tick.addEventListener("change", function () {
            if (tick.checked) {
              bill.amount = String(bill.outstanding / 100);
              amountInput.value = bill.amount;
            } else {
              bill.amount = ""; bill.discount = "";
              amountInput.value = ""; discountInput.value = "";
            }
            recalc();
          });
          bill.tick = tick;
          return el("tr" + (bill.age > 0 ? ".overdue" : ""), {}, [
            el("td.mid", {}, [tick]),
            el("td", { text: bill.number }),
            el("td", { text: bill.date_bs || "" }),
            el("td.num", { text: bill.age === null || bill.age === undefined ? ""
                           : (bill.age <= 0 ? "not due" : bill.age + " d") }),
            el("td.num", { text: UI.rs(bill.outstanding) }),
            el("td", { style: "width:118px" }, [amountInput]),
            el("td", { style: "width:110px" }, [discountInput])
          ]);
        });

        billsBox.appendChild(UI.table([
          { label: "", mid: true }, "Bill", "Date", { label: "Age", num: true },
          { label: "Outstanding", num: true },
          { label: spec.amountLabel, num: true },
          { label: spec.discountLabel, num: true }
        ], rows, null, { tall: true }));

        billsBox.appendChild(el("div.row", { style: "margin-top:.5rem" }, [
          el("button.secondary", { text: "Settle everything", onclick: function () {
            bills.forEach(function (bill) {
              bill.amount = String(bill.outstanding / 100);
              if (bill.tick) { bill.tick.checked = true; }
            });
            drawBills();
          }}),
          el("button.secondary", { text: "Clear", onclick: function () {
            bills.forEach(function (bill) { bill.amount = ""; bill.discount = ""; });
            drawBills();
          }})
        ]));
        recalc();
      }

      function totals() {
        var settled = 0, discount = 0;
        bills.forEach(function (bill) {
          settled += NP.toPaisa(bill.amount || 0);
          discount += NP.toPaisa(bill.discount || 0);
        });
        var advance = NP.toPaisa(onAccount.value || 0);
        return { settled: settled, discount: discount, advance: advance,
                 money: settled + advance, party: settled + advance + discount };
      }

      function recalc() {
        var t = totals();
        UI.clear(summary);
        function row(label, value, cls) {
          summary.appendChild(el("div" + (cls ? "." + cls : ""), {}, [
            el("span", { text: label }), el("span.num", { text: UI.rs(value) })
          ]));
        }
        if (t.settled) { row("Set against bills", t.settled); }
        if (t.advance) { row("On account", t.advance); }
        row(spec.amountLabel + " in total", t.money);
        if (t.discount) { row(spec.discountLabel, t.discount); }
        row("Taken off the account", t.party, "grand");
        summary.appendChild(el("div.in-words", { text: kind === "receipt"
          ? "The customer will owe " + UI.rs(t.party) + " less."
          : "You will owe the supplier " + UI.rs(t.party) + " less." }));
      }

      function refreshNumber() { loadNextNumber(kind, dateField.getIso(), numberInput); }

      function save() {
        var t = totals();
        if (!partyId) { UI.flash("Choose the " + spec.partyLabel.toLowerCase() + ".", "bad"); return; }
        if (!bankId) { UI.flash("Choose the cash box or bank account.", "bad"); return; }
        if (!t.party) { UI.flash("Nothing has been entered.", "bad"); return; }
        var over = bills.filter(function (bill) {
          return NP.toPaisa(bill.amount || 0) + NP.toPaisa(bill.discount || 0)
                 > bill.outstanding;
        });
        if (over.length) {
          UI.flash("Bill " + over[0].number + " is being settled for more than is open on it.",
                   "bad");
          return;
        }
        api("/api/vouchers/settle", { query: { kind: kind }, body: {
          date_ad: dateField.getIso(), number: numberInput.value.trim(),
          party_id: partyId, bank_account_id: bankId,
          discount_account_id: discountAccountId,
          payment_mode: paymentMode.value, reference_no: referenceInput.value.trim(),
          narration: narration.value.trim(),
          on_account: onAccount.value || 0,
          allocations: bills.filter(function (bill) {
            return NP.toPaisa(bill.amount || 0) || NP.toPaisa(bill.discount || 0);
          }).map(function (bill) {
            return { voucher_id: bill.voucher_id, number: bill.number,
                     amount: bill.amount || 0, discount: bill.discount || 0 };
          })
        }}).then(function (data) {
          UI.flash(spec.title + " " + data.voucher.voucher.number + " saved.", "good");
          view(data.id);
        }).catch(function (error) { UI.flash(error.message, "bad"); });
      }

      refreshNumber();
      recalc();

      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: spec.title }),
          el("button.link-button", { text: "Enter it as a free journal instead",
                                     onclick: function () { App.go(spec.freeScreen); } })
        ]),
        el("p.card-note", { text: spec.note }),
        el("div.row", { style: "margin-top:.7rem" }, [
          UI.field("Date", dateField),
          UI.field("Number", numberInput),
          UI.field(spec.partyLabel, el("div", {}, [partyInput, partyNote])),
          UI.field(spec.moneyLabel, bankInput)
        ]),
        el("div.row", {}, [
          UI.field("How", paymentMode),
          UI.field("Reference", referenceInput),
          UI.field("Narration", narration)
        ])
      ]));

      page.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [el("h2", { text: "Which bills it settles" })]),
        billsBox
      ]));

      page.appendChild(el("div.card", {}, [
        el("div.row", {}, [
          el("div.field", { style: "flex:0 0 200px" }, [
            el("label", { text: "Not against any bill" }), onAccount,
            el("div.hint", { text: "An advance, or money on account" })
          ]),
          el("div.field", { style: "flex:1 1 240px" }, [
            el("label", { text: spec.discountLabel + " goes to" }), discountAccountInput
          ]),
          el("div.spacer")
        ]),
        el("div", { style: "display:flex;margin-top:.6rem" }, [summary])
      ]));

      page.appendChild(el("div.card", {}, [
        el("div.row", {}, [
          el("button.primary", { text: "Save the " + spec.title.toLowerCase(), onclick: save }),
          el("button.ghost", { text: "Clear the form", onclick: function () { App.go(kind); } })
        ])
      ]));

      setTimeout(function () { partyInput.focus(); }, 60);
    };
  }

  App.register("receipt", settlementScreen("receipt"));
  App.register("payment", settlementScreen("payment"));
}());
