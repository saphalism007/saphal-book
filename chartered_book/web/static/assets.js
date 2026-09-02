/* The fixed asset register.

   One row for each thing the business owns, with what it cost, when it was
   bought, how the books write it down, and which class it falls in under
   Schedule 2 of the Income Tax Act, 2058. This is the schedule an auditor ticks
   physical verification against, and it is what makes the tax depreciation and
   deferred tax workings possible. */

var Assets = (function () {
  "use strict";

  var el = UI.el, api = UI.api;
  var taxClasses = [];
  var assetAccounts = [];

  App.register("assets", function (page) {
    var box = el("div");
    var bar = Reports.periodBar(load);
    var hideDisposed = el("input", { type: "checkbox" });
    hideDisposed.addEventListener("change", load);

    function load() {
      return api("/api/assets", { query: {
        from_ad: bar.from.getIso(), to_ad: bar.to.getIso(),
        hide_disposed: hideDisposed.checked ? "1" : ""
      }}).then(function (data) {
        assetAccounts = data.accounts || [];
        UI.clear(box);

        box.appendChild(el("div.grid.four", { style: "margin-bottom:.9rem" }, [
          tile("Assets held", String(data.count), "On the register", "violet"),
          tile("Cost", UI.rs(data.totals.cost), "What was paid for them", "teal"),
          tile("Written off", UI.rs(data.totals.closing_accumulated),
               "Depreciation to date", "amber"),
          tile("Carrying amount", UI.rs(data.totals.carrying), "What the books show", "good")
        ]));

        var currentClass = null;
        var rows = [];
        data.rows.forEach(function (asset) {
          if (asset.tax_class !== currentClass) {
            currentClass = asset.tax_class;
            var info = taxClasses.filter(function (c) { return c.code === currentClass; })[0];
            rows.push(el("tr.group-row", {}, [
              el("td", { text: "Class " + currentClass }),
              el("td", { colspan: "9", text: info ? info.description : "" })
            ]));
          }
          rows.push(el("tr.clickable" + (asset.disposed ? ".cancelled" : ""), {
            onclick: function () { openForm(asset); }
          }, [
            el("td", { text: asset.code }),
            el("td", {}, [
              el("div", { text: asset.name }),
              asset.location || asset.serial_no
                ? el("div.muted", { style: "font-size:.74rem",
                    text: [asset.location, asset.serial_no].filter(Boolean).join("  ") })
                : null
            ]),
            el("td", { text: asset.acquired_bs }),
            el("td.muted", { text: asset.acquired_ad, style: "font-size:.74rem" }),
            el("td.num", { text: UI.rs(asset.cost) }),
            el("td.mid", { text: asset.book_method === "slm" ? "Straight line"
                           : asset.book_method === "none" ? "Not written down" : "Reducing",
                           style: "font-size:.76rem" }),
            el("td.num", { text: asset.book_method === "slm"
                           ? (asset.useful_life_years + " yr")
                           : (asset.book_rate_bp / 100) + "%" }),
            el("td.num", { text: UI.rs(asset.charge, { blankZero: true }) }),
            el("td.num", { text: UI.rs(asset.closing_accumulated, { blankZero: true }) }),
            el("td.num", { text: UI.rs(asset.carrying) })
          ]));
        });

        box.appendChild(UI.table([
          "Code", "Asset", "Bought (BS)", "Bought (AD)", { label: "Cost", num: true },
          { label: "Method", mid: true }, { label: "Rate or life", num: true },
          { label: "Charge this year", num: true },
          { label: "Written off to date", num: true },
          { label: "Carrying amount", num: true }
        ], rows, [el("tr.total-row", {}, [
          el("td", { colspan: "4", text: "Total of assets held" }),
          el("td.num", { text: UI.rs(data.totals.cost) }),
          el("td"), el("td"),
          el("td.num", { text: UI.rs(data.totals.charge) }),
          el("td.num", { text: UI.rs(data.totals.closing_accumulated) }),
          el("td.num", { text: UI.rs(data.totals.carrying) })
        ])], { tall: true,
               emptyText: "Nothing on the register yet. Add the assets the business owns." }));

        if (data.disposed_count) {
          box.appendChild(el("p.card-note", { style: "margin-top:.6rem",
            text: data.disposed_count + " asset" + (data.disposed_count === 1 ? "" : "s")
              + " disposed of, shown struck through. They stay on the register because the "
              + "tax pool still has to account for what they were sold for." }));
        }
      });
    }

    function tile(label, value, note, kind) {
      return el("div.tile" + (kind ? "." + kind : ""), {}, [
        el("div.tile-label", { text: label }),
        el("div.tile-value", { text: value }),
        note ? el("div.tile-note", { text: note }) : null
      ]);
    }

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [
        el("h2", { text: "Fixed asset register" }),
        el("button.primary", { text: "Add an asset", onclick: function () { openForm(null); } })
      ]),
      el("p.card-note", { text: "What the books write off need not match what the Income Tax "
        + "Act allows, and usually does not. The register keeps both, which is what the "
        + "deferred tax working is built on." }),
      el("div.toolbar", {}, [
        el("label.check", {}, [hideDisposed, el("span", { text: "Hide disposals" })])
      ]),
      bar, box
    ]));

    return api("/api/tax-classes").then(function (data) {
      taxClasses = data.rows;
      return load();
    });
  });

  function openForm(asset) {
    var isNew = !asset;
    var name = el("input", { type: "text", value: asset ? asset.name : "" });
    var code = el("input", { type: "text", value: asset ? asset.code : "",
                             placeholder: "left blank, one is made for you" });
    var description = el("input", { type: "text", value: asset ? asset.description : "" });
    var account = UI.select(assetAccounts
      .filter(function (a) { return a.group_code !== "1120"; })
      .map(function (a) { return { value: a.id, label: a.code + "  " + a.name }; }),
      asset ? asset.account_id : "");
    var taxClass = UI.select(taxClasses.map(function (c) {
      return { value: c.code, label: "Class " + c.code + " at " + (c.rate_bp / 100)
               + "%  ·  " + c.description.slice(0, 60) };
    }), asset ? asset.tax_class : "D");
    var acquired = UI.dateField(asset ? asset.acquired_ad : NP.todayIso());
    var cost = UI.amountInput(asset ? asset.cost / 100 : "");
    var method = UI.select([
      { value: "wdv", label: "Reducing balance" },
      { value: "slm", label: "Straight line" },
      { value: "none", label: "Not written down" }
    ], asset ? asset.book_method : "wdv");
    var rate = el("input", { type: "number", step: "0.01",
                             value: asset ? asset.book_rate_bp / 100 : 15 });
    var life = el("input", { type: "number", value: asset ? asset.useful_life_years : 0 });
    var residual = UI.amountInput(asset && asset.residual ? asset.residual / 100 : "");
    var openingAccum = UI.amountInput(
      asset && asset.opening_accumulated ? asset.opening_accumulated / 100 : "");
    var location = el("input", { type: "text", value: asset ? asset.location : "" });
    var serial = el("input", { type: "text", value: asset ? asset.serial_no : "" });
    var supplier = el("input", { type: "text", value: asset ? asset.supplier : "" });
    var invoice = el("input", { type: "text", value: asset ? asset.invoice_no : "" });
    var notes = el("textarea", { rows: "2" });
    notes.value = asset && asset.notes ? asset.notes : "";

    var rateField = UI.field("Rate percent a year", rate);
    var lifeField = UI.field("Useful life in years", life);
    function applyMethod() {
      rateField.style.display = method.value === "wdv" ? "" : "none";
      lifeField.style.display = method.value === "slm" ? "" : "none";
    }
    method.addEventListener("change", applyMethod);
    applyMethod();

    // Choosing a tax class suggests a book rate, which most small entities
    // simply follow so the two workings stay close together.
    taxClass.addEventListener("change", function () {
      var found = taxClasses.filter(function (c) { return c.code === taxClass.value; })[0];
      if (found && found.rate_bp && method.value === "wdv") { rate.value = found.rate_bp / 100; }
    });

    var body = el("div", {}, [
      el("div.section-title", { text: "What it is" }),
      el("div.row", {}, [UI.field("Name", name), UI.field("Code", code)]),
      UI.field("Description", description),
      el("div.row", {}, [
        UI.field("Ledger it sits in", account),
        UI.field("Class under Schedule 2 of the Income Tax Act", taxClass)
      ]),
      el("div.section-title", { text: "What it cost" }),
      el("div.row", {}, [
        UI.field("Date bought", acquired),
        UI.field("Cost", cost),
        UI.field("Residual value", residual, "What it is expected to be worth at the end")
      ]),
      el("div.section-title", { text: "How the books write it down" }),
      el("div.row", {}, [UI.field("Method", method), rateField, lifeField]),
      isNew ? UI.field("Depreciation already charged before the books began", openingAccum,
        "Leave blank for something bought after the books started") : null,
      el("div.section-title", { text: "Where it is and who supplied it" }),
      el("div.row", {}, [UI.field("Location", location), UI.field("Serial number", serial)]),
      el("div.row", {}, [UI.field("Supplier", supplier), UI.field("Their invoice number", invoice)]),
      UI.field("Notes", notes)
    ]);

    var buttons = [{ label: "Cancel" }];
    if (!isNew && !asset.disposed) {
      buttons.push({ label: "Record a disposal", action: function () {
        UI.closeModal(); openDisposal(asset); return false;
      }});
    }
    if (!isNew) {
      buttons.push({ label: "Delete", kind: "danger", action: function () {
        return api("/api/assets/" + asset.id + "/delete", { body: {} })
          .then(function () { UI.flash("Removed from the register.", "good"); App.go("assets"); });
      }});
    }
    buttons.push({ label: isNew ? "Add to the register" : "Save changes", kind: "primary",
      action: function () {
        var payload = {
          name: name.value.trim(), description: description.value.trim(),
          asset_account_id: +account.value, tax_class: taxClass.value,
          acquired_ad: acquired.getIso(), cost: cost.value || 0,
          book_method: method.value, book_rate: rate.value || 0,
          useful_life_years: +life.value || 0, residual: residual.value || 0,
          location: location.value.trim(), serial_no: serial.value.trim(),
          supplier: supplier.value.trim(), invoice_no: invoice.value.trim(),
          notes: notes.value.trim()
        };
        if (!payload.name) { UI.flash("Give the asset a name.", "bad"); return false; }
        if (!payload.asset_account_id) { UI.flash("Choose the ledger it sits in.", "bad"); return false; }
        if (isNew) {
          payload.code = code.value.trim();
          payload.opening_accumulated = openingAccum.value || 0;
          return api("/api/assets/create", { body: payload })
            .then(function () { UI.flash("Added to the register.", "good"); App.go("assets"); });
        }
        return api("/api/assets/" + asset.id + "/update", { body: payload })
          .then(function () { UI.flash("Saved.", "good"); App.go("assets"); });
      }});

    UI.modal(isNew ? "New asset" : asset.name, body, buttons, { wide: true });
  }

  function openDisposal(asset) {
    var when = UI.dateField(NP.todayIso());
    var proceeds = UI.amountInput("");
    var note = el("input", { type: "text" });
    UI.modal("Dispose of " + asset.name, el("div", {}, [
      el("p.card-note", { text: "The carrying amount today is " + UI.rs(asset.carrying)
        + ". What it sold for comes out of the tax pool, not what it cost, which is how "
        + "Schedule 2 of the Income Tax Act works." }),
      el("div.row", {}, [
        UI.field("Date sold or scrapped", when),
        UI.field("What it sold for", proceeds, "Nil if it was scrapped")
      ]),
      UI.field("Note", note)
    ]), [
      { label: "Cancel" },
      { label: "Record the disposal", kind: "danger", action: function () {
        return api("/api/assets/" + asset.id + "/dispose", { body: {
          disposed_ad: when.getIso(), proceeds: proceeds.value || 0, note: note.value.trim()
        }}).then(function () {
          UI.flash("Disposal recorded. Remember to post the entry that takes it out of the "
                   + "ledgers as well.", "warn");
          App.go("assets");
        });
      }}
    ], { slim: true });
  }

  return { openForm: openForm };
}());
