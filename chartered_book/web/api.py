"""
Every address the screen can call.

Each handler does three things: check that the person is allowed to do this,
hand the work to a module, and return plain data. No accounting logic lives in
this file.
"""

import datetime
import os

from ..core import audit, auth, backup, coa, db, money, nepali_date as nd
from ..modules import company as company_module, invoices, ledger, masters, reports
from .server import ApiError, route


def rows(cursor_rows):
    return [dict(row) for row in cursor_rows]


def one(row):
    return dict(row) if row is not None else None


def today():
    return datetime.date.today().isoformat()


def _dates(request, conn):
    """Work out the date range a report should cover."""
    fy = company_module.current_fiscal_year(conn)
    from_ad = request.arg("from_ad") or (fy["start_ad"] if fy else today())
    to_ad = request.arg("to_ad") or (fy["end_ad"] if fy else today())
    return from_ad, to_ad


# Session and setup


@route("GET", "/api/ping")
def ping(request):
    """
    Says that a Saphal Book server is already answering here.

    The launcher calls this before starting. If a copy is already running it
    just opens the browser at it, rather than starting a second one that would
    fight over the same files.
    """
    return {"application": "chartered-book", "ok": True,
            "data_folder": db.DATA_DIR, "today": nd.describe(today())}


@route("GET", "/api/network")
def network(request):
    """The addresses this machine can be reached at, for the phone screen."""
    request.require_user()
    import socket
    addresses = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.4)
        probe.connect(("10.255.255.255", 1))
        addresses.append(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
    except OSError:
        pass
    from .server import BIND
    port = BIND["port"]
    # Only a server bound to every address can be reached by another machine.
    on_network = BIND["host"] not in ("127.0.0.1", "localhost", "::1")
    return {
        "addresses": addresses,
        "port": port,
        "hostname": _local_hostname(),
        "hostname_url": ("http://%s:%d/" % (_local_hostname(), port)) if _local_hostname() else "",
        "urls": ["http://%s:%d/" % (address, port) for address in addresses],
        "listening_on_network": on_network,
        "bound_to": BIND["host"],
        "this_url": "http://localhost:%d/" % port,
    }


def _local_hostname():
    """
    The name this machine answers to on the local network.

    Worth having because, unlike the numeric address, it does not change when
    the machine moves to a different wifi. An iPad resolves it without being
    told anything. A recent Android does too, an older one may not, which is
    why the numbers are still offered alongside.
    """
    import socket
    import subprocess
    import sys as _sys
    if _sys.platform == "darwin":
        try:
            result = subprocess.run(["scutil", "--get", "LocalHostName"],
                                    capture_output=True, text=True, timeout=4)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip() + ".local"
        except Exception:
            pass
    try:
        plain = socket.gethostname()
    except OSError:
        return ""
    if not plain:
        return ""
    return plain if plain.endswith(".local") else plain + ".local"


def _build_stamp():
    """
    Which copy of the software is answering, and whether it is behind the source.

    The Mac application carries its own copy of the code, so an improvement made
    to the source does not reach it until it is built again. Saying so on the
    screen is the difference between a fix that looks broken and a fix that
    simply has not arrived yet.
    """
    from ..core import build
    stamp = build.read()
    behind = False
    try:
        if not stamp.startswith("source of"):
            behind = build.newest_source().strftime("%Y-%m-%d %H:%M") > stamp
    except Exception:
        behind = False
    return {"stamp": stamp, "behind": behind}


@route("GET", "/api/bootstrap")
def bootstrap(request):
    """Everything the screen needs the moment it opens."""
    payload = {
        "needs_setup": not auth.has_any_user(request.system),
        "today": nd.describe(today()),
        "user": None,
        "companies": [],
        "company": None,
        "roles": auth.ROLE_LABELS,
        "version": "0.1",
    }
    if request.session:
        payload["user"] = {
            "username": request.session["username"],
            "full_name": request.session["full_name"],
            "role": request.session["role"],
            "must_change": request.session["must_change"],
        }
        payload["companies"] = rows(company_module.list_companies(request.system))
        payload["permissions"] = {action: auth.can(request.session, action)
                                  for action in auth.PERMISSIONS}
        if request.session.get("company_id"):
            try:
                conn = request.company()
                profile = company_module.profile(conn)
                fy = company_module.current_fiscal_year(conn)
                payload["company"] = one(profile)
                payload["company"]["id"] = request.session["company_id"]
                payload["settings"] = {r["key"]: r["value"]
                                       for r in conn.execute("SELECT * FROM settings")}
                payload["build"] = _build_stamp()
                payload["fiscal_year"] = one(fy)
                payload["fiscal_years"] = rows(company_module.fiscal_years(conn))
                payload["settings"] = {r["key"]: r["value"]
                                       for r in conn.execute("SELECT * FROM settings")}
            except ApiError:
                payload["company"] = None
            except Exception:
                payload["company"] = None
    return payload


@route("GET", "/api/gate-help")
def gate_help(request):
    """
    What to tell somebody stuck on the sign in screen.

    Answers the only question that matters at that moment: is there an account
    on this computer already, and if so does it have anything in it worth
    keeping. No password, no user name, nothing that helps anyone get in. This
    is deliberately available before signing in, because that is the one moment
    it is needed, and the server only ever listens on this machine.
    """
    system = request.system
    accounts = system.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    names = [row["username"] for row in
             system.execute("SELECT username FROM users ORDER BY id LIMIT 5")]
    companies = system.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"]

    # Whether anything has actually been entered, which decides whether starting
    # again is harmless or destroys work.
    vouchers = 0
    from ..modules import company as company_module
    for row in company_module.list_companies(system, include_inactive=True):
        try:
            book = company_module.open_company(row["slug"])
            vouchers += book.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"]
            book.close()
        except Exception:
            continue

    last = system.execute(
        "SELECT username, at, outcome FROM login_history ORDER BY id DESC LIMIT 1").fetchone()

    return {
        "accounts": accounts,
        "usernames": names,
        "companies": companies,
        "vouchers": vouchers,
        "empty": vouchers == 0,
        "data_folder": db.DATA_DIR,
        "last_attempt": dict(last) if last else None,
        "needs_setup": accounts == 0,
    }


@route("POST", "/api/setup")
def first_run_setup(request):
    """Create the first user. Only possible while no user exists."""
    if auth.has_any_user(request.system):
        raise ApiError("This system has already been set up.", 409)
    username = (request.arg("username") or "").strip()
    password = request.arg("password") or ""
    full_name = (request.arg("full_name") or "").strip()
    try:
        user_id = auth.create_user(request.system, username, password, full_name, "owner")
    except auth.AuthError as exc:
        raise ApiError(str(exc))
    token = auth.start_session(request.system, user_id)
    request.set_cookie = token
    return {"ok": True, "username": username}


def _try_account(request, username, password, making_account):
    """
    Do the account half of signing in, where there is a server to do it with.

    Returns a note about what happened, or None where there is no server or it
    could not be reached. Reaching it is never made a condition of getting into
    the books: a shop with the internet down still has to be able to trade, and
    the books are on this machine either way.
    """
    from ..core import cloud, cloud_config
    if not cloud_config.configured(request.system):
        return None
    settings = cloud_config.settings(request.system)
    session = cloud.Cloud(settings["url"], settings["anon_key"])
    try:
        if making_account:
            session.sign_up(username, password)
        else:
            session.sign_in(username, password)
    except cloud.CloudError as exc:
        message = str(exc)
        # A username somebody already holds is a real answer and has to stop an
        # attempt to open an account with it.
        if making_account and "taken" in message.lower():
            raise ApiError(message, 409)
        # Anything else is not this module's business to refuse. The account may
        # simply not exist yet, which is exactly the case for a login made on
        # this machine before there was ever a server, and turning that into a
        # refusal locked the owner out of their own books. The login kept on the
        # machine decides, and it is checked next.
        return {"reached": False, "why": message}
    return {"reached": True, "session": session, "username": session.username,
            "user_id": session.user_id or ""}


def _finish_account(request, note, token):
    """Hold on to the signed in connection and remember the name."""
    if not note or not note.get("reached"):
        return
    _CLOUD_SESSIONS[token] = note["session"]
    request.system.execute(
        """INSERT INTO cloud_account (id, username, user_id, last_signed_in)
           VALUES (1, ?, ?, ?)
           ON CONFLICT (id) DO UPDATE SET username = excluded.username,
                                          user_id = excluded.user_id,
                                          last_signed_in = excluded.last_signed_in""",
        (note["username"], note["user_id"], db.now_stamp()))
    request.system.commit()


@route("POST", "/api/login")
def login(request):
    """
    Sign in, to the account and to these books, with one name and one password.

    The account is checked first where there is a server and it answers, because
    that is the only place a username is counted and so the only place that can
    say whether this is really the same person. Where it cannot be reached, the
    copy of the login kept on this machine is used instead, so the shop is never
    stopped from trading by somebody else's outage.
    """
    username = (request.arg("username") or "").strip()
    password = request.arg("password") or ""
    note = _try_account(request, username, password, False)

    try:
        user = auth.authenticate(request.system, username, password)
    except auth.AuthError as exc:
        if note and note.get("reached"):
            # The account is genuine but this machine has never seen it, which
            # is what happens on a second device. Give it a login of its own so
            # it works here afterwards, with or without the internet.
            if auth.find_user(request.system, username) is None:
                role = "owner" if not auth.has_any_user(request.system) else "operator"
                auth.create_user(request.system, username, password, role=role)
            else:
                auth.set_password(request.system,
                                  auth.find_user(request.system, username)["id"], password)
            request.system.commit()
            user = auth.authenticate(request.system, username, password)
        else:
            raise ApiError(str(exc), 401)

    companies = company_module.list_companies(request.system)
    company_id = companies[0]["id"] if len(companies) == 1 else None
    token = auth.start_session(request.system, user["id"], company_id)
    _finish_account(request, note, token)
    request.set_cookie = token
    return {"ok": True, "username": user["username"], "role": user["role"],
            "must_change": user["must_change"],
            "account": bool(note and note.get("reached")),
            "account_note": "" if not note else note.get("why", "")}


@route("POST", "/api/register")
def register(request):
    """
    Open an account and a login on this machine, in that order.

    The order is the point. The server is asked first, and it refuses a username
    somebody already holds. Making the login here first would let two people on
    two devices both believe they were saphalism, which is exactly what used to
    happen.
    """
    username = (request.arg("username") or "").strip()
    password = request.arg("password") or ""
    if len(password) < 8:
        raise ApiError("Use at least eight characters. This password also unlocks the "
                       "books, so a short one is the weak link.")
    existing = auth.find_user(request.system, username)
    if existing is not None:
        # Somebody who has been using these books since before there was a
        # server. The name is theirs already; opening the account simply lifts
        # it onto one. Proving the password is what stops anybody else doing it.
        try:
            auth.authenticate(request.system, username, password)
        except auth.AuthError:
            raise ApiError(
                "There is already a login called %s on this device, and that is not its "
                "password. Use the password you have been signing in with here, and the "
                "account will be opened under it." % username, 409)

    note = _try_account(request, username, password, True)
    if note is not None and not note.get("reached"):
        raise ApiError(
            "The account could not be opened because the server could not be reached. "
            "Opening one needs the internet, once. After that, signing in works without "
            "it. (%s)" % note.get("why", ""))

    if existing is None:
        role = "owner" if not auth.has_any_user(request.system) else "operator"
        auth.create_user(request.system, username, password, role=role)
        request.system.commit()
    user = auth.authenticate(request.system, username, password)
    companies = company_module.list_companies(request.system)
    company_id = companies[0]["id"] if len(companies) == 1 else None
    token = auth.start_session(request.system, user["id"], company_id)
    _finish_account(request, note, token)
    request.set_cookie = token
    return {"ok": True, "username": user["username"], "role": user["role"],
            "account": bool(note and note.get("reached"))}


@route("POST", "/api/logout")
def logout(request):
    if request.session:
        auth.end_session(request.system, request.session["token"])
    request.clear_cookie = True
    return {"ok": True}


@route("POST", "/api/change-password")
def change_password(request):
    user = request.require_user()
    current = request.arg("current_password") or ""
    fresh = request.arg("new_password") or ""
    try:
        auth.authenticate(request.system, user["username"], current)
        auth.set_password(request.system, user["user_id"], fresh)
    except auth.AuthError as exc:
        raise ApiError(str(exc))
    return {"ok": True}


@route("GET", "/api/users")
def list_users(request):
    request.require("user.manage")
    return {"rows": rows(request.system.execute(
        """SELECT id, username, full_name, role, active, created_at, last_login_at
           FROM users ORDER BY username"""))}


@route("POST", "/api/users/create")
def create_user(request):
    request.require("user.manage")
    try:
        user_id = auth.create_user(
            request.system, request.arg("username"), request.arg("password"),
            request.arg("full_name") or "", request.arg("role") or "operator", must_change=1)
    except auth.AuthError as exc:
        raise ApiError(str(exc))
    return {"ok": True, "id": user_id}


@route("POST", "/api/users/<user_id>/update")
def update_user(request, user_id):
    request.require("user.manage")
    user_id = int(user_id)
    if request.arg("password"):
        try:
            auth.set_password(request.system, user_id, request.arg("password"))
        except auth.AuthError as exc:
            raise ApiError(str(exc))
    sets, args = [], []
    for field in ("full_name", "role", "active"):
        if field in request.body:
            if field == "role" and request.body[field] not in auth.ROLES:
                raise ApiError("Unknown role.")
            sets.append("%s = ?" % field)
            args.append(request.body[field])
    if sets:
        args.append(user_id)
        request.system.execute("UPDATE users SET %s WHERE id = ?" % ", ".join(sets), args)
    return {"ok": True}


# Companies


@route("GET", "/api/companies")
def companies(request):
    request.require_user()
    return {"rows": rows(company_module.list_companies(request.system, include_inactive=True)),
            "business_types": company_module.BUSINESS_TYPES,
            "entity_types": company_module.ENTITY_TYPES}


@route("POST", "/api/companies/create")
def create_company(request):
    request.require("company.create")
    body = dict(request.body)
    name = (body.pop("name", "") or "").strip()
    business_type = body.pop("business_type", "trading")
    if not name:
        raise ApiError("Give the company a name.")
    pan = (body.get("pan") or "").strip()
    if pan and (not pan.isdigit() or len(pan) != 9):
        raise ApiError("A Nepali PAN is nine digits.")
    result = company_module.create_company(request.system, name, business_type,
                                           request.username(), **body)
    auth.set_session_company(request.system, request.session["token"], result["id"])
    return {"ok": True, "id": result["id"], "slug": result["slug"]}


@route("POST", "/api/companies/select")
def select_company(request):
    request.require_user()
    company_id = request.int_arg("company_id")
    row = request.system.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        raise ApiError("No such company.")
    auth.set_session_company(request.system, request.session["token"], company_id)
    return {"ok": True, "name": row["name"], "slug": row["slug"]}


@route("GET", "/api/company")
def get_company(request):
    conn = request.company()
    return {"profile": one(company_module.profile(conn)),
            "build": _build_stamp(),
            "fiscal_year": one(company_module.current_fiscal_year(conn)),
            "fiscal_years": rows(company_module.fiscal_years(conn)),
            "settings": {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings")}}


@route("POST", "/api/company/update")
def update_company(request):
    request.require("company.edit")
    conn = request.company()
    body = dict(request.body)
    settings = body.pop("settings", None)
    company_module.update_profile(conn, request.username(), **body)
    if isinstance(settings, dict):
        for key, value in settings.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         (key, str(value)))
    if "name" in body:
        request.system.execute("UPDATE companies SET name = ? WHERE id = ?",
                               (body["name"], request.session["company_id"]))
    return {"ok": True}


@route("POST", "/api/fiscal-years/create")
def create_fiscal_year(request):
    request.require("company.edit")
    conn = request.company()
    start_bs_year = request.int_arg("start_bs_year")
    if not start_bs_year:
        raise ApiError("Give the Bikram Sambat year the fiscal year starts in.")
    row = company_module.ensure_fiscal_year(conn, start_bs_year, request.username())
    if request.arg("make_current"):
        conn.execute("UPDATE company SET current_fy_id = ? WHERE id = 1", (row["id"],))
    return {"ok": True, "fiscal_year": one(row)}


@route("POST", "/api/fiscal-years/select")
def select_fiscal_year(request):
    request.require_user()
    conn = request.company()
    fy_id = request.int_arg("fiscal_year_id")
    row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
    if row is None:
        raise ApiError("No such fiscal year.")
    conn.execute("UPDATE company SET current_fy_id = ? WHERE id = 1", (fy_id,))
    return {"ok": True, "fiscal_year": one(row)}


# Masters


@route("GET", "/api/lookups")
def lookups(request):
    conn = request.company()
    return {
        "units": rows(masters.units(conn)),
        "item_groups": rows(masters.item_groups(conn)),
        "warehouses": rows(masters.warehouses(conn)),
        "voucher_types": rows(conn.execute(
            "SELECT * FROM voucher_types WHERE active = 1 ORDER BY sort_order")),
        "tds_sections": rows(conn.execute(
            "SELECT * FROM tds_sections WHERE active = 1 ORDER BY code")),
        "account_groups": rows(masters.account_groups(conn)),
    }


@route("GET", "/api/accounts")
def list_accounts(request):
    conn = request.company()
    only_active = request.arg("all") != "1"
    result = masters.accounts(conn, only_active=only_active,
                              group_id=request.int_arg("group_id"),
                              kind=request.arg("kind"),
                              search=request.arg("q"))
    out = rows(result)
    if request.arg("with_balance") == "1":
        balances = reports.balances_as_at(conn, request.arg("as_at") or today())
        for row in out:
            row["balance"] = balances.get(row["id"], 0)
    return {"rows": out}


@route("GET", "/api/accounts/<account_id>")
def get_account(request, account_id):
    conn = request.company()
    account = masters.get_account(conn, int(account_id))
    if account is None:
        raise ApiError("No such account.", 404)
    return {"account": one(account)}


@route("POST", "/api/accounts/create")
def create_account(request):
    request.require("master.create")
    conn = request.company()
    body = dict(request.body)
    name = body.pop("name", "")
    group_id = body.pop("group_id", None)
    try:
        account_id = masters.create_account(conn, request.username(), name, group_id, **body)
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True, "id": account_id}


@route("POST", "/api/accounts/<account_id>/update")
def update_account(request, account_id):
    request.require("master.edit")
    conn = request.company()
    try:
        masters.update_account(conn, request.username(), int(account_id), **request.body)
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True}


