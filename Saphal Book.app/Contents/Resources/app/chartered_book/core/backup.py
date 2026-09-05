"""
Offline backup and restore.

A backup is a plain zip file written to data/backups. It contains a consistent
copy of every book plus the system file, taken with SQLite's own online backup
call, so a backup taken while the software is running is still sound.

Nothing is uploaded anywhere. Copy the zip to a pen drive or a second folder
and that is the whole disaster plan.
"""

import datetime
import os
import shutil
import sqlite3
import zipfile

from . import db, nepali_date as nd



def _safe_copy(source_path, target_path):
    """Copy a live SQLite database without risking a half written file."""
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


# How many days of backups to hold, here and in Drive. Enough to fall back
# on if today's turns out to contain the mistake, and few enough that the
# folder never becomes a list nobody reads.
KEEP_DAYS = 3


def create_backup(note="", kind="manual"):
    """Write a backup zip and return a description of it."""
    db.ensure_dirs()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bs = nd.format_bs(nd.today_bs(), "numeric")
    # One file a day, not one a press.
    #
    # The name used to carry the time, so pressing backup four times in an
    # afternoon left four files that differ by nothing anybody would want, and a
    # folder that only grows is a folder nobody opens. The name carries the day
    # only, so today's backup replaces today's backup.
    #
    # Not one file in total, though it was asked for that way. A backup taken
    # after a mistake would then be the only backup there is, and the mistake
    # would be the only thing kept. Three days are held: today, and two to fall
    # back on.
    name = "saphal_book_%s.zip" % datetime.datetime.now().strftime("%Y%m%d")
    target = os.path.join(db.BACKUP_DIR, name)
    staging = os.path.join(db.BACKUP_DIR, "_staging_%s" % stamp)
    os.makedirs(staging, exist_ok=True)
    try:
        copied = []
        if os.path.exists(db.SYSTEM_DB):
            _safe_copy(db.SYSTEM_DB, os.path.join(staging, "system.db"))
            copied.append("system.db")
        books_dir = os.path.join(staging, "books")
        os.makedirs(books_dir, exist_ok=True)
        for filename in sorted(os.listdir(db.BOOKS_DIR)):
            if not filename.endswith(".db"):
                continue
            _safe_copy(os.path.join(db.BOOKS_DIR, filename), os.path.join(books_dir, filename))
            copied.append("books/" + filename)

        readme = (
            "Saphal Book backup\n"
            "Taken on %s AD, %s BS\n"
            "Kind: %s\n"
            "Note: %s\n\n"
            "To restore, use Backup and Restore inside the software, or copy the\n"
            "files in this zip back into the data folder while the software is closed.\n"
            % (datetime.datetime.now().strftime("%d %b %Y %H:%M"), bs, kind, note or "none"))
        with open(os.path.join(staging, "README.txt"), "w", encoding="utf-8") as handle:
            handle.write(readme)

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for root, _dirs, files in os.walk(staging):
                for filename in files:
                    full = os.path.join(root, filename)
                    archive.write(full, os.path.relpath(full, staging))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # Every backup, not only the automatic ones. There is one file a day now,
    # so a backup taken by hand is today's backup rather than an extra one, and
    # the old days go the same way whoever asked for them.
    prune_automatic()
    info = describe(target)
    try:
        system = db.connect(db.SYSTEM_DB) if os.path.exists(db.SYSTEM_DB) else None
        if system is not None:
            system.execute("CREATE TABLE IF NOT EXISTS app_settings "
                           "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            info["copies"] = copy_to_destinations(target, get_destinations(system))
            # And straight up to Google Drive, where one is connected. The
            # folders above are copies onto this machine that something else
            # carries away; this one goes to Google itself, with nothing on the
            # machine in between to go wrong.
            sent = send_to_google(system, target)
            if sent is not None:
                info["copies"].append({"folder": "Google Drive", "ok": sent["ok"],
                                       "message": sent.get("message", "Uploaded.")})
            system.close()
    except Exception as exc:
        info["copies"] = [{"folder": "", "ok": False, "message": str(exc)}]
    return info


def describe(path):
    stat = os.stat(path)
    taken = datetime.datetime.fromtimestamp(stat.st_mtime)
    return {
        "filename": os.path.basename(path),
        "path": path,
        "size_bytes": stat.st_size,
        "size_text": human_size(stat.st_size),
        "taken_ad": taken.strftime("%Y-%m-%d %H:%M"),
        "taken_bs": nd.format_bs(nd.ad_to_bs(taken.date()), "long"),
        "kind": "automatic" if "_automatic_" in os.path.basename(path) else "manual",
    }


def human_size(count):
    for unit in ("bytes", "KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            return "%d %s" % (count, unit) if unit == "bytes" else "%.1f %s" % (count, unit)
        count /= 1024.0
    return "%d bytes" % count


def list_backups():
    db.ensure_dirs()
    out = []
    for filename in os.listdir(db.BACKUP_DIR):
        if filename.endswith(".zip"):
            out.append(describe(os.path.join(db.BACKUP_DIR, filename)))
    out.sort(key=lambda item: item["taken_ad"], reverse=True)
    return out


def prune_automatic(keep=KEEP_DAYS):
    """
    Keep the newest few days of backups and remove the rest.

    There is one file per day now, so this counts days rather than presses.
    Gives back how many were actually removed, so the screen can say.
    """
    everything = list_backups()
    removed = 0
    for old in everything[keep:]:
        try:
            os.remove(old["path"])
            removed += 1
        except OSError:
            pass
    return removed


def restore_backup(filename):
    """
    Put the books back from a backup.

    The current data folder is copied to a safety backup first, so a restore
    started by mistake can itself be undone.
    """
    path = os.path.join(db.BACKUP_DIR, os.path.basename(filename))
    if not os.path.isfile(path):
        raise FileNotFoundError("No backup named %s" % filename)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            if name.startswith("/") or ".." in name:
                raise ValueError("This backup file looks tampered with and was not opened.")
        safety = create_backup("Taken automatically before restoring %s" % os.path.basename(path),
                               "presafety")
        for name in names:
            if name == "system.db":
                archive.extract(name, db.DATA_DIR)
            elif name.startswith("books/") and name.endswith(".db"):
                archive.extract(name, db.DATA_DIR)
    # Stale write ahead logs would otherwise reintroduce the old contents.
    for folder in (db.DATA_DIR, db.BOOKS_DIR):
        for filename in os.listdir(folder):
            if filename.endswith("-wal") or filename.endswith("-shm"):
                try:
                    os.remove(os.path.join(folder, filename))
                except OSError:
                    pass
    return {"restored": os.path.basename(path), "safety_backup": safety["filename"]}


def read_backup(filename):
    """The bytes of a backup, so it can be handed to whoever asked for it."""
    path = os.path.join(db.BACKUP_DIR, os.path.basename(filename))
    if not os.path.isfile(path):
        raise FileNotFoundError("No backup named %s" % filename)
    with open(path, "rb") as handle:
        return handle.read()


def accept_backup(data, filename=""):
    """
    Take in a backup that came from somewhere else and put it with the rest.

    This is how a set of books moves between two machines that have no way of
    reaching one another. It is checked for being a real backup before it is
    written, so an unrelated zip, or a file that has been tampered with to write
    outside the folder, is refused rather than unpacked.
    """
    db.ensure_dirs()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = os.path.basename(filename or "").strip() or "brought_in.zip"
    if not safe.lower().endswith(".zip"):
        safe += ".zip"
    name = "saphal_book_brought_in_%s_%s" % (stamp, safe)
    target = os.path.join(db.BACKUP_DIR, name)

    with open(target, "wb") as handle:
        handle.write(data)
    try:
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            for entry in names:
                if entry.startswith("/") or ".." in entry:
                    raise ValueError(
                        "That file looks tampered with and was not opened.")
            if "system.db" not in names and not any(
                    n.startswith("books/") and n.endswith(".db") for n in names):
                raise ValueError(
                    "That is a zip file, but there are no books inside it. Choose the file "
                    "the other device produced under Back up now.")
    except zipfile.BadZipFile:
        os.remove(target)
        raise ValueError("That file is not a backup. Choose the .zip the other device made.")
    except ValueError:
        os.remove(target)
        raise
    return describe(target)


def export_folder():
    return db.BACKUP_DIR


# Extra destinations
#
# A backup sitting on the same disk protects you from a mistake, not from the
# disk failing. Naming a second folder means every backup is copied there as
# well. Point it at a Google Drive, OneDrive or Dropbox folder on this machine
# and the copy syncs itself the next time the machine is online, with no
# account to connect, no keys to expire and nothing to pay for.

def get_destinations(system_conn):
    row = system_conn.execute("SELECT value FROM app_settings WHERE key = 'backup_destinations'"
                              ).fetchone()
    if not row or not row["value"]:
        return []
    return [line for line in row["value"].split("\n") if line.strip()]


def set_destinations(system_conn, folders):
    cleaned = []
    problems = []
    for folder in folders or []:
        folder = os.path.expanduser(str(folder).strip())
        if not folder:
            continue
        if not os.path.isdir(folder):
            # A folder that is not there yet is not a mistake. Somebody naming
            # where they want the copies kept expects it to be made for them.
            parent = os.path.dirname(folder.rstrip(os.sep))
            if not os.path.isdir(parent):
                problems.append("%s is not a folder on this computer." % folder)
                continue
            try:
                os.makedirs(folder)
            except OSError as exc:
                problems.append("%s could not be made. %s" % (folder, exc))
                continue
        # Actually put a file there and take it away again, rather than asking
        # the operating system whether it thinks we could. A folder that lives
        # on a cloud service is not a real disk and will happily say yes and
        # then refuse, which is how somebody gets told their own Drive cannot be
        # written to when the truth is that only its top level cannot.
        if not _writable(folder):
            problems.append(
                "%s cannot be written to. If this is Google Drive, choose the folder "
                "inside it rather than the account itself." % folder)
            continue
        cleaned.append(folder)
    system_conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('backup_destinations', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", ("\n".join(cleaned),))
    return cleaned, problems


def google_settings(system_conn):
    """The permission Google gave, if the owner has connected a Drive."""
    held = {row["key"]: row["value"] for row in system_conn.execute(
        "SELECT key, value FROM app_settings WHERE key LIKE 'gdrive_%'")}
    if not held.get("gdrive_refresh_token"):
        return None
    return {"client_id": held.get("gdrive_client_id", ""),
            "client_secret": held.get("gdrive_client_secret", ""),
            "refresh_token": held["gdrive_refresh_token"],
            # The folder the owner chose, by the name Google files it under. A
            # name is not enough: this software can only see folders it made
            # itself, so it would never find somebody's own folder by looking.
            "folder_id": held.get("gdrive_folder_id", ""),
            "folder_name": held.get("gdrive_folder_name") or "Saphal Book backups",
            "account": held.get("gdrive_account", ""),
            "keep": int(held.get("gdrive_keep") or 20)}


def google_account(system_conn):
    """Which Google account the backups go to, asked of Google rather than assumed."""
    from . import gdrive
    settings = google_settings(system_conn)
    if settings is None:
        return ""
    try:
        token = gdrive.access_token(settings["client_id"], settings["client_secret"],
                                    settings["refresh_token"])
        who = gdrive._call(token, "https://www.googleapis.com/drive/v3/about?fields=user")
        return who.get("user", {}).get("emailAddress", "")
    except Exception:                                               # noqa: BLE001
        return settings.get("account", "")


def send_to_google(system_conn, zip_path):
    """
    Put one backup into Google Drive, directly.

    Not through the Google Drive application, which keeps a copy of the whole of
    somebody's Drive on their machine and reconciles it in both directions. One
    file goes up and nothing comes down. The permission is the narrow one, so
    this can see the backups it put there and nothing else in the Drive.
    """
    from . import gdrive
    settings = google_settings(system_conn)
    if settings is None:
        return None
    try:
        token = gdrive.access_token(settings["client_id"], settings["client_secret"],
                                    settings["refresh_token"])
        folder = settings["folder_id"] or gdrive.ensure_folder(
            token, settings["folder_name"])
        sent = gdrive.upload(token, zip_path, folder)
        removed = gdrive.tidy(token, folder, KEEP_DAYS)
        return {"ok": True, "name": sent.get("name"), "removed": removed,
                "where": "Google Drive"}
    except Exception as exc:                                        # noqa: BLE001
        # A backup that reached the disk is still a backup. Never let the upload
        # failing take the whole thing down with it.
        return {"ok": False, "message": str(exc), "where": "Google Drive"}


# What a backup this software wrote is called. Nothing outside this pattern is
# ever touched by the tidying below, so a folder shared with somebody's own
# files stays exactly as they left it.
BACKUP_PREFIX = "saphal_book_"


def tidy_folder(folder, keep=None):
    """
    Keep the newest few backups in one folder and remove the rest.

    Only files this software wrote are considered, matched on the name it gives
    them. Anything else in the folder is none of its business.
    """
    keep = KEEP_DAYS if keep is None else keep
    if not os.path.isdir(folder):
        return 0
    ours = []
    for name in os.listdir(folder):
        if not (name.startswith(BACKUP_PREFIX) and name.endswith(".zip")):
            continue
        full = os.path.join(folder, name)
        try:
            ours.append((os.path.getmtime(full), full))
        except OSError:
            continue
    ours.sort(reverse=True)
    removed = 0
    for _when, full in ours[keep:]:
        try:
            os.remove(full)
            removed += 1
        except OSError:
            pass
    return removed


def copy_to_destinations(zip_path, folders):
    """
    Copy a finished backup to each extra folder, and tidy that folder after.

    The tidying was missing, so the main folder held three and a cloud folder
    beside it had nineteen going back over days, all of them nearly identical.
    A folder that only grows is a folder nobody opens, and on a cloud folder it
    is somebody's storage quota as well.

    A failure never loses the backup: the copy that matters is already written.
    """
    results = []
    for folder in folders or []:
        try:
            # Make the folder if it is not there. A cloud folder chosen from the
            # list has a name of ours on the end, so the backups sit together
            # instead of loose among somebody's own files.
            if not os.path.isdir(folder):
                os.makedirs(folder)
            target = os.path.join(folder, os.path.basename(zip_path))
            shutil.copy2(zip_path, target)
            dropped = tidy_folder(folder)
            results.append({"folder": folder, "ok": True,
                            "message": "Copied." if not dropped else
                            "Copied, and %d older one%s cleared."
                            % (dropped, "" if dropped == 1 else "s")})
        except OSError as exc:
            results.append({"folder": folder, "ok": False, "message": str(exc)})
    return results


# Which program has to be running for a folder to actually reach the internet.
# A folder belonging to a cloud service is only a folder. Something has to be
# running to carry what is put in it upwards, and where that something has been
# uninstalled the folder stays behind looking exactly as it did. Files written
# into it then sit there forever while everybody believes they are safe.
SYNC_AGENTS = (
    # Named exactly. An earlier attempt matched FileProvider as well, which is
    # part of macOS and always running, so a Drive that had been uninstalled
    # still reported itself as working. A check that cannot fail is not a check.
    ("googledrive", "Google Drive", ("Google Drive", "FinderSyncExt")),
    ("google drive", "Google Drive", ("Google Drive", "FinderSyncExt")),
    ("onedrive", "OneDrive", ("OneDrive",)),
    ("dropbox", "Dropbox", ("Dropbox",)),
    ("icloud", "iCloud Drive", ("bird",)),
    ("mobile documents", "iCloud Drive", ("bird",)),
)


def _running_programs():
    """The names of the programs running on this machine, lowercased."""
    import subprocess
    try:
        out = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True,
                             timeout=8).stdout
    except Exception:
        return None
    return out.lower()


def sync_state(path, running=None):
    """
    Whether anything is actually carrying this folder to the internet.

    Returns the name of the service and whether its program is running. Where
    the folder is an ordinary one on this disk, nothing is claimed either way.
    """
    lowered = path.lower()
    service = None
    markers = ()
    for needle, name, processes in SYNC_AGENTS:
        if needle in lowered:
            service, markers = name, processes
            break
    if service is None:
        return {"service": "", "syncing": None,
                "note": "An ordinary folder on this computer."}
    if running is None:
        running = _running_programs()
    if running is None:
        return {"service": service, "syncing": None, "note": ""}
    alive = any(marker.lower() in running for marker in markers)
    return {
        "service": service,
        "syncing": alive,
        "note": "" if alive else
                "%s is not running on this computer, so anything put in this folder stays "
                "on this machine and never reaches the internet." % service,
    }


def _writable(path):
    """Whether a folder will actually accept a file, rather than merely existing."""
    probe = os.path.join(path, ".saphal-book-write-test")
    try:
        with open(probe, "w") as handle:
            handle.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def _usable_inside(path):
    """
    The folder a cloud service really wants files put into.

    Google Drive mounts its account folder read only and keeps the writable part
    one level down, in My Drive. Offering the folder that exists rather than the
    folder that works is how somebody ends up being told their own Drive cannot
    be written to.
    """
    if _writable(path):
        return path
    for inside in ("My Drive", "MyDrive", "Documents"):
        candidate = os.path.join(path, inside)
        if os.path.isdir(candidate) and _writable(candidate):
            return candidate
    return None


def likely_cloud_folders():
    """
    Folders on this machine that a cloud service keeps in step with the internet.

    Only folders that can genuinely be written to are offered. A folder that
    cannot take a file is not a place to keep a backup, however promising its
    name, and offering it only wastes somebody's afternoon.
    """
    home = os.path.expanduser("~")
    candidates = [
        ("Google Drive", os.path.join(home, "Google Drive")),
        ("Google Drive", os.path.join(home, "Library", "CloudStorage")),
        ("Google Drive", os.path.join(home, "GoogleDrive")),
        ("OneDrive", os.path.join(home, "OneDrive")),
        ("Dropbox", os.path.join(home, "Dropbox")),
        ("iCloud Drive", os.path.join(home, "Library", "Mobile Documents",
                                      "com~apple~CloudDocs")),
    ]
    found = []
    seen = set()

    def offer(label, path):
        usable = _usable_inside(path)
        if usable and usable not in seen:
            seen.add(usable)
            # A folder of our own inside it, so a year of backups does not end
            # up scattered through somebody's Drive.
            found.append({"label": label,
                          "path": os.path.join(usable, "Saphal Book backups")})

    for label, path in candidates:
        if not os.path.isdir(path) or path in seen:
            continue
        seen.add(path)
        if os.path.basename(path) == "CloudStorage":
            # macOS puts each connected account in its own folder under here.
            try:
                for entry in sorted(os.listdir(path)):
                    full = os.path.join(path, entry)
                    if os.path.isdir(full):
                        offer(entry, full)
            except OSError:
                pass
            continue
        offer(label, path)
    return found


# Carrying the Google connection between a person's devices


GOOGLE_KEYS = ("gdrive_client_id", "gdrive_client_secret", "gdrive_refresh_token",
               "gdrive_folder_id", "gdrive_folder_name", "gdrive_account")


def _remember_google(system_conn, details):
    for key in GOOGLE_KEYS:
        if details.get(key) is None:
            continue
        system_conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(details[key])))
    system_conn.commit()


