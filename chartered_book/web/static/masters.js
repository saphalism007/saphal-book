/* Customers and suppliers, items and services, and the chart of accounts.

   Every form here can be opened on its own from the Records menu, or from
   inside a voucher when something turns out to be missing. When it is opened
   from a voucher it hands the new record straight back, so the line being
   typed carries on where it left off. */

var Masters = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  function company() { return App.state.company || {}; }
  function sellsGoods() { return company().has_goods !== 0; }
  function sellsServices() { return company().has_services === 1 || company().has_services === true; }

  /* A dropdown with an "add a new one" entry at the bottom. */

  function selectWithAdd(items, value, addLabel, onAdd) {
    var node = el("select");

    function fill(list, chosen) {
      UI.clear(node);
      node.appendChild(el("option", { value: "", text: "Not set" }));
      list.forEach(function (item) {
        node.appendChild(el("option", {
          value: item.value, text: item.label,
          selected: String(item.value) === String(chosen)
        }));
      });
      node.appendChild(el("option", { value: "__add", text: "+  " + addLabel }));
    }

    fill(items, value);
    var previous = node.value;
    node.addEventListener("change", function () {
      if (node.value !== "__add") { previous = node.value; return; }
      node.value = previous;
      onAdd(function (made) {
        items = items.concat([{ value: made.id, label: made.label }]);
        fill(items, made.id);
        previous = String(made.id);
      });
    });
    return node;
  }

  /* Small lists */

  function openUnitForm(typed, done) {
    var name = el("input", { type: "text", value: typed || "" });
    var symbol = el("input", { type: "text", placeholder: "kg, pcs, ft" });
    var decimals = UI.select([
      { value: "0", label: "Whole numbers only, such as pieces" },
      { value: "2", label: "Two decimal places" },
      { value: "3", label: "Three decimal places, such as kilograms" }
    ], "0");
    UI.modal("New unit", el("div", {}, [
      UI.field("Name", name, "For example Kilogram"),
      UI.field("Short symbol", symbol, "What appears on the invoice"),
      UI.field("How precisely is it counted", decimals)
    ]), [
      { label: "Cancel" },
      { label: "Add the unit", kind: "primary", action: function () {
        if (!name.value.trim() || !symbol.value.trim()) {
          UI.flash("A unit needs a name and a symbol.", "bad");
          return false;
        }
        return api("/api/units/create", { body: {
          name: name.value.trim(), symbol: symbol.value.trim(), decimals: +decimals.value
        }}).then(function (made) {
          UI.flash("Unit added.", "good");
          return App.loadLookups().then(function () {
            if (done) { done({ id: made.id, label: made.name + " (" + made.symbol + ")" }); }
          });
        });
      }}
    ], { slim: true });
  }

  function openItemGroupForm(typed, done) {
    var name = el("input", { type: "text", value: typed || "" });
    UI.modal("New item group", el("div", {}, [
      UI.field("Group name", name, "For example Cement and Concrete")
    ]), [
      { label: "Cancel" },
      { label: "Add the group", kind: "primary", action: function () {
        if (!name.value.trim()) { UI.flash("Give the group a name.", "bad"); return false; }
        return api("/api/item-groups/create", { body: { name: name.value.trim() } }).then(function (made) {
          UI.flash("Group added.", "good");
          return App.loadLookups().then(function () {
            if (done) { done({ id: made.id, label: made.name }); }
          });
        });
      }}
    ], { slim: true });
  }

  /* Parties */

  App.register("parties", function (page) {
    var search = el("input", { type: "search", placeholder: "Search by name, PAN or phone" });
    var typeFilter = UI.select([
      { value: "", label: "Everyone" },
      { value: "customer", label: "Customers" },
      { value: "supplier", label: "Suppliers" }
    ], "");
    var listBox = el("div");

    function load() {
      return api("/api/parties", { query: {
        q: search.value.trim(), type: typeFilter.value, with_balance: "1", all: "1"
      }}).then(function (data) {
        var owed = 0, owing = 0;
        var rows = data.rows.map(function (party) {
          var balance = party.balance || 0;
          if (balance > 0) { owed += balance; } else { owing -= balance; }
          return el("tr.clickable", { onclick: function () { openPartyForm(party); } }, [
            el("td", { text: party.code }),
            el("td", {}, [
              el("div", { text: party.name }),
            ]),
            el("td", {}, [el("span.pill" + (party.party_type === "supplier" ? "" : ".brand"),
              { text: party.party_type })]),
            el("td", { text: party.pan || "" }),
            el("td", { text: party.mobile || party.phone || "" }),
            el("td.num", { text: balance === 0 ? "" : UI.rs(Math.abs(balance)) }),
            el("td.muted", { text: balance === 0 ? "" : (balance > 0 ? "Dr" : "Cr"),
                             style: "font-size:.74rem" }),
            el("td", {}, [party.active ? null : el("span.pill.bad", { text: "off" })])
          ]);
        });
        UI.clear(listBox);
        listBox.appendChild(el("div.grid.three", { style: "margin-bottom:.9rem" }, [
          tile("On the list", String(data.rows.length), "Customers and suppliers"),
          tile("Owed to you", UI.rs(owed), "Across every customer"),
          tile("Owed by you", UI.rs(owing), "Across every supplier")
        ]));
        listBox.appendChild(UI.table(
          ["Code", "Name", "Type", "PAN", "Phone", { label: "Balance", num: true }, "", ""],
          rows, null, { tall: true,
            emptyText: "No customers or suppliers yet. Add the first one to begin." }));
      });
    }

    search.addEventListener("input", function () { load(); });
    typeFilter.addEventListener("change", load);

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [
        el("h2", { text: "Customers and suppliers" }),
        el("div.row", {}, [
          el("button.secondary", { text: "Add a supplier",
            onclick: function () { openPartyForm(null, "supplier"); } }),
          el("button.primary", { text: "Add a customer",
            onclick: function () { openPartyForm(null, "customer"); } })
        ])
      ]),
      el("div.toolbar", {}, [
        el("div.field", { style: "flex:1 1 280px;margin:0" }, [search]),
        el("div.field", { style: "flex:0 0 165px;margin:0" }, [typeFilter])
      ]),
      listBox
    ]));
    return load();
  });

  function tile(label, value, note, kind) {
    return el("div.tile" + (kind ? "." + kind : ""), {}, [
      el("div.tile-label", { text: label }),
      el("div.tile-value", { text: value }),
      note ? el("div.tile-note", { text: note }) : null
    ]);
  }

  function openPartyForm(party, defaultType, options) {
    options = options || {};
    var isNew = !party;
    var name = el("input", { type: "text", value: party ? party.name : (options.presetName || "") });
    var type = UI.select([
      { value: "customer", label: "Customer, buys from you" },
      { value: "supplier", label: "Supplier, you buy from them" },
      { value: "both", label: "Both, buys and sells" },
      { value: "employee", label: "Employee" },
      { value: "other", label: "Other" }
    ], party ? party.party_type : (defaultType || "customer"));
    var pan = el("input", { type: "text", maxlength: "9", inputmode: "numeric",
                            value: party ? party.pan : "" });
    var vatBox = el("input", { type: "checkbox" });
    vatBox.checked = party ? !!party.vat_registered : false;
    pan.addEventListener("input", function () {
      // A nine digit PAN in Nepal usually means the party is VAT registered.
      if (pan.value.trim().length === 9 && !party) { vatBox.checked = true; }
    });
    var contact = el("input", { type: "text", value: party ? party.contact_person : "" });
    var address = el("input", { type: "text", value: party ? party.address : "" });
    var city = el("input", { type: "text", value: party ? party.city : "" });
    var district = el("input", { type: "text", value: party ? party.district : "" });
    var phone = el("input", { type: "text", value: party ? party.phone : "" });
    var mobile = el("input", { type: "text", value: party ? party.mobile : "" });
    var email = el("input", { type: "text", value: party ? party.email : "" });
    var creditDays = el("input", { type: "number", min: "0",
                                   value: party ? party.credit_days : 0 });
    var creditLimit = UI.amountInput(party && party.credit_limit_paisa
      ? (party.credit_limit_paisa / 100) : "");
    var opening = UI.amountInput("");
    var openingSide = UI.select([
      { value: "dr", label: "Debit, they owe you" },
      { value: "cr", label: "Credit, you owe them" }
    ], (defaultType || (party && party.party_type)) === "supplier" ? "cr" : "dr");
    var active = el("input", { type: "checkbox" });
    active.checked = party ? !!party.active : true;
    var notes = el("textarea", { rows: "2" });
    notes.value = party ? (party.notes || "") : "";

    type.addEventListener("change", function () {
      openingSide.value = type.value === "supplier" ? "cr" : "dr";
    });

    var body = el("div", {}, [
      UI.field("Name", name),
      el("div.row", {}, [
        UI.field("They are a", type),
        UI.field("PAN", pan, "Nine digits, leave blank if none"),
        UI.field("Registered for VAT", el("label.check", {}, [vatBox, el("span", { text: "Yes" })]))
      ]),
      el("div.row", {}, [UI.field("Contact person", contact), UI.field("Phone", phone),
                         UI.field("Mobile", mobile)]),
      el("div.row", {}, [UI.field("Email", email), UI.field("Address", address)]),
      el("div.row", {}, [UI.field("City", city), UI.field("District", district)]),
      el("div.row", {}, [UI.field("Credit days", creditDays), UI.field("Credit limit", creditLimit)]),
      isNew ? el("div.row", {}, [
        UI.field("Opening balance", opening, "What was already owed when the books began"),
        UI.field("Which side", openingSide)
      ]) : null,
      UI.field("Notes", notes),
      isNew ? null : UI.field("Active", el("label.check", {}, [active, el("span", { text: "Can be used on vouchers" })]))
    ]);

    var buttons = [{ label: "Cancel" }];
    if (!isNew) {
      buttons.push({ label: "Open ledger", action: function () {
        UI.closeModal(); Reports.openLedger(party.account_id); return false;
      }});
    }
    buttons.push({ label: isNew ? "Add" : "Save changes", kind: "primary", action: function () {
      var payload = {
        name: name.value.trim(),
        pan: pan.value.trim(), vat_registered: vatBox.checked ? 1 : 0,
        contact_person: contact.value.trim(), address: address.value.trim(),
        city: city.value.trim(), district: district.value.trim(),
        phone: phone.value.trim(), mobile: mobile.value.trim(), email: email.value.trim(),
        credit_days: +creditDays.value || 0, credit_limit: creditLimit.value || 0,
        notes: notes.value.trim(), party_type: type.value
      };
      if (!payload.name) { UI.flash("Give the party a name.", "bad"); return false; }
      if (isNew) {
        payload.opening = opening.value || 0;
        payload.opening_side = openingSide.value;
        return api("/api/parties/create", { body: payload }).then(function (made) {
          UI.flash(payload.name + " added.", "good");
          if (options.onSaved) {
            return api("/api/parties/" + made.id).then(function (data) {
              options.onSaved(data.party);
            });
          }
          App.go("parties");
        });
      }
      payload.active = active.checked ? 1 : 0;
      return api("/api/parties/" + party.id + "/update", { body: payload }).then(function () {
        UI.flash("Saved.", "good");
        if (options.onSaved) { options.onSaved(party); } else { App.go("parties"); }
      });
    }});

    UI.modal(isNew ? "New party" : party.name, body, buttons, { wide: true });
  }

  /* Items and services */

  App.register("items", function (page) {
    var search = el("input", { type: "search", placeholder: "Search by name, code or barcode" });
    var typeFilter = UI.select([
      { value: "", label: "Everything" },
      { value: "goods", label: "Goods" },
      { value: "service", label: "Services" }
    ], "");
    var listBox = el("div");

    function load() {
      return api("/api/items", { query: {
        q: search.value.trim(), type: typeFilter.value, with_stock: "1", all: "1"
      }}).then(function (data) {
        var stockValue = 0, lowCount = 0;
        var rows = data.rows.map(function (item) {
          if (item.maintain_stock) { stockValue += item.stock_value || 0; }
          var low = item.reorder_qty > 0 && (item.stock_qty || 0) <= item.reorder_qty;
          if (low && item.maintain_stock) { lowCount += 1; }
          return el("tr.clickable", { onclick: function () { openItemForm(item); } }, [
            el("td", { text: item.code }),
            el("td", {}, [
              el("div", {}, [
                el("span", { text: item.name }),
                low && item.maintain_stock
                  ? el("span.pill.warn", { text: "low", style: "margin-left:.4rem" }) : null
              ]),
              item.group_name ? el("div.muted", { text: item.group_name, style: "font-size:.74rem" }) : null
            ]),
            el("td", {}, [el("span.pill" + (item.item_type === "service" ? ".brand" : ".good"),
              { text: item.item_type })]),
            el("td", { text: item.unit_symbol || "" }),
            el("td.num", { text: UI.rs(item.purchase_rate_paisa, { blankZero: true }) }),
            el("td.num", { text: UI.rs(item.sale_rate_paisa, { blankZero: true }) }),
            el("td.num", { text: item.maintain_stock ? NP.formatQty(item.stock_qty) : "" }),
            el("td.num", { text: item.maintain_stock
              ? UI.rs(item.stock_value, { blankZero: true }) : "" }),
            el("td", {}, [item.active ? null : el("span.pill.bad", { text: "off" })])
          ]);
        });
        UI.clear(listBox);
        if (sellsGoods()) {
          listBox.appendChild(el("div.grid.three", { style: "margin-bottom:.9rem" }, [
            tile("On the list", String(data.rows.length), "Items and services"),
            tile("Stock value", UI.rs(stockValue), "At weighted average cost"),
            tile("Running low", String(lowCount), "At or below the reorder level",
                 lowCount ? "bad" : "good")
          ]));
        }
        listBox.appendChild(UI.table([
          "Code", "Name", "Type", "Unit",
          { label: "Buy rate", num: true }, { label: "Sell rate", num: true },
          { label: "In stock", num: true }, { label: "Stock value", num: true }, ""
        ], rows, null, { tall: true,
          emptyText: "Nothing on the list yet. Add the things you buy and sell." }));
      });
    }

    search.addEventListener("input", function () { load(); });
    typeFilter.addEventListener("change", load);

    var actions = el("div.row", {}, [
      sellsServices() ? el("button" + (sellsGoods() ? ".secondary" : ".primary"), {
        text: "Add a service", onclick: function () { openItemForm(null, "service"); } }) : null,
      sellsGoods() ? el("button.primary", {
        text: "Add an item", onclick: function () { openItemForm(null, "goods"); } }) : null
    ]);

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [
        el("h2", { text: sellsGoods() && sellsServices() ? "Items and services"
                   : sellsGoods() ? "Items" : "Services" }),
        actions
      ]),
      el("div.toolbar", {}, [
        el("div.field", { style: "flex:1 1 280px;margin:0" }, [search]),
        sellsGoods() && sellsServices()
          ? el("div.field", { style: "flex:0 0 155px;margin:0" }, [typeFilter]) : null
      ]),
      listBox
    ]));
    return load();
  });

  function openItemForm(item, defaultType, options) {
    options = options || {};
    var isNew = !item;
    var lookups = App.state.lookups || { units: [], item_groups: [] };
    var startType = item ? item.item_type
      : (defaultType || (sellsGoods() ? "goods" : "service"));

    var name = el("input", { type: "text", value: item ? item.name : (options.presetName || "") });
    var code = el("input", { type: "text", value: item ? item.code : "",
                             placeholder: "left blank, one is made for you" });
    var barcode = el("input", { type: "text", value: item ? item.barcode : "" });

    var typeChoices = [];
    if (sellsGoods() || startType === "goods") {
      typeChoices.push({ value: "goods", label: "Goods, counted in stock" });
    }
    if (sellsServices() || startType === "service") {
      typeChoices.push({ value: "service", label: "Service, nothing to count" });
    }
    if (!typeChoices.length) { typeChoices = [{ value: "goods", label: "Goods" }]; }
    var type = UI.select(typeChoices, startType);

    var group = selectWithAdd(
      lookups.item_groups.map(function (g) { return { value: g.id, label: g.name }; }),
      item ? item.group_id : "", "Add a new group",
      function (done) { openItemGroupForm("", done); });

    var unit = selectWithAdd(
      lookups.units.map(function (u) { return { value: u.id, label: u.name + " (" + u.symbol + ")" }; }),
      item ? item.unit_id : (defaultUnitId(lookups, startType)), "Add a new unit",
      function (done) { openUnitForm("", done); });

    var hsCode = el("input", { type: "text", value: item ? item.hs_code : "" });
    var vatBox = el("input", { type: "checkbox" });
    vatBox.checked = item ? !!item.vat_applicable : (company().vat_registered ? true : false);
    var vatRate = el("input", { type: "number", step: "0.01",
      value: item ? (item.vat_rate_bp / 100) : 13 });
    vatBox.addEventListener("change", function () {
      vatRate.disabled = !vatBox.checked;
      if (!vatBox.checked) { vatRate.value = 0; }
      else if (!+vatRate.value) { vatRate.value = 13; }
    });
    vatRate.disabled = !vatBox.checked;

    var buyRate = UI.amountInput(item ? item.purchase_rate_paisa / 100 : "");
    var sellRate = UI.amountInput(item ? item.sale_rate_paisa / 100 : "");
    var mrp = UI.amountInput(item && item.mrp_paisa ? item.mrp_paisa / 100 : "");
    var reorder = UI.amountInput(item && item.reorder_qty ? item.reorder_qty / 1000 : "");
    var openingQty = UI.amountInput("");
    var openingRate = UI.amountInput("");
    var active = el("input", { type: "checkbox" });
    active.checked = item ? !!item.active : true;
    var notes = el("textarea", { rows: "2" });
    notes.value = item ? (item.notes || "") : "";

    var stockBlock = el("div", {}, [
      el("div.row", {}, [
        UI.field("Warn below this quantity", reorder, "Leave blank for no warning"),
        isNew ? UI.field("Opening quantity", openingQty) : null,
        isNew ? UI.field("Opening cost per unit", openingRate, "Cost, not selling price") : null
      ])
    ]);

    function applyType() {
      var goods = type.value === "goods";
      stockBlock.style.display = goods ? "" : "none";
      unit.parentNode.style.display = goods ? "" : "none";
      hsCode.parentNode.style.display = goods ? "" : "none";
      barcode.parentNode.style.display = goods ? "" : "none";
    }

    // A shop that only sells goods has no use for a dropdown with one entry.
    var typeField = UI.field("This is", type);
    if (typeChoices.length < 2) { typeField.style.display = "none"; }

    var body = el("div", {}, [
      UI.field("Name", name),
      el("div.row", {}, [
        typeField,
        UI.field("Group", group),
        UI.field("Code", code)
      ]),
      el("div.row", {}, [
        UI.field("Unit", unit),
        UI.field("Barcode", barcode),
        UI.field("Harmonised code", hsCode, "For customs, optional")
      ]),
      el("div.row", {}, [
        UI.field("VAT applies", el("label.check", {}, [vatBox, el("span", { text: "Charge VAT on this" })])),
        UI.field("VAT rate percent", vatRate),
        UI.field("Purchase rate", buyRate),
        UI.field("Selling rate", sellRate)
      ]),
      el("div.row", {}, [UI.field("Maximum retail price", mrp, "Printed on the pack, optional")]),
      stockBlock,
      UI.field("Notes", notes),
      isNew ? null : UI.field("Active",
        el("label.check", {}, [active, el("span", { text: "Can be used on vouchers" })]))
    ]);

    type.addEventListener("change", applyType);
    applyType();

    var buttons = [{ label: "Cancel" }];
    if (!isNew && item.maintain_stock) {
      buttons.push({ label: "Stock movement", action: function () {
        UI.closeModal(); Reports.openItemMovement(item.id); return false;
      }});
    }
    buttons.push({ label: isNew ? "Add" : "Save changes", kind: "primary", action: function () {
      var payload = {
        name: name.value.trim(),
        barcode: barcode.value.trim(), group_id: group.value || null,
        unit_id: unit.value || null, hs_code: hsCode.value.trim(),
        vat_applicable: vatBox.checked ? 1 : 0,
        vat_rate_bp: vatBox.checked ? Math.round((+vatRate.value || 0) * 100) : 0,
        purchase_rate: buyRate.value || 0, sale_rate: sellRate.value || 0,
        mrp: mrp.value || 0, reorder_qty: reorder.value || 0,
        notes: notes.value.trim()
      };
      if (!payload.name) { UI.flash("Give it a name.", "bad"); return false; }
      if (isNew) {
        payload.code = code.value.trim();
        payload.item_type = type.value;
        payload.maintain_stock = type.value === "goods" ? 1 : 0;
        payload.opening_qty = openingQty.value || 0;
        payload.opening_rate = openingRate.value || 0;
        return api("/api/items/create", { body: payload }).then(function (made) {
          UI.flash(payload.name + " added.", "good");
          if (options.onSaved) {
            return api("/api/items/" + made.id).then(function (data) { options.onSaved(data.item); });
          }
          App.go("items");
        });
      }
      payload.active = active.checked ? 1 : 0;
      return api("/api/items/" + item.id + "/update", { body: payload }).then(function () {
        UI.flash("Saved.", "good");
        if (options.onSaved) { options.onSaved(item); } else { App.go("items"); }
      });
    }});

    UI.modal(isNew ? (startType === "service" ? "New service" : "New item") : item.name,
             body, buttons, { wide: true });
  }

  function defaultUnitId(lookups, type) {
    var wanted = type === "service" ? "job" : "pcs";
    var found = (lookups.units || []).filter(function (u) { return u.symbol === wanted; })[0];
    return found ? found.id : "";
  }

  /* Chart of accounts */

  App.register("accounts", function (page) {
    var search = el("input", { type: "search", placeholder: "Search a ledger by name or code" });
    var listBox = el("div");

    function load() {
      return api("/api/accounts", { query: { q: search.value.trim(), with_balance: "1", all: "1" } })
        .then(function (data) {
          var currentGroup = null;
          var rows = [];
          data.rows.forEach(function (account) {
            if (account.group_code !== currentGroup) {
              currentGroup = account.group_code;
              rows.push(el("tr.group-row", {}, [
                el("td", { text: account.group_code }),
                el("td", { colspan: "4", text: account.group_name })
              ]));
            }
            var balance = account.balance || 0;
            rows.push(el("tr.clickable", { onclick: function () { openAccountForm(account); } }, [
              el("td", { text: account.code }),
              el("td.indent", {}, [
                el("span", { text: account.name }),
                account.is_system ? el("span.pill", { text: "system", style: "margin-left:.4rem" }) : null,
                account.active ? null : el("span.pill.bad", { text: "off", style: "margin-left:.4rem" })
              ]),
              el("td.muted", { text: account.account_kind === "general" ? "" : account.account_kind,
                               style: "font-size:.74rem" }),
              el("td.num", { text: balance === 0 ? "" : UI.rs(Math.abs(balance)) }),
              el("td.muted", { text: balance === 0 ? "" : (balance > 0 ? "Dr" : "Cr"),
                               style: "font-size:.74rem" })
            ]));
          });
          UI.clear(listBox).appendChild(UI.table(
            ["Code", "Ledger", "Kind", { label: "Balance", num: true }, ""],
            rows, null, { tall: true }));
        });
    }

    search.addEventListener("input", function () { load(); });

    page.appendChild(el("div.card", {}, [
      el("div.card-head", {}, [
        el("h2", { text: "Chart of accounts" }),
        el("button.primary", { text: "Add a ledger", onclick: function () { openAccountForm(null); } })
      ]),
      el("p.card-note", { text: "Set up when the company was created, following the way NFRS and NAS statements are presented in Nepal. Add to it freely. Ledgers marked as system are posted to by the software itself and cannot be removed." }),
      el("div.toolbar", {}, [el("div.field", { style: "flex:1 1 300px;margin:0" }, [search])]),
      listBox
    ]));
    return load();
  });

  function openAccountForm(account, options) {
    options = options || {};
    var isNew = !account;
    var lookups = App.state.lookups || { account_groups: [] };
    var name = el("input", { type: "text",
      value: account ? account.name : (options.presetName || "") });
    var code = el("input", { type: "text", value: account ? account.code : "" });
    var group = UI.select(lookups.account_groups.map(function (g) {
      return { value: g.id, label: g.code + "   " + g.name };
    }), account ? account.group_id : (options.groupId || ""));
    var kind = UI.select([
      { value: "general", label: "General ledger" },
      { value: "cash", label: "Cash" },
      { value: "bank", label: "Bank" },
      { value: "fixed_asset", label: "Fixed asset" },
      { value: "capital", label: "Capital or reserve" }
    ], account ? account.account_kind : "general");
    var bankName = el("input", { type: "text", value: account ? account.bank_name : "" });
    var bankAccount = el("input", { type: "text", value: account ? account.bank_account_no : "" });
    var bankBranch = el("input", { type: "text", value: account ? account.bank_branch : "" });
    var opening = UI.amountInput(account && account.opening_paisa
      ? Math.abs(account.opening_paisa) / 100 : "");
    var openingSide = UI.select([{ value: "dr", label: "Debit" }, { value: "cr", label: "Credit" }],
      account && account.opening_paisa < 0 ? "cr" : "dr");
    var active = el("input", { type: "checkbox" });
    active.checked = account ? !!account.active : true;
    var notes = el("textarea", { rows: "2" });
    notes.value = account ? (account.notes || "") : "";

    var bankBlock = el("div.row", {}, [
      UI.field("Bank name", bankName), UI.field("Account number", bankAccount),
      UI.field("Branch", bankBranch)
    ]);
    function applyKind() {
      bankBlock.style.display = kind.value === "bank" ? "" : "none";
    }
    kind.addEventListener("change", applyKind);
    applyKind();

    var body = el("div", {}, [
      UI.field("Ledger name", name),
      el("div.row", {}, [
        UI.field("Sits under", group),
        UI.field("Kind", kind),
        UI.field("Code", code, "Leave blank and one is made for you")
      ]),
      bankBlock,
      el("div.row", {}, [UI.field("Opening balance", opening), UI.field("Side", openingSide)]),
      UI.field("Notes", notes),
      isNew ? null : UI.field("Active",
        el("label.check", {}, [active, el("span", { text: "Can be used on vouchers" })]))
    ]);

    var buttons = [{ label: "Cancel" }];
    if (!isNew) {
      buttons.push({ label: "Open ledger", action: function () {
        UI.closeModal(); Reports.openLedger(account.id); return false;
      }});
      if (!account.is_system) {
        buttons.push({ label: "Delete", kind: "danger", action: function () {
          return api("/api/accounts/" + account.id + "/delete", { body: {} })
            .then(function () { UI.flash("Deleted.", "good"); App.go("accounts"); });
        }});
      }
    }
    buttons.push({ label: isNew ? "Add" : "Save changes", kind: "primary", action: function () {
      var payload = {
        name: name.value.trim(),
        group_id: +group.value, account_kind: kind.value,
        bank_name: bankName.value.trim(), bank_account_no: bankAccount.value.trim(),
        bank_branch: bankBranch.value.trim(), notes: notes.value.trim(),
        opening: opening.value || 0, opening_side: openingSide.value
      };
      if (!payload.name) { UI.flash("Give the ledger a name.", "bad"); return false; }
      if (!payload.group_id) { UI.flash("Choose the group it sits under.", "bad"); return false; }
      if (isNew) {
        payload.code = code.value.trim();
        return api("/api/accounts/create", { body: payload }).then(function (made) {
          UI.flash("Ledger added.", "good");
          if (options.onSaved) {
            return api("/api/accounts/" + made.id).then(function (data) {
              options.onSaved(data.account);
            });
          }
          App.go("accounts");
        });
      }
      payload.active = active.checked ? 1 : 0;
      return api("/api/accounts/" + account.id + "/update", { body: payload }).then(function () {
        UI.flash("Saved.", "good");
        if (options.onSaved) { options.onSaved(account); } else { App.go("accounts"); }
      });
    }});

    UI.modal(isNew ? "New ledger" : account.name, body, buttons, { wide: true });
  }

  return {
    openPartyForm: openPartyForm,
    openItemForm: openItemForm,
    openAccountForm: openAccountForm,
    openUnitForm: openUnitForm,
    openItemGroupForm: openItemGroupForm,
    selectWithAdd: selectWithAdd,
    sellsGoods: sellsGoods,
    sellsServices: sellsServices
  };
}());