@route("POST", "/api/accounts/<account_id>/delete")
def delete_account(request, account_id):
    request.require("master.delete")
    conn = request.company()
    try:
        masters.delete_account(conn, request.username(), int(account_id))
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True}


@route("GET", "/api/parties")
def list_parties(request):
    conn = request.company()
    result = masters.parties(conn, party_type=request.arg("type"),
                             only_active=request.arg("all") != "1",
                             search=request.arg("q"))
    out = rows(result)
    if request.arg("with_balance") == "1":
        balances = reports.balances_as_at(conn, request.arg("as_at") or today())
        for row in out:
            row["balance"] = balances.get(row["account_id"], 0)
    return {"rows": out}


@route("GET", "/api/parties/<party_id>")
def get_party(request, party_id):
    conn = request.company()
    party = masters.get_party(conn, int(party_id))
    if party is None:
        raise ApiError("No such party.", 404)
    return {"party": one(party)}


@route("POST", "/api/parties/create")
def create_party(request):
    request.require("master.create")
    conn = request.company()
    body = dict(request.body)
    name = body.pop("name", "")
    party_type = body.pop("party_type", "customer")
    try:
        party_id = masters.create_party(conn, request.username(), name, party_type, **body)
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True, "id": party_id}


@route("POST", "/api/parties/<party_id>/update")
def update_party(request, party_id):
    request.require("master.edit")
    conn = request.company()
    try:
        masters.update_party(conn, request.username(), int(party_id), **request.body)
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True}