def publish_google_link(system_conn, session):
    """
    Send this machine's Google connection up, so the person's other devices get it.

    Called after somebody connects a Drive. Without it the connection would
    belong to whichever machine happened to be in front of them that day, and
    every other device would have to be walked through Google's consent screens
    again.
    """
    from . import cloud
    settings = google_settings(system_conn)
    if settings is None or session is None or not session.signed_in():
        return None
    details = {
        "gdrive_client_id": settings["client_id"],
        "gdrive_client_secret": settings["client_secret"],
        "gdrive_refresh_token": settings["refresh_token"],
        "gdrive_folder_id": settings["folder_id"],
        "gdrive_folder_name": settings["folder_name"],
        "gdrive_account": google_account(system_conn),
    }
    cloud.save_linked_account(session, details)
    return details["gdrive_account"]


def sync_google_link(system_conn, session):
    """
    Make this device's Google connection and the account's agree.

    It used to only ever be pulled down, and only at the moment somebody signed
    in. That left two ways to end up with a tablet saying no Google account is
    connected while the shop machine was backing up to Drive quite happily: the
    machine that had the connection never sent it up, or the tablet had signed
    in on some earlier day and never asked again.

    So it goes both ways now, and it is safe to call as often as it is useful.
    Whichever side has the connection gives it to the other, and where both
    have one, the one on this device is left alone.
    """
    if session is None or not session.signed_in():
        return None
    if google_settings(system_conn) is not None:
        try:
            return publish_google_link(system_conn, session)
        except Exception:                                           # noqa: BLE001
            return None
    try:
        return adopt_google_link(system_conn, session)
    except Exception:                                               # noqa: BLE001
        return None


def adopt_google_link(system_conn, session):
    """
    Take the Google connection this person set up elsewhere.

    Run when somebody signs in to their account. A tablet that has never seen
    Google before ends up backing up to the same Drive as the shop machine,
    because the connection followed the person rather than staying on the
    machine.

    Anything already set up on this machine is left alone, so a deliberate
    choice made here is not quietly replaced by one made somewhere else.
    """
    from . import cloud
    if session is None or not session.signed_in():
        return None
    if google_settings(system_conn) is not None:
        return None
    try:
        details = cloud.linked_account(session)
    except cloud.CloudError:
        return None
    if not details or not details.get("gdrive_refresh_token"):
        return None
    _remember_google(system_conn, details)
    return details.get("gdrive_account", "")
