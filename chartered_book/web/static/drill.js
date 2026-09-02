/* Drilling into a figure.

   Every total in a statement can be opened. A statement line opens the group
   inside it, a group opens its sub groups and ledgers, a ledger opens month by
   month, a month opens the vouchers behind it, and a voucher opens itself.
   The trail across the top says where you are and takes you back a step. */

var Drill = (function () {
  "use strict";

  var el = UI.el, api = UI.api;

  var stack = [];
  var host = null;
  var period = { from_ad: null, to_ad: null };

  function setPeriod(from_ad, to_ad) {
    period = { from_ad: from_ad, to_ad: to_ad };
  }

  function mount(node) {
    host = node;
  }

  function start(level, from_ad, to_ad) {
    if (from_ad) { setPeriod(from_ad, to_ad); }
    stack = [level];
    render();
    reveal();
  }

  function push(level) {
    stack.push(level);
    render();
    reveal();
  }

  function reveal() {
    // The drill sits under the report, which on a full statement can be a long
    // way down. Without this the click looks as though it did nothing.
    if (!host || !host.scrollIntoView) { return; }
    setTimeout(function () {
      host.scrollIntoView({ block: "start", behavior: "smooth" });
    }, 60);
  }

  function popTo(index) {
    stack = stack.slice(0, index + 1);
    render();
  }

  function close() {
    stack = [];
    if (host) { UI.clear(host); }
  }

  function depth() { return stack.length; }

  function breadcrumb() {
    var bar = el("div.crumbs");
    stack.forEach(function (level, index) {
      if (index) { bar.appendChild(el("span.crumb-sep", { text: "›" })); }
      var last = index === stack.length - 1;
      bar.appendChild(last
        ? el("span.crumb.here", { text: level.label })
        : el("button.crumb", { text: level.label,
                               onclick: function () { popTo(index); } }));
    });
    if (stack.length > 1) {
      bar.appendChild(el("button.link-button.no-print", {
        style: "margin-left:auto", text: "Back",
        onclick: function () { popTo(stack.length - 2); }
      }));
    }
    return bar;
  }

  function render() {
    if (!host) { return; }
    UI.clear(host);
    if (!stack.length) { return; }
    var level = stack[stack.length - 1];
    host.appendChild(breadcrumb());
    var body = el("div");
    host.appendChild(body);
    body.appendChild(el("div.empty", { text: "Opening…" }));

    var loader = {
      group: loadGroup,
      ledger: loadLedger,
      month: loadMonth
    }[level.type];

    if (!loader) {
      UI.clear(body).appendChild(el("div.empty", { text: "Nothing further to open." }));
      return;
    }
    loader(level, body).catch(function (error) {
      UI.clear(body).appendChild(el("div.empty", { text: error.message }));
    });
  }

  /* A group: the sub groups and ledgers directly inside it */

  function loadGroup(level, body) {
    return api("/api/reports/group", { query: {
      group_id: level.id, from_ad: period.from_ad, to_ad: period.to_ad
    }}).then(function (data) {
      var rows = [];

      function line(entry) {
        var open = entry.kind === "group"
          ? function () { push({ type: "group", id: entry.id, label: entry.name }); }
          : function () { push({ type: "ledger", id: entry.id, label: entry.name }); };
        return el("tr.clickable", { onclick: open }, [
          el("td", { text: entry.code }),
          el("td", {}, [
            el("span", { text: entry.name }),
            entry.kind === "group"
              ? el("span.pill", { text: "group", style: "margin-left:.4rem" }) : null
          ]),
          el("td.num", { text: UI.rs(entry.opening, { blankZero: true }) }),
          el("td.num", { text: UI.rs(entry.debit, { blankZero: true }) }),
          el("td.num", { text: UI.rs(entry.credit, { blankZero: true }) }),
          el("td.num", { text: signed(entry.closing) })
        ]);
      }

      data.children.forEach(function (child) { rows.push(line(child)); });
      data.ledgers.forEach(function (ledger) { rows.push(line(ledger)); });

      UI.clear(body).appendChild(UI.table(
        ["Code", "Name", { label: "Opening", num: true }, { label: "Debit", num: true },
         { label: "Credit", num: true }, { label: "Closing", num: true }],
        rows,
        [el("tr.total-row", {}, [
          el("td", { colspan: "2", text: "Total for " + data.group.name }),
          el("td.num", { text: UI.rs(data.totals.opening, { blankZero: true }) }),
          el("td.num", { text: UI.rs(data.totals.debit) }),
          el("td.num", { text: UI.rs(data.totals.credit) }),
          el("td.num", { text: signed(data.totals.closing) })
        ])],
        { tall: true, emptyText: "Nothing has been posted under this group." }));
    });
  }

  /* A ledger: month by month */

  function loadLedger(level, body) {
    return api("/api/reports/ledger-monthly", { query: {
      account_id: level.id, from_ad: period.from_ad, to_ad: period.to_ad
    }}).then(function (data) {
      var rows = data.months.map(function (month) {
        return el("tr.clickable", {
          onclick: function () {
            push({ type: "month", accountId: level.id, from_ad: month.from_ad,
                   to_ad: month.to_ad, label: month.label });
          }
        }, [
          el("td", { text: month.label }),
          el("td.muted", { text: month.from_ad + " to " + month.to_ad,
                           style: "font-size:.74rem" }),
          el("td.num", { text: String(month.count) }),
          el("td.num", { text: UI.rs(month.debit, { blankZero: true }) }),
          el("td.num", { text: UI.rs(month.credit, { blankZero: true }) }),
          el("td.num", { text: signed(month.closing) })
        ]);
      });

      var head = el("div.drill-head", {}, [
        el("div", {}, [
          el("strong", { text: data.account.name }),
          el("div.muted", { style: "font-size:.78rem",
            text: data.account.code + "  ·  " + data.account.group_name })
        ]),
        el("div", { style: "text-align:right" }, [
          el("div.muted", { style: "font-size:.74rem", text: "Opening" }),
          el("div.num", { text: signed(data.opening) })
        ])
      ]);

      UI.clear(body);
      body.appendChild(head);
      body.appendChild(UI.table(
        ["Month", "Covering", { label: "Entries", num: true },
         { label: "Debit", num: true }, { label: "Credit", num: true },
         { label: "Balance", num: true }],
        rows,
        [el("tr.total-row", {}, [
          el("td", { colspan: "3", text: "For the period" }),
          el("td.num", { text: UI.rs(data.total_debit) }),
          el("td.num", { text: UI.rs(data.total_credit) }),
          el("td.num", { text: signed(data.closing) })
        ])],
        { emptyText: "Nothing was posted to this ledger in the period." }));
      body.appendChild(el("p.card-note", { style: "margin-top:.6rem",
        text: "Open a month to see the vouchers behind it." }));
    });
  }

  /* A month: the vouchers themselves */

  function loadMonth(level, body) {
    return api("/api/reports/ledger", { query: {
      account_id: level.accountId, from_ad: level.from_ad, to_ad: level.to_ad
    }}).then(function (data) {
      var rows = data.lines.map(function (line) {
        return el("tr.clickable", {
          onclick: function () { Vouchers.view(line.voucher_id); }
        }, [
          el("td", { text: UI.bs(line.date_ad, "short") }),
          el("td.muted", { text: line.date_ad, style: "font-size:.74rem" }),
          el("td", { text: line.number }),
          el("td", { text: line.party_name || "" }),
          el("td", { text: line.particulars || "", style: "max-width:280px" }),
          el("td.num", { text: UI.rs(line.dr, { blankZero: true }) }),
          el("td.num", { text: UI.rs(line.cr, { blankZero: true }) }),
          el("td.num", { text: signed(line.balance) })
        ]);
      });
      UI.clear(body).appendChild(UI.table(
        ["Date", "Gregorian", "Voucher", "Party", "Particulars",
         { label: "Debit", num: true }, { label: "Credit", num: true },
         { label: "Balance", num: true }],
        rows,
        [el("tr.total-row", {}, [
          el("td", { colspan: "5", text: "Total for " + level.label }),
          el("td.num", { text: UI.rs(data.total_dr) }),
          el("td.num", { text: UI.rs(data.total_cr) }),
          el("td.num", { text: signed(data.closing) })
        ])],
        { tall: true, emptyText: "No vouchers in this month." }));
    });
  }

  function signed(paisa) {
    if (paisa === 0) { return "0.00"; }
    return UI.rs(Math.abs(paisa)) + (paisa > 0 ? " Dr" : " Cr");
  }

  /* Helpers the report screens use to make a row openable */

  function openGroup(groupId, label) {
    start({ type: "group", id: groupId, label: label });
  }

  function openLedger(accountId, label) {
    start({ type: "ledger", id: accountId, label: label });
  }

  return {
    mount: mount, setPeriod: setPeriod, start: start, push: push, close: close,
    depth: depth, openGroup: openGroup, openLedger: openLedger, signed: signed
  };
}());