@route("GET", "/api/items")
def list_items(request):
    conn = request.company()
    result = masters.items(conn, only_active=request.arg("all") != "1",
                           group_id=request.int_arg("group_id"),
                           item_type=request.arg("type"),
                           search=request.arg("q"))
    out = rows(result)
    if request.arg("with_stock") == "1":
        for row in out:
            if row["maintain_stock"]:
                state = reports.item_stock(conn, row["id"], request.arg("as_at"))
                row["stock_qty"] = state["qty"]
                row["stock_value"] = state["value"]
            else:
                row["stock_qty"] = 0
                row["stock_value"] = 0
    return {"rows": out}


@route("GET", "/api/items/<item_id>")
def get_item(request, item_id):
    conn = request.company()
    item = masters.get_item(conn, int(item_id))
    if item is None:
        raise ApiError("No such item.", 404)
    state = reports.item_stock(conn, int(item_id))
    return {"item": one(item), "stock_qty": state["qty"], "stock_value": state["value"],
            "average_rate": state["average_rate"]}


@route("POST", "/api/items/create")
def create_item(request):
    request.require("master.create")
    conn = request.company()
    body = dict(request.body)
    name = body.pop("name", "")
    try:
        item_id = masters.create_item(conn, request.username(), name, **body)
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True, "id": item_id}


@route("POST", "/api/items/<item_id>/update")
def update_item(request, item_id):
    request.require("master.edit")
    conn = request.company()
    try:
        masters.update_item(conn, request.username(), int(item_id), **request.body)
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True}


@route("POST", "/api/items/<item_id>/delete")
def delete_item(request, item_id):
    request.require("master.delete")
    conn = request.company()
    try:
        masters.delete_item(conn, request.username(), int(item_id))
    except masters.MasterError as exc:
        raise ApiError(str(exc))
    return {"ok": True}


# Vouchers


def _post(conn, request, builder):
    with db.Transaction(conn):
        try:
            return builder()
        except (ledger.PostingError, invoices.InvoiceError, masters.MasterError) as exc:
            raise ApiError(str(exc))


@route("POST", "/api/vouchers/create")
def create_voucher(request):
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    voucher_id = _post(conn, request,
                       lambda: ledger.post_voucher(conn, request.username(), payload))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("POST", "/api/vouchers/sales")
def create_sales(request):
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    voucher_id = _post(conn, request,
                       lambda: invoices.post_sales(conn, request.username(), payload))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("POST", "/api/vouchers/purchase")
def create_purchase(request):
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    voucher_id = _post(conn, request,
                       lambda: invoices.post_purchase(conn, request.username(), payload))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("POST", "/api/vouchers/preview")
def preview_invoice(request):
    """Price an invoice without saving it, so the screen can show live totals."""
    request.require_user()
    conn = request.company()
    try:
        result = invoices.price_voucher(conn, request.body)
    except invoices.InvoiceError as exc:
        raise ApiError(str(exc))
    other = money.to_paisa(request.body.get("other_charges") or 0)
    total = result["net"] + other
    rounded = total
    if request.body.get("round_invoice", True):
        remainder = total % 100
        if remainder:
            rounded = total - remainder + (100 if remainder >= 50 else 0)
    return {
        "lines": [{k: v for k, v in line.items()} for line in result["lines"]],
        "subtotal": result["subtotal"], "discount": result["discount"],
        "line_discount": result["line_discount"], "bill_discount": result["bill_discount"],
        "taxable": result["taxable"], "exempt": result["exempt"], "vat": result["vat"],
        "other_charges": other, "round_off": rounded - total, "total": rounded,
        "in_words": money.amount_in_words(rounded),
        "in_words_np": money.amount_in_words(rounded, "np"),
    }


def _voucher_payload(conn, voucher_id):
    data = ledger.get_voucher(conn, voucher_id)
    if data is None:
        return None
    return {
        "voucher": one(data["voucher"]),
        "entries": rows(data["entries"]),
        "items": rows(data["items"]),
        "allocations": rows(data["allocations"]),
        "in_words": money.amount_in_words(data["voucher"]["total_paisa"]),
        "in_words_np": money.amount_in_words(data["voucher"]["total_paisa"], "np"),
    }


@route("GET", "/api/vouchers/<voucher_id>")
def get_voucher(request, voucher_id):
    conn = request.company()
    payload = _voucher_payload(conn, int(voucher_id))
    if payload is None:
        raise ApiError("No such voucher.", 404)
    return payload


@route("POST", "/api/vouchers/<voucher_id>/amend")
def amend_voucher(request, voucher_id):
    request.require("voucher.edit")
    conn = request.company()
    payload = dict(request.body)
    kind = payload.pop("build", None)
    if kind == "sales":
        payload = invoices.build_sales(conn, payload)
    elif kind == "purchase":
        payload = invoices.build_purchase(conn, payload)
    _post(conn, request,
          lambda: ledger.amend_voucher(conn, request.username(), int(voucher_id), payload))
    return {"ok": True, "voucher": _voucher_payload(conn, int(voucher_id))}


@route("POST", "/api/vouchers/<voucher_id>/cancel")
def cancel_voucher(request, voucher_id):
    request.require("voucher.cancel")
    conn = request.company()
    reason = request.arg("reason") or ""
    _post(conn, request,
          lambda: ledger.cancel_voucher(conn, request.username(), int(voucher_id), reason))
    return {"ok": True}


@route("POST", "/api/vouchers/<voucher_id>/delete")
def delete_voucher(request, voucher_id):
    request.require("voucher.delete")
    conn = request.company()
    _post(conn, request,
          lambda: ledger.delete_draft(conn, request.username(), int(voucher_id)))
    return {"ok": True}


