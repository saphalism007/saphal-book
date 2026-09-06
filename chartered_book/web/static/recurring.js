/* The entries that come round again.

   Rent, salary, a loan instalment. The month one gets forgotten is the month
   the accounts are wrong, so what is due is shown rather than remembered.

   Nothing posts itself. A voucher that appeared without anybody agreeing to it
   is worse than one that was forgotten, because a forgotten one gets noticed
   and an invented one does not. What this removes is the remembering. */

var Recurring = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  App.register("recurring", function (page) {
    var box = el("div");

    function load() {
      return api("/api/recurring").then(draw);
    }

    function draw(data) {
      UI.clear(box);

      var owed = data.due_total;
      box.appendChild(el("div.card", {}, [
        el("div.card-head", {}, [
          el("h2", { text: owed
            ? (owed === 1 ? "One entry is due" : owed + " entries are due")
            : "Nothing is due" }),
          el("button.primary", { text: "Set up a new one",
                                 onclick: function () { editor(null); } })
        ]),
        el("p.card-note", { text: owed
          ? "Each one is posted on its own, so what goes into the books is seen "
            + "before it goes in."
          : "Rent, salary, a loan instalment. Set one up and it will be offered "
            + "each time it comes round, rather than needing to be remembered." })
      ]));

      (data.rows || []).forEach(function (pattern) {
        box.appendChild(card(pattern));
      });

      if (!(data.rows || []).length) {
        box.appendChild(el("div.empty", {}, [
          el("strong", { text: "Nothing set up yet" }),
          el("span", { text: "The entries that are the same every month belong here." })
        ]));
      }
    }

    function card(pattern) {
      var every = { month: "Every month", quarter: "Every quarter",
                    year: "Every year" }[pattern.every] || pattern.every;
      var head = el("div.card-head", {}, [
        el("h2", {}, [
          el("span", { text: pattern.name }),
          pattern.active ? null : el("span.pill.warn", { text: "switched off" })
        ]),
        el("div.row", {}, [
          el("button.secondary", { text: "Change",
                                   onclick: function () { editor(pattern); } }),
          App.state.permissions["voucher.cancel"]
            ? el("button.secondary", { text: "Remove", onclick: function () {
                UI.confirmAction("Remove " + pattern.name,
                  "The entries it has already made stay in the books. Those are real "
                  + "entries and have nothing to do with whether the pattern goes on.",
                  function () {
                    return api("/api/recurring/remove", { body: { id: pattern.id } })
                      .then(load)
                      .catch(function (error) { UI.flash(error.message, "bad"); });
                  }, "Remove it");
              }})
            : null
        ])
      ]);

      var lines = UI.table(
        ["Ledger", { label: "Debit", num: true }, { label: "Credit", num: true }],
        pattern.lines.map(function (line) {
          return el("tr", {}, [
            el("td", { text: line.account_code + "  " + line.account_name }),
            el("td.num", { text: line.dr_paisa ? UI.rs(line.dr_paisa) : "" }),
            el("td.num", { text: line.cr_paisa ? UI.rs(line.cr_paisa) : "" })
          ]);
        }), null, {});

      var due = el("div");
      if (pattern.due_count) {
        due.appendChild(el("div.doc-subtitle", { text: pattern.due_count === 1
          ? "One is due" : pattern.due_count + " are due" }));
        pattern.due.forEach(function (one) {
          due.appendChild(el("div.due-row", {}, [
            el("div", {}, [
              el("span.due-when", { text: UI.bs(one.date_ad, "long") }),
              el("span.muted", { text: "  " + one.date_ad })
            ]),
            el("button.secondary", { text: "Post this one", onclick: function (event) {
              var button = event.currentTarget;
              button.disabled = true;
              return api("/api/recurring/post",
                         { body: { id: pattern.id, due_bs: one.due_bs } })
                .then(function (result) {
                  UI.flash("Posted " + result.voucher.voucher.number + ".", "good");
                  return load();
                })
                .catch(function (error) {
                  button.disabled = false;
                  UI.flash(error.message, "bad");
                });
            }})
          ]));
        });
      } else if (pattern.active) {
        due.appendChild(el("p.card-note", { text: "Nothing due at the moment." }));
      }

      return el("div.card", {}, [
        head,
        el("p.card-note", { text: every + ", from "
          + UI.bs(bsToIso(pattern.starts_bs), "long")
          + (pattern.ends_bs ? " until " + UI.bs(bsToIso(pattern.ends_bs), "long") : "")
          + (pattern.narration ? "  ·  " + pattern.narration : "") }),
        lines,
        due
      ]);
    }

    /* Setting one up */

    function editor(existing) {
      var name = el("input", { type: "text", value: existing ? existing.name : "",
                               placeholder: "Shop rent" });
      var every = UI.select([
        { value: "month", label: "Every month" },
        { value: "quarter", label: "Every quarter" },
        { value: "year", label: "Every year" }
      ], existing ? existing.every : "month");
      var starts = UI.dateField(existing ? bsToIso(existing.starts_bs) : NP.todayIso());
      var ends = UI.dateField(existing && existing.ends_bs
                              ? bsToIso(existing.ends_bs) : "");
      var narration = el("input", { type: "text",
        value: existing ? existing.narration : "",
        placeholder: "What this entry is for" });

      var lines = (existing && existing.lines.length)
        ? existing.lines.map(function (line) {
            return { accountId: line.account_id, name: line.account_name,
                     dr: line.dr_paisa ? UI.rs(line.dr_paisa, { plain: true }) : "",
                     cr: line.cr_paisa ? UI.rs(line.cr_paisa, { plain: true }) : "" };
          })
        : [{ accountId: null, name: "", dr: "", cr: "" },
           { accountId: null, name: "", dr: "", cr: "" }];

      var grid = el("tbody");
      function drawLines() {
        UI.clear(grid);
        lines.forEach(function (line, index) {
          var account = el("input", { type: "text", value: line.name,
                                      placeholder: "Ledger" });
          UI.attachPicker(account, function (term) {
            return api("/api/accounts", { query: { q: term } })
              .then(function (d) { return d.rows; });
          }, function (chosen) {
            line.accountId = chosen.id;
            line.name = chosen.name;
            account.value = chosen.name;
          }, function (a) { return { main: a.name, side: a.group_name }; });

          var dr = UI.amountInput(line.dr, { onChange: function (v) { line.dr = v; } });
          var cr = UI.amountInput(line.cr, { onChange: function (v) { line.cr = v; } });
          dr.addEventListener("input", function () { line.dr = dr.value; });
          cr.addEventListener("input", function () { line.cr = cr.value; });

          grid.appendChild(el("tr", {}, [
            el("td", {}, [account]),
            el("td", {}, [dr]),
            el("td", {}, [cr]),
            el("td.no-print", {}, [el("button.link", { text: "×", onclick: function () {
              lines.splice(index, 1);
              if (lines.length < 2) { lines.push({ accountId: null, name: "", dr: "", cr: "" }); }
              drawLines();
            }})])
          ]));
        });
      }
      drawLines();

      var body = el("div", {}, [
        el("div.row", {}, [
          UI.field("Name", name),
          UI.field("How often", every)
        ]),
        el("div.row", {}, [
          UI.field("Starts", starts),
          UI.field("Ends, if it does", ends),
          UI.field("Narration", narration)
        ]),
        el("div.card-note", { text: "The same entry every time. A rent that changes is "
          + "a new pattern rather than a guess, so the amounts are fixed here." }),
        el("div.table-wrap", {}, [el("table", {}, [
          el("thead", {}, [el("tr", {}, [
            el("th", { text: "Ledger" }), el("th.num", { text: "Debit" }),
            el("th.num", { text: "Credit" }), el("th")
          ])]),
          grid
        ])]),
        el("button.secondary.no-print", { text: "Another line", onclick: function () {
          lines.push({ accountId: null, name: "", dr: "", cr: "" });
          drawLines();
        }})
      ]);

      UI.modal(existing ? "Change " + existing.name : "An entry that comes round again",
        body, [
        { label: "Cancel" },
        { label: existing ? "Save it" : "Set it up", kind: "primary", action: function () {
            var payload = {
              name: name.value, every: every.value,
              starts_bs: isoToBs(starts.getIso()),
              ends_bs: ends.getIso() ? isoToBs(ends.getIso()) : "",
              narration: narration.value, active: 1,
              lines: lines.filter(function (l) { return l.accountId; })
                          .map(function (l) {
                            return { account_id: l.accountId, dr: l.dr || 0, cr: l.cr || 0 };
                          })
            };
            var where = existing ? "/api/recurring/update" : "/api/recurring/create";
            if (existing) { payload.id = existing.id; }
            return api(where, { body: payload })
              .then(function () {
                UI.flash(existing ? "Saved." : "Set up.", "good");
                return load();
              })
              .catch(function (error) { UI.flash(error.message, "bad"); return false; });
          } }
      ], { wide: true });
    }

    // The engine keeps these dates as Bikram Sambat text; the date field works
    // in ordinary dates. One conversion in each direction, in one place.
    function bsToIso(bs) {
      if (!bs) { return ""; }
      var bits = String(bs).split("-");
      var day = +bits[2];
      // A pattern can be kept on a day some months do not have, so walk back
      // to one that exists rather than showing nothing.
      while (day > 27) {
        var iso = NP.bsToAd(+bits[0], +bits[1], day);
        if (iso) { return iso; }
        day -= 1;
      }
      return NP.bsToAd(+bits[0], +bits[1], day) || "";
    }
    function isoToBs(iso) {
      var bs = iso ? NP.adToBs(iso) : null;
      if (!bs) { return ""; }
      return bs.year + "-" + String(bs.month).padStart(2, "0")
             + "-" + String(bs.day).padStart(2, "0");
    }

    page.appendChild(box);
    return load();
  });

  return {};
}());