@route("GET", "/api/daybook")
def daybook(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    result = reports.day_book(conn, from_ad, to_ad, request.arg("voucher_type"),
                              request.arg("include_cancelled") == "1")
    return {"rows": rows(result), "from_ad": from_ad, "to_ad": to_ad}


@route("GET", "/api/next-number")
def next_number(request):
    conn = request.company()
    voucher_type = request.arg("voucher_type") or "sales"
    date_ad = request.arg("date_ad") or today()
    try:
        fy = ledger.fiscal_year_for_date(conn, date_ad)
    except ledger.PostingError as exc:
        raise ApiError(str(exc))
    return {"number": ledger.next_voucher_number(conn, voucher_type, fy["id"], reserve=False),
            "fiscal_year": one(fy)}


# Reports


@route("GET", "/api/reports/trial-balance")
def trial_balance(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    return reports.trial_balance(conn, from_ad, to_ad, request.arg("include_zero") == "1")


@route("GET", "/api/reports/ledger")
def ledger_report(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    account_id = request.int_arg("account_id")
    if not account_id:
        raise ApiError("Choose a ledger to view.")
    result = reports.ledger_statement(conn, account_id, from_ad, to_ad)
    if result is None:
        raise ApiError("No such account.", 404)
    result["account"] = one(result["account"])
    return result


@route("GET", "/api/reports/profit-loss")
def profit_loss(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    return reports.profit_and_loss(conn, from_ad, to_ad)


@route("GET", "/api/reports/balance-sheet")
def balance_sheet(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    return reports.balance_sheet(conn, to_ad, from_ad)


@route("GET", "/api/reports/stock")
def stock_report(request):
    conn = request.company()
    _, to_ad = _dates(request, conn)
    return reports.stock_summary(conn, request.arg("as_at") or to_ad,
                                 request.int_arg("group_id"))


@route("GET", "/api/reports/stock-item")
def stock_item(request):
    conn = request.company()
    item_id = request.int_arg("item_id")
    if not item_id:
        raise ApiError("Choose an item.")
    result = reports.item_stock(conn, item_id, request.arg("as_at"))
    if result is None:
        raise ApiError("No such item.", 404)
    result["item"] = one(result["item"])
    return result


@route("GET", "/api/reports/outstanding")
def outstanding(request):
    conn = request.company()
    _, to_ad = _dates(request, conn)
    side = request.arg("side") or "receivable"
    return reports.outstanding(conn, side, request.arg("as_at") or to_ad)


@route("GET", "/api/reports/vat")
def vat_report(request):
    conn = request.company()
    bs_year = request.int_arg("bs_year")
    bs_month = request.int_arg("bs_month")
    if not bs_year or not bs_month:
        current = nd.today_bs()
        bs_year = bs_year or current[0]
        bs_month = bs_month or current[1]
    try:
        return reports.vat_return(conn, bs_year, bs_month)
    except nd.DateRangeError as exc:
        raise ApiError(str(exc))


@route("POST", "/api/period-end/vat-settlement")
def settle_vat(request):
    """
    Close a month's value added tax off into what is actually owed.

    Output tax and input tax go on accumulating in their own ledgers until the
    month is closed off. Without this the balance sheet shows a large tax asset
    and a large tax liability side by side when only the difference is really
    owed, or only the difference is really recoverable.
    """
    from ..modules import period_end
    request.require("voucher.create")
    conn = request.company()
    bs_year = request.body.get("bs_year")
    bs_month = request.body.get("bs_month")
    if not bs_year or not bs_month:
        raise ApiError("Say which Nepali month is being settled.")
    try:
        voucher_id = _post(conn, request, lambda: period_end.post_vat_settlement(
            conn, request.username(), int(bs_year), int(bs_month)))
    except period_end.PeriodEndError as exc:
        raise ApiError(str(exc))
    return {"ok": True, "id": voucher_id}


@route("GET", "/api/dashboard")
def dashboard(request):
    conn = request.company()
    fy = company_module.current_fiscal_year(conn)
    from_ad = fy["start_ad"] if fy else today()
    to_ad = min(today(), fy["end_ad"]) if fy else today()
    pl = reports.profit_and_loss(conn, from_ad, to_ad)
    stock = reports.stock_summary(conn, to_ad)

    # Stock is kept on the periodic basis, so cost of sales holds purchases in
    # full until the closing stock entry is passed. For a figure the owner can
    # act on today, take the stock that is on hand but not yet booked and show
    # gross profit and profit as they will read once that entry is made.
    from ..modules import period_end
    try:
        position = period_end.closing_stock_position(conn, to_ad)
        pending_stock = position["adjustment"]
    except period_end.PeriodEndError:
        pending_stock = 0
    gross_profit = pl["gross_profit"] + pending_stock
    profit = pl["profit_after_tax"] + pending_stock

    receivable = reports.outstanding(conn, "receivable", to_ad)
    payable = reports.outstanding(conn, "payable", to_ad)
    cash = reports.cash_and_bank_summary(conn, to_ad)
    bs_now = nd.today_bs()
    vat = None
    profile = company_module.profile(conn)
    if profile and profile["vat_registered"]:
        vat = reports.vat_return(conn, bs_now[0], bs_now[1])
        vat.pop("sales_rows", None)
        vat.pop("purchase_rows", None)
    low_stock = [r for r in stock["rows"] if r["below_reorder"]][:10]
    recent = reports.day_book(conn, from_ad, to_ad)
    return {
        "fiscal_year": one(fy),
        "period": {"from_ad": from_ad, "to_ad": to_ad},
        "revenue": pl["revenue"],
        "gross_profit": gross_profit,
        "expenses": pl["operating_expense"] + pl["finance"] + pl["depreciation"] + pl["other_expense"],
        "profit": profit,
        "pending_closing_stock": pending_stock,
        "gross_profit_booked": pl["gross_profit"],
        "stock_value": stock["total_value"],
        "receivable": receivable["total"],
        "payable": payable["total"],
        "cash_and_bank": cash,
        "vat": vat,
        "low_stock": low_stock,
        "recent_vouchers": rows(recent[-12:][::-1]),
        "counts": {
            "parties": conn.execute("SELECT COUNT(*) n FROM parties WHERE active = 1").fetchone()["n"],
            "items": conn.execute("SELECT COUNT(*) n FROM items WHERE active = 1").fetchone()["n"],
            "vouchers": conn.execute(
                "SELECT COUNT(*) n FROM vouchers WHERE status = 'posted'").fetchone()["n"],
        },
    }


@route("GET", "/api/audit")
def audit_trail(request):
    request.require("audit.view")
    conn = request.company()
    limit = request.int_arg("limit", 200)
    return {"rows": rows(conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)))}


# Dates and the calculator helpers


@route("GET", "/api/date/convert")
def convert_date(request):
    ad = request.arg("ad")
    bs = request.arg("bs")
    try:
        if bs:
            parts = nd.parse_bs(bs)
            return nd.describe(nd.bs_to_ad(*parts))
        return nd.describe(ad or today())
    except (nd.DateRangeError, ValueError) as exc:
        raise ApiError(str(exc))


@route("GET", "/api/date/calendar")
def calendar_month(request):
    bs_year = request.int_arg("year")
    bs_month = request.int_arg("month")
    if not bs_year or not bs_month:
        bs_year, bs_month, _ = nd.today_bs()
    try:
        grid = nd.bs_month_grid(bs_year, bs_month)
    except nd.DateRangeError as exc:
        raise ApiError(str(exc))
    grid["today_ad"] = today()
    grid["min_year"] = nd.BS_START_YEAR
    grid["max_year"] = nd.BS_END_YEAR
    return grid


@route("GET", "/api/amount-in-words")
def amount_words(request):
    amount = request.arg("amount") or "0"
    try:
        paisa = money.to_paisa(amount)
    except money.MoneyError as exc:
        raise ApiError(str(exc))
    return {"paisa": paisa,
            "en": money.amount_in_words(paisa),
            "np": money.amount_in_words(paisa, "np"),
            "formatted": money.format_money(paisa),
            "formatted_np": money.format_money(paisa, lang="np")}


# Backup


@route("GET", "/api/backup/list")
def list_backups(request):
    request.require("backup.run")
    return {"rows": backup.list_backups(), "folder": backup.export_folder()}


@route("POST", "/api/backup/create")
def make_backup(request):
    request.require("backup.run")
    info = backup.create_backup(request.arg("note") or "", "manual")
    return {"ok": True, "backup": info}


@route("GET", "/api/backup/download")
def download_backup(request):
    """
    Hand a backup over as text, so it can be saved as a file wherever the books
    are being looked at.

    This is what lets a set of books leave a tablet. There is no folder to reach
    into on a phone, and no shared server anywhere, so the file has to travel
    through the screen itself.
    """
    import base64
    request.require("backup.run")
    name = request.arg("name")
    if not name:
        raise ApiError("Say which backup to send.")
    try:
        data = backup.read_backup(name)
    except (FileNotFoundError, OSError) as exc:
        raise ApiError(str(exc), 404)
    return {"filename": os.path.basename(name),
            "content": base64.b64encode(data).decode("ascii"),
            "bytes": len(data)}


@route("POST", "/api/backup/upload")
def upload_backup(request):
    """Take in a backup made on another device and put it with the rest."""
    import base64
    request.require("backup.restore")
    content = request.body.get("content") or ""
    if not content:
        raise ApiError("Choose the backup file first.")
    try:
        data = base64.b64decode(content)
    except Exception:
        raise ApiError("That file could not be read.")
    try:
        info = backup.accept_backup(data, request.body.get("filename") or "")
    except (ValueError, OSError) as exc:
        raise ApiError(str(exc))
    return {"ok": True, "backup": info}


@route("POST", "/api/backup/restore")
def restore_backup(request):
    request.require("backup.restore")
    filename = request.arg("filename")
    if not filename:
        raise ApiError("Choose a backup to restore.")
    try:
        result = backup.restore_backup(filename)
    except (FileNotFoundError, ValueError) as exc:
        raise ApiError(str(exc))
    return {"ok": True, "result": result,
            "message": "Restored. Close and start Saphal Book again so every screen reloads."}


@route("GET", "/api/reference/tds")
def tds_reference(request):
    return {"rows": [{"code": c, "description": d, "rate_bp": r, "legal_ref": ref}
                     for c, d, r, ref in coa.TDS_SECTIONS]}


# Period end


@route("GET", "/api/period-end/closing-stock")
def closing_stock_preview(request):
    from ..modules import period_end
    conn = request.company()
    _, to_ad = _dates(request, conn)
    date_ad = request.arg("date_ad") or to_ad
    try:
        return period_end.closing_stock_position(conn, date_ad)
    except period_end.PeriodEndError as exc:
        raise ApiError(str(exc))


@route("POST", "/api/period-end/closing-stock")
def post_closing_stock(request):
    from ..modules import period_end
    request.require("voucher.create")
    conn = request.company()
    date_ad = request.arg("date_ad")
    if not date_ad:
        raise ApiError("Choose the date to value the stock at.")
    with db.Transaction(conn):
        try:
            voucher_id = period_end.post_closing_stock(conn, request.username(), date_ad,
                                                       request.arg("narration") or "")
        except (period_end.PeriodEndError, ledger.PostingError) as exc:
            raise ApiError(str(exc))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("POST", "/api/period-end/opening-stock")
def post_opening_stock(request):
    from ..modules import period_end
    request.require("voucher.create")
    conn = request.company()
    date_ad = request.arg("date_ad")
    if not date_ad:
        raise ApiError("Choose the first day of the new year.")
    with db.Transaction(conn):
        try:
            voucher_id = period_end.post_opening_stock(conn, request.username(), date_ad,
                                                       request.arg("narration") or "")
        except (period_end.PeriodEndError, ledger.PostingError) as exc:
            raise ApiError(str(exc))
    return {"ok": True, "id": voucher_id}


@route("GET", "/api/period-end/depreciation")
def depreciation_preview(request):
    from ..modules import period_end
    conn = request.company()
    _, to_ad = _dates(request, conn)
    return period_end.depreciation_preview(conn, request.arg("as_at") or to_ad)


# Banking and reconciliation


@route("GET", "/api/banking/accounts")
def banking_accounts(request):
    from ..modules import banking
    conn = request.company()
    _, to_ad = _dates(request, conn)
    as_at = request.arg("as_at") or min(today(), to_ad)
    return {"rows": banking.accounts(conn, as_at), "as_at": as_at,
            "position": banking.cash_position(conn, as_at)}


@route("POST", "/api/banking/accounts/create")
def create_banking_account(request):
    from ..modules import banking
    request.require("master.create")
    conn = request.company()
    body = dict(request.body)
    name = (body.pop("name", "") or "").strip()
    kind = body.pop("kind", "bank")
    if not name:
        raise ApiError("Give the account a name.")
    try:
        account_id = banking.create_account(conn, request.username(), name, kind, **body)
    except (banking.BankingError, masters.MasterError) as exc:
        raise ApiError(str(exc))
    return {"ok": True, "id": account_id}


@route("GET", "/api/banking/reconciliation")
def reconciliation_worksheet(request):
    from ..modules import banking
    conn = request.company()
    account_id = request.int_arg("account_id")
    if not account_id:
        raise ApiError("Choose an account to reconcile.")
    statement_date = request.arg("statement_date_ad") or today()
    try:
        return banking.worksheet(conn, account_id, statement_date)
    except banking.BankingError as exc:
        raise ApiError(str(exc))


@route("POST", "/api/banking/clear")
def mark_cleared(request):
    from ..modules import banking
    request.require("voucher.edit")
    conn = request.company()
    entry_ids = request.body.get("entry_ids") or []
    if not isinstance(entry_ids, list):
        raise ApiError("Nothing was selected.")
    cleared_ad = request.arg("cleared_ad") or ""
    with db.Transaction(conn):
        count = banking.set_cleared(conn, request.username(), [int(i) for i in entry_ids],
                                    cleared_ad, request.int_arg("account_id"))
    return {"ok": True, "count": count}


@route("POST", "/api/banking/reconciliation/save")
def save_reconciliation(request):
    from ..modules import banking
    request.require("voucher.edit")
    conn = request.company()
    account_id = request.int_arg("account_id")
    statement_date = request.arg("statement_date_ad")
    if not account_id or not statement_date:
        raise ApiError("Choose the account and the statement date.")
    with db.Transaction(conn):
        try:
            recon_id = banking.save_reconciliation(
                conn, request.username(), account_id, statement_date,
                request.arg("statement_balance") or 0, request.arg("note") or "",
                bool(request.arg("complete")))
        except banking.BankingError as exc:
            raise ApiError(str(exc))
    return {"ok": True, "id": recon_id}


@route("GET", "/api/banking/history")
def reconciliation_history(request):
    from ..modules import banking
    conn = request.company()
    return {"rows": rows(banking.history(conn, request.int_arg("account_id")))}


# Quick creation of the small lists, so nothing forces you to leave a voucher


@route("POST", "/api/units/create")
def create_unit(request):
    request.require("master.create")
    conn = request.company()
    name = (request.arg("name") or "").strip()
    symbol = (request.arg("symbol") or "").strip()
    if not name or not symbol:
        raise ApiError("A unit needs a name and a short symbol.")
    if conn.execute("SELECT 1 FROM units WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        raise ApiError("A unit called %s already exists." % name)
    cur = conn.execute("INSERT INTO units (name, symbol, decimals, active) VALUES (?, ?, ?, 1)",
                       (name, symbol, int(request.arg("decimals") or 0)))
    audit.log(conn, request.username(), "unit.create", "units", cur.lastrowid, symbol,
              "Unit %s added." % name)
    return {"ok": True, "id": cur.lastrowid, "name": name, "symbol": symbol}


@route("POST", "/api/item-groups/create")
def create_item_group(request):
    request.require("master.create")
    conn = request.company()
    name = (request.arg("name") or "").strip()
    if not name:
        raise ApiError("Give the group a name.")
    if conn.execute("SELECT 1 FROM item_groups WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        raise ApiError("A group called %s already exists." % name)
    code = (request.arg("code") or "").strip() or ("G%03d" % (
        conn.execute("SELECT COUNT(*) n FROM item_groups").fetchone()["n"] + 1))
    while conn.execute("SELECT 1 FROM item_groups WHERE code = ?", (code,)).fetchone():
        code = code + "X"
    cur = conn.execute("INSERT INTO item_groups (code, name, name_np, active) VALUES (?, ?, ?, 1)",
                       (code, name, request.arg("name_np") or ""))
    audit.log(conn, request.username(), "item_group.create", "item_groups", cur.lastrowid, code,
              "Item group %s added." % name)
    return {"ok": True, "id": cur.lastrowid, "name": name, "code": code}


@route("POST", "/api/warehouses/create")
def create_warehouse(request):
    request.require("master.create")
    conn = request.company()
    name = (request.arg("name") or "").strip()
    if not name:
        raise ApiError("Give the store a name.")
    code = (request.arg("code") or "").strip() or name[:4].upper()
    while conn.execute("SELECT 1 FROM warehouses WHERE code = ?", (code,)).fetchone():
        code = code + "X"
    cur = conn.execute(
        "INSERT INTO warehouses (code, name, address, is_default, active) VALUES (?, ?, ?, 0, 1)",
        (code, name, request.arg("address") or ""))
    return {"ok": True, "id": cur.lastrowid, "name": name}


# Backup destinations


@route("GET", "/api/backup/destinations")
def backup_destinations(request):
    request.require("backup.run")
    running = backup._running_programs()
    folders = backup.get_destinations(request.system)
    return {
        # Each folder says whether anything is actually carrying it to the
        # internet. A folder belonging to a cloud service whose program has been
        # uninstalled looks exactly as it always did, and quietly keeps every
        # backup on this machine.
        "folders": [dict(backup.sync_state(f, running), path=f) for f in folders],
        "suggestions": [dict(s, **backup.sync_state(s["path"], running))
                        for s in backup.likely_cloud_folders()],
        "data_folder": db.DATA_DIR,
        "backup_folder": db.BACKUP_DIR,
    }


@route("POST", "/api/backup/prune")
def prune_backups(request):
    """
    Clear out the automatic backups, keeping the newest few.

    Pressing the backup button a few times while wondering whether anything
    happened leaves a pile of identical copies. Anything taken by hand is kept,
    because somebody meant to take it.
    """
    request.require("backup.restore")
    keep = int(request.body.get("keep") or 3)
    removed = backup.prune_automatic(max(1, keep))
    return {"ok": True, "removed": removed, "kept": keep}


@route("POST", "/api/backup/destinations")
def set_backup_destinations(request):
    request.require("backup.restore")
    folders = request.body.get("folders")
    if not isinstance(folders, list):
        raise ApiError("Send the list of folders.")
    saved, problems = backup.set_destinations(request.system, folders)
    return {"ok": True, "folders": saved, "problems": problems}


# Drilling into a figure


@route("GET", "/api/reports/groups")
def group_tree(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    tree = reports.group_tree(conn, from_ad, to_ad,
                              request.arg("statement"), request.arg("section"))
    # A dictionary keyed by integer will not survive JSON, so send a list.
    return {"nodes": list(tree["nodes"].values()), "roots": tree["roots"],
            "from_ad": from_ad, "to_ad": to_ad}


@route("GET", "/api/reports/group")
def group_detail(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    group_id = request.int_arg("group_id")
    if not group_id:
        raise ApiError("Choose a group to open.")
    result = reports.group_detail(conn, group_id, from_ad, to_ad)
    if result is None:
        raise ApiError("No such group.", 404)
    return result


@route("GET", "/api/reports/ledger-monthly")
def ledger_monthly(request):
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    account_id = request.int_arg("account_id")
    if not account_id:
        raise ApiError("Choose a ledger to open.")
    result = reports.ledger_monthly(conn, account_id, from_ad, to_ad)
    if result is None:
        raise ApiError("No such ledger.", 404)
    return result


@route("GET", "/api/reports/ageing")
def ageing_report(request):
    conn = request.company()
    _, to_ad = _dates(request, conn)
    side = request.arg("side") or "receivable"
    return reports.ageing(conn, side, request.arg("as_at") or to_ad)


# The formal financial statements


@route("GET", "/api/reports/statements")
def financial_statements(request):
    from ..modules import statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    compare = request.arg("compare") != "0"
    return statements.full_set(conn, from_ad, to_ad, compare)


@route("GET", "/api/reports/cash-flow")
def cash_flow(request):
    from ..modules import statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    return statements.cash_flows(conn, from_ad, to_ad)


@route("GET", "/api/reports/equity")
def equity_statement(request):
    from ..modules import statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    return statements.changes_in_equity(conn, from_ad, to_ad)


@route("GET", "/api/reports/schedules")
def schedules(request):
    from ..modules import statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    compare = statements.previous_period(from_ad, to_ad) if request.arg("compare") != "0" else None
    return statements.schedules(conn, from_ad, to_ad, compare)


@route("GET", "/api/reports/discounts")
def discount_note(request):
    """The working from what was invoiced down to revenue, showing discounts."""
    from ..modules import statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    compare = statements.previous_period(from_ad, to_ad) if request.arg("compare") != "0" else None
    return statements.discount_note(conn, from_ad, to_ad, compare)


@route("POST", "/api/export/xlsx")
def export_xlsx(request):
    """
    Turn whatever is on the screen into an Excel workbook.

    The screen sends the table it is showing, so whatever can be looked at can
    be exported: a report, a register, a ledger, a list of entries. Amounts
    arrive as numbers and stay numbers, so they add up in Excel instead of
    sitting there as text with commas in them.

    The file comes back as text rather than as a download, because the same
    call has to work when the whole engine is running inside the browser with no
    web server underneath it at all. The screen turns it back into a file.
    """
    import base64
    from ..core import spreadsheet

    request.require_user()
    sheets = []
    for raw in request.body.get("sheets") or []:
        columns = [max(9, min(48, int(width or 14))) for width in (raw.get("widths") or [])]
        sheet = spreadsheet.Sheet(raw.get("name") or "Sheet", columns)
        for line in raw.get("title") or []:
            if line:
                sheet.add([(line, spreadsheet.STYLE_TITLE)])
        if raw.get("title"):
            sheet.blank()
        headings = raw.get("columns") or []
        if headings:
            sheet.add([(head, spreadsheet.STYLE_HEADING) for head in headings])
        for row in raw.get("rows") or []:
            cells = []
            for cell in row:
                if isinstance(cell, dict):
                    value = cell.get("v")
                    style = {"money": spreadsheet.STYLE_MONEY,
                             "qty": spreadsheet.STYLE_QUANTITY,
                             "date": spreadsheet.STYLE_DATE,
                             "total": spreadsheet.STYLE_TOTAL,
                             "head": spreadsheet.STYLE_HEADING}.get(cell.get("s"))
                    cells.append((value, style))
                else:
                    cells.append((cell, None))
            sheet.add(cells)
        sheets.append(sheet)

    if not sheets:
        raise ApiError("There is nothing on this screen to export.")
    data = spreadsheet.build(sheets)
    return {"filename": (request.body.get("filename") or "Saphal Book") + ".xlsx",
            "content": base64.b64encode(data).decode("ascii"),
            "bytes": len(data)}


# Carrying books between devices
#
# The signed in connection is held in memory against the browser session and
# nowhere else. It carries the key that opens the books, so writing it to disk
# would undo the point of locking them in the first place. Closing the app
# forgets it, which is why the password is asked for again.

_CLOUD_SESSIONS = {}


def _cloud_session(request, required=True):
    from ..core import cloud
    token = request.session["token"] if request.session else ""
    held = _CLOUD_SESSIONS.get(token)
    if held is None and required:
        raise ApiError("Sign in to your account first.", 409)
    return held


@route("GET", "/api/cloud/status")
def cloud_status(request):
    """Where every set of books stands against the server."""
    from ..core import cloud_config
    from ..modules import sync
    request.require_user()
    session = _cloud_session(request, required=False)
    found = sync.status(request.system, session)
    found["configured"] = cloud_config.configured(request.system)
    found["signed_in"] = bool(session and session.signed_in())
    row = request.system.execute("SELECT * FROM cloud_account WHERE id = 1").fetchone()
    found["remembered"] = row["username"] if row else ""
    return found


def _cloud_open(request, username, password, making_account):
    from ..core import cloud, cloud_config
    request.require_user()
    settings = cloud_config.settings(request.system)
    session = cloud.Cloud(settings["url"], settings["anon_key"])
    try:
        if making_account:
            session.sign_up(username, password)
        else:
            session.sign_in(username, password)
    except cloud.CloudError as exc:
        raise ApiError(str(exc))
    token = request.session["token"]
    _CLOUD_SESSIONS[token] = session
    request.system.execute(
        """INSERT INTO cloud_account (id, username, user_id, last_signed_in)
           VALUES (1, ?, ?, ?)
           ON CONFLICT (id) DO UPDATE SET username = excluded.username,
                                          user_id = excluded.user_id,
                                          last_signed_in = excluded.last_signed_in""",
        (session.username, session.user_id or "", db.now_stamp()))
    request.system.commit()
    return {"ok": True, "username": session.username}


@route("POST", "/api/cloud/sign-up")
def cloud_sign_up(request):
    """Open an account. The server refuses a username somebody already holds."""
    return _cloud_open(request, request.body.get("username", ""),
                       request.body.get("password", ""), True)


@route("POST", "/api/cloud/sign-in")
def cloud_sign_in(request):
    return _cloud_open(request, request.body.get("username", ""),
                       request.body.get("password", ""), False)


@route("POST", "/api/cloud/sign-out")
def cloud_sign_out(request):
    request.require_user()
    token = request.session["token"] if request.session else ""
    held = _CLOUD_SESSIONS.pop(token, None)
    if held:
        held.sign_out()
    return {"ok": True}


@route("POST", "/api/cloud/send")
def cloud_send(request):
    """Put this device's copy of one set of books on the server."""
    from ..core import cloud
    from ..modules import sync
    request.require_user()
    session = _cloud_session(request)
    slug = (request.body.get("slug") or "").strip()
    if not slug:
        raise ApiError("Say which books to send.")
    try:
        return sync.send_up(request.system, session, slug)
    except cloud.Conflict as exc:
        raise ApiError(
            "%s Bring it down first, or send anyway only if you are certain this "
            "device holds the work that matters." % str(exc), 409)
    except (cloud.CloudError, sync.SyncError) as exc:
        raise ApiError(str(exc))


@route("POST", "/api/cloud/bring-new")
def cloud_bring_new(request):
    """Fetch every set of books on the server this device has never seen."""
    from ..core import cloud
    from ..modules import sync
    request.require_user()
    session = _cloud_session(request)
    try:
        return sync.bring_new(request.system, session)
    except (cloud.CloudError, sync.SyncError) as exc:
        raise ApiError(str(exc))


@route("POST", "/api/close")
def close_the_software(request):
    """
    Stop the server.

    The window and the software are two different things: closing the window
    leaves the books served, which is what lets a phone on the same wifi go on
    reaching them. This is how somebody actually finishes for the day. A closing
    backup is taken on the way out, as it always was.
    """
    import os
    import signal
    import threading
    request.require_user()
    threading.Timer(0.4, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
    return {"ok": True,
            "note": "Saphal Book is closing. A backup is being taken as it goes."}


@route("POST", "/api/cloud/auto")
def cloud_auto(request):
    """
    Keep everything level with the server without being asked.

    Called when somebody signs in, every so often afterwards, and once things
    have gone quiet after an entry. Answers plainly when there is nothing to do,
    so the screen can stay silent rather than announcing itself.
    """
    from ..modules import sync
    request.require_user()
    session = _cloud_session(request, required=False)
    if session is None:
        return {"ran": False, "why": "not signed in"}
    return sync.auto(request.system, session)


@route("POST", "/api/cloud/bring")
def cloud_bring(request):
    """Replace this device's copy with the one on the server."""
    from ..core import cloud
    from ..modules import sync
    request.require_user()
    session = _cloud_session(request)
    slug = (request.body.get("slug") or "").strip()
    if not slug:
        raise ApiError("Say which books to bring down.")
    try:
        return sync.bring_down(request.system, session, slug)
    except (cloud.CloudError, sync.SyncError) as exc:
        raise ApiError(str(exc))


# Returns, notes and stock adjustments


@route("POST", "/api/vouchers/sales-return")
def create_sales_return(request):
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    voucher_id = _post(conn, request,
                       lambda: invoices.post_sales_return(conn, request.username(), payload))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("POST", "/api/vouchers/purchase-return")
def create_purchase_return(request):
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    voucher_id = _post(conn, request,
                       lambda: invoices.post_purchase_return(conn, request.username(), payload))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("POST", "/api/vouchers/credit-note")
def create_credit_note(request):
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    voucher_id = _post(conn, request,
                       lambda: invoices.post_note(conn, request.username(), payload, "credit_note"))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("POST", "/api/vouchers/debit-note")
def create_debit_note(request):
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    voucher_id = _post(conn, request,
                       lambda: invoices.post_note(conn, request.username(), payload, "debit_note"))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("GET", "/api/adjustment-reasons")
def adjustment_reasons(request):
    from ..modules import adjustments
    request.require_user()
    conn = request.company()
    out = []
    for code, label, direction, account_code in adjustments.REASONS:
        account = masters.account_by_code(conn, account_code)
        out.append({"code": code, "label": label, "direction": direction,
                    "account_code": account_code,
                    "account_name": account["name"] if account else account_code})
    return {"rows": out}


@route("POST", "/api/vouchers/stock-adjust/preview")
def preview_adjustment(request):
    from ..modules import adjustments
    request.require_user()
    conn = request.company()
    try:
        lines = adjustments.price_lines(conn, request.body.get("items"),
                                        request.arg("date_ad") or today())
    except adjustments.AdjustmentError as exc:
        raise ApiError(str(exc))
    return {"lines": lines,
            "total": sum(line["value"] * line["direction"] for line in lines)}


@route("POST", "/api/vouchers/stock-adjust")
def create_stock_adjustment(request):
    from ..modules import adjustments
    request.require("voucher.create")
    conn = request.company()
    payload = dict(request.body)
    with db.Transaction(conn):
        try:
            voucher_id = adjustments.post(conn, request.username(), payload)
        except (adjustments.AdjustmentError, ledger.PostingError) as exc:
            raise ApiError(str(exc))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("GET", "/api/vouchers/returnable")
def returnable_vouchers(request):
    """
    Invoices a return can be made against, so the lines can be pulled through
    rather than typed again.
    """
    conn = request.company()
    kind = request.arg("kind") or "sales"
    party_id = request.int_arg("party_id")
    sql = """SELECT v.id, v.number, v.date_ad, v.date_bs, v.total_paisa, p.name AS party_name
             FROM vouchers v LEFT JOIN parties p ON p.id = v.party_id
             WHERE v.status = 'posted' AND v.voucher_type = ?"""
    args = [kind]
    if party_id:
        sql += " AND v.party_id = ?"
        args.append(party_id)
    sql += " ORDER BY v.date_ad DESC, v.id DESC LIMIT 60"
    return {"rows": rows(conn.execute(sql, args))}


# Fixed assets and the schedules behind the accounts


def _fiscal_bs_year(request, conn):
    year = request.int_arg("bs_year")
    if year:
        return year
    fy = company_module.current_fiscal_year(conn)
    if fy:
        return fy["start_bs_year"]
    return nd.today_bs()[0]


@route("GET", "/api/tax-classes")
def tax_classes(request):
    from ..modules import schedules as sched
    request.require_user()
    return {"rows": [{"code": code, "description": description, "rate_bp": rate}
                     for code, description, rate in sched.TAX_CLASSES],
            "absorption": [{"months": list(m), "fraction": "%d/%d" % (n, d), "note": label}
                           for m, n, d, label in sched.ABSORPTION]}


@route("GET", "/api/assets")
def list_assets(request):
    from ..modules import schedules as sched
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    register = sched.asset_register(conn, from_ad, to_ad,
                                    include_disposed=request.arg("hide_disposed") != "1")
    register["accounts"] = rows(conn.execute(
        """SELECT a.id, a.code, a.name, g.code AS group_code
           FROM accounts a JOIN account_groups g ON g.id = a.group_id
           WHERE a.account_kind IN ('fixed_asset', 'contra_asset') AND a.active = 1
           ORDER BY a.code"""))
    return register


@route("POST", "/api/assets/create")
def create_asset(request):
    conn = request.company()
    request.require("master.create")
    body = request.body
    name = (body.get("name") or "").strip()
    account_id = body.get("asset_account_id")
    acquired = body.get("acquired_ad")
    if not name or not account_id or not acquired:
        raise ApiError("An asset needs a name, the ledger it sits in, and the date it was bought.")
    code = (body.get("code") or "").strip()
    if not code:
        count = conn.execute("SELECT COUNT(*) n FROM fixed_assets").fetchone()["n"]
        code = "FA%04d" % (count + 1)
        while conn.execute("SELECT 1 FROM fixed_assets WHERE code = ?", (code,)).fetchone():
            count += 1
            code = "FA%04d" % (count + 1)
    now = db.now_stamp()
    try:
        cur = conn.execute(
            """INSERT INTO fixed_assets (code, name, description, asset_account_id,
                    depreciation_account_id, expense_account_id, tax_class, acquired_ad,
                    acquired_bs, cost_paisa, book_method, book_rate_bp, useful_life_years,
                    residual_paisa, opening_cost_paisa, opening_accumulated_paisa,
                    opening_tax_wdv_paisa, location, serial_no, supplier, invoice_no,
                    active, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (code, name, body.get("description", ""), account_id,
             body.get("depreciation_account_id") or None,
             body.get("expense_account_id") or None,
             body.get("tax_class", "D"), acquired,
             nd.format_bs(nd.ad_to_bs(acquired), "numeric"),
             money.to_paisa(body.get("cost") or 0),
             body.get("book_method", "wdv"),
             money.rate_to_bp(body.get("book_rate") or 0),
             int(body.get("useful_life_years") or 0),
             money.to_paisa(body.get("residual") or 0),
             money.to_paisa(body.get("opening_cost") or 0),
             money.to_paisa(body.get("opening_accumulated") or 0),
             money.to_paisa(body.get("opening_tax_wdv") or 0),
             body.get("location", ""), body.get("serial_no", ""),
             body.get("supplier", ""), body.get("invoice_no", ""),
             body.get("notes", ""), now, now))
    except Exception as exc:
        raise ApiError(str(exc))
    audit.log(conn, request.username(), "asset.create", "fixed_assets", cur.lastrowid, code,
              "Asset %s added to the register." % name)
    return {"ok": True, "id": cur.lastrowid, "code": code}


@route("POST", "/api/assets/<asset_id>/update")
def update_asset(request, asset_id):
    conn = request.company()
    request.require("master.edit")
    before = conn.execute("SELECT * FROM fixed_assets WHERE id = ?", (asset_id,)).fetchone()
    if before is None:
        raise ApiError("That asset is not on the register.", 404)
    body = request.body
    plain = ("name", "description", "tax_class", "book_method", "location",
             "serial_no", "supplier", "invoice_no", "notes", "active",
             "asset_account_id", "depreciation_account_id", "expense_account_id",
             "useful_life_years")
    sets, args = [], []
    for field in plain:
        if field in body:
            sets.append("%s = ?" % field)
            args.append(body[field])
    for field, column in (("cost", "cost_paisa"), ("residual", "residual_paisa"),
                          ("opening_cost", "opening_cost_paisa"),
                          ("opening_accumulated", "opening_accumulated_paisa"),
                          ("opening_tax_wdv", "opening_tax_wdv_paisa")):
        if field in body:
            sets.append("%s = ?" % column)
            args.append(money.to_paisa(body[field]))
    if "book_rate" in body:
        sets.append("book_rate_bp = ?")
        args.append(money.rate_to_bp(body["book_rate"]))
    if "acquired_ad" in body and body["acquired_ad"]:
        sets.append("acquired_ad = ?")
        args.append(body["acquired_ad"])
        sets.append("acquired_bs = ?")
        args.append(nd.format_bs(nd.ad_to_bs(body["acquired_ad"]), "numeric"))
    if not sets:
        return {"ok": True}
    sets.append("updated_at = ?")
    args.append(db.now_stamp())
    args.append(asset_id)
    conn.execute("UPDATE fixed_assets SET %s WHERE id = ?" % ", ".join(sets), args)
    audit.log(conn, request.username(), "asset.update", "fixed_assets", int(asset_id),
              before["code"], "Asset %s changed." % before["name"], dict(before), dict(body))
    return {"ok": True}


@route("POST", "/api/assets/<asset_id>/dispose")
def dispose_asset(request, asset_id):
    conn = request.company()
    request.require("master.edit")
    asset = conn.execute("SELECT * FROM fixed_assets WHERE id = ?", (asset_id,)).fetchone()
    if asset is None:
        raise ApiError("That asset is not on the register.", 404)
    when = request.arg("disposed_ad")
    if not when:
        raise ApiError("Give the date it was sold or scrapped.")
    if when < asset["acquired_ad"]:
        raise ApiError("It cannot be disposed of before it was bought.")
    conn.execute("""UPDATE fixed_assets SET disposed_ad = ?, disposal_proceeds_paisa = ?,
                                            disposal_note = ?, updated_at = ?
                    WHERE id = ?""",
                 (when, money.to_paisa(request.arg("proceeds") or 0),
                  request.arg("note") or "", db.now_stamp(), asset_id))
    audit.log(conn, request.username(), "asset.dispose", "fixed_assets", int(asset_id),
              asset["code"], "Asset %s disposed of on %s." % (asset["name"], when))
    return {"ok": True}


@route("POST", "/api/assets/<asset_id>/delete")
def delete_asset(request, asset_id):
    conn = request.company()
    request.require("master.delete")
    asset = conn.execute("SELECT * FROM fixed_assets WHERE id = ?", (asset_id,)).fetchone()
    if asset is None:
        raise ApiError("That asset is not on the register.", 404)
    conn.execute("DELETE FROM fixed_assets WHERE id = ?", (asset_id,))
    audit.log(conn, request.username(), "asset.delete", "fixed_assets", int(asset_id),
              asset["code"], "Asset %s removed from the register." % asset["name"],
              dict(asset), None)
    return {"ok": True}


@route("GET", "/api/schedules/movement")
def movement_schedule(request):
    from ..modules import schedules as sched, statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    group_code = request.arg("group_code") or "1110"
    compare = statements.previous_period(from_ad, to_ad) if request.arg("compare") != "0" else None
    result = sched.movement_schedule(conn, group_code, from_ad, to_ad, compare)
    if result is None:
        raise ApiError("No such group.", 404)
    return result


@route("GET", "/api/schedules/tax-depreciation")
def tax_depreciation(request):
    from ..modules import schedules as sched
    conn = request.company()
    try:
        return sched.tax_depreciation(conn, _fiscal_bs_year(request, conn),
                                      request.arg("special_industry") == "1")
    except nd.DateRangeError as exc:
        raise ApiError(str(exc))


@route("GET", "/api/schedules/deferred-tax")
def deferred_tax(request):
    from ..modules import schedules as sched
    conn = request.company()
    year = _fiscal_bs_year(request, conn)
    compare = year - 1 if request.arg("compare") != "0" else None
    try:
        return sched.deferred_tax(conn, year, compare)
    except nd.DateRangeError as exc:
        raise ApiError(str(exc))


@route("GET", "/api/schedules/financial-instruments")
def financial_instruments(request):
    from ..modules import schedules as sched, statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    earlier = statements.previous_period(from_ad, to_ad) if request.arg("compare") != "0" else None
    return sched.financial_instruments(conn, to_ad, earlier["to_ad"] if earlier else None)


# Settling bills, and the discount that goes with it


@route("GET", "/api/open-bills")
def open_bills(request):
    from ..modules import settlements
    conn = request.company()
    _, to_ad = _dates(request, conn)
    party_id = request.int_arg("party_id")
    if not party_id:
        raise ApiError("Choose the party first.")
    side = request.arg("side") or "receivable"
    try:
        return settlements.open_bills(conn, party_id, side, request.arg("as_at") or to_ad)
    except settlements.SettlementError as exc:
        raise ApiError(str(exc))


@route("POST", "/api/vouchers/settle")
def settle(request):
    from ..modules import settlements
    request.require("voucher.create")
    conn = request.company()
    kind = request.arg("kind") or "receipt"
    payload = dict(request.body)
    with db.Transaction(conn):
        try:
            voucher_id = settlements.post(conn, request.username(), payload, kind)
        except (settlements.SettlementError, ledger.PostingError) as exc:
            raise ApiError(str(exc))
    return {"ok": True, "id": voucher_id, "voucher": _voucher_payload(conn, voucher_id)}


@route("GET", "/api/statement")
def party_statement(request):
    from ..modules import settlements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    party_id = request.int_arg("party_id")
    if not party_id:
        raise ApiError("Choose a customer or a supplier.")
    try:
        result = settlements.statement_of_account(conn, party_id, from_ad, to_ad)
    except settlements.SettlementError as exc:
        raise ApiError(str(exc))
    return result


# Audit tools


@route("GET", "/api/reports/stock-ageing")
def stock_ageing(request):
    conn = request.company()
    _, to_ad = _dates(request, conn)
    return reports.stock_ageing(conn, request.arg("as_at") or min(today(), to_ad))


@route("GET", "/api/audit/review")
def audit_review_run(request):
    from ..modules import audit_review, statements
    conn = request.company()
    from_ad, to_ad = _dates(request, conn)
    # Reviewing up to a date that has not happened yet reports things as missing
    # that simply have not been done, so the period is capped at today.
    to_ad = min(to_ad, today()) if to_ad > today() else to_ad
    compare = statements.previous_period(from_ad, to_ad) if request.arg("compare") != "0" else None
    return audit_review.review(conn, from_ad, to_ad, compare)


@route("POST", "/api/audit/trial-balance")
def read_trial_balance(request):
    from ..modules import tb_import
    request.require_user()
    text = request.body.get("text") or ""
    try:
        parsed = tb_import.parse(text)
    except tb_import.ImportError_ as exc:
        raise ApiError(str(exc))
    tb_import.suggest_mapping(parsed["lines"])
    parsed["summary"] = tb_import.summarise(parsed["lines"])
    parsed["groups"] = [{"code": g[0], "name": g[1], "statement": g[5], "section": g[6]}
                        for g in coa.GROUPS]
    parsed["review"] = _review_imported(parsed)
    return parsed


@route("POST", "/api/audit/trial-balance/remap")
def remap_trial_balance(request):
    from ..modules import tb_import
    request.require_user()
    lines = request.body.get("lines") or []
    if not lines:
        raise ApiError("Nothing to work on.")
    groups = {g[0]: g for g in coa.GROUPS}
    for line in lines:
        group = groups.get(line.get("group_code"))
        line["group_name"] = group[1] if group else line.get("group_code", "")
        line["balance"] = int(line.get("debit") or 0) - int(line.get("credit") or 0)
    summary = tb_import.summarise(lines)
    parsed = {
        "lines": lines,
        "total_debit": sum(int(l.get("debit") or 0) for l in lines),
        "total_credit": sum(int(l.get("credit") or 0) for l in lines),
        "summary": summary,
    }
    parsed["difference"] = parsed["total_debit"] - parsed["total_credit"]
    parsed["balanced"] = parsed["difference"] == 0
    parsed["review"] = _review_imported(parsed)
    return {"summary": summary, "review": parsed["review"],
            "balanced": parsed["balanced"], "difference": parsed["difference"]}


def _review_imported(parsed):
    """
    What can be said about a trial balance handed over on paper.

    Far less than about a full set of books, because there are no vouchers
    behind it, but the shape of it still says a good deal.
    """
    findings = []
    summary = parsed["summary"]

    def add(severity, title, detail, reference="", amount=0):
        findings.append({"severity": severity, "area": "Trial balance", "title": title,
                         "detail": detail, "reference": reference, "amount": amount,
                         "count": 0, "items": []})

    if not parsed.get("balanced", True):
        add("high", "The trial balance does not cast",
            "Debit and credit differ by %s. Everything below assumes that gets resolved."
            % money.format_money(abs(parsed["difference"])),
            "", abs(parsed["difference"]))

    unmapped = [l for l in parsed["lines"] if l.get("confidence") == "none"]
    if unmapped:
        add("medium", "Lines that could not be recognised",
            "%d line%s were not recognised from the name and have been put somewhere neutral. "
            "Set them properly before relying on the statements."
            % (len(unmapped), "" if len(unmapped) == 1 else "s"), "",
            sum(abs(l["balance"]) for l in unmapped))

    if summary["revenue"] and summary["gross_profit"] < 0:
        add("high", "Gross profit is negative",
            "Cost of sales exceeds revenue. Either closing stock is missing from the trial "
            "balance or something is misclassified.", "", -summary["gross_profit"])

    if summary["revenue"]:
        margin = summary["gross_profit"] * 100.0 / summary["revenue"]
        if margin > 60:
            add("medium", "The gross margin looks high",
                "A margin of %.1f percent is unusual for trade. Check that opening and closing "
                "stock are both in, and that nothing has been posted to the wrong side."
                % margin)
        elif 0 < margin < 3:
            add("medium", "The gross margin looks thin",
                "A margin of %.1f percent leaves nothing to cover overheads. Worth asking "
                "about." % margin)

    opening = sum(l["balance"] for l in parsed["lines"] if l.get("group_code") == "5300")
    closing = sum(l["balance"] for l in parsed["lines"] if l.get("group_code") == "1210")
    if opening and not closing:
        add("high", "Opening stock is in but closing stock is not",
            "Cost of sales, and so the profit, is overstated by whatever the closing stock "
            "comes to.", "NAS 02")

    if not summary["depreciation"]:
        owns = any(l.get("group_code") in ("1110", "1140") and l["balance"] > 0
                   for l in parsed["lines"])
        if owns:
            add("high", "Fixed assets but no depreciation",
                "The trial balance shows assets with nothing written off them.", "NAS 16")

    if not summary["tax"] and summary["profit_before_tax"] > 0:
        add("medium", "No tax charge against a profit",
            "A profit of %s is shown with no provision for income tax."
            % money.format_money(summary["profit_before_tax"]),
            "Income Tax Act, 2058", summary["profit_before_tax"])

    if not summary["balanced"]:
        add("high", "The statements do not balance after mapping",
            "Assets differ from equity and liabilities by %s once the profit is taken in. "
            "Usually a line mapped to the wrong side."
            % money.format_money(abs(summary["difference"])), "", abs(summary["difference"]))

    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), -abs(f["amount"])))
    counts = {level: sum(1 for f in findings if f["severity"] == level)
              for level in ("high", "medium", "low", "info")}
    return {"findings": findings, "counts": counts, "total": len(findings)}


@route("GET", "/api/reference")
def reference(request):
    from ..modules import guidance
    request.require_user()
    return {"sections": guidance.SECTIONS, "updated": guidance.LAST_REVIEWED}
