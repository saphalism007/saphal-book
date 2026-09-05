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

KEEP_AUTOMATIC = 30


def _safe_copy(source_path, target_path):
    """Copy a live SQLite database without risking a half written file."""
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def create_backup(note="", kind="manual"):
    """Write a backup zip and return a description of it."""
    db.ensure_dirs()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bs = nd.format_bs(nd.today_bs(), "numeric")
    name = "saphal_book_%s_%s.zip" % (kind, stamp)
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

    if kind == "automatic":
        prune_automatic()
    info = describe(target)
    try:
        system = db.connect(db.SYSTEM_DB) if os.path.exists(db.SYSTEM_DB) else None
        if system is not None:
            system.execute("CREATE TABLE IF NOT EXISTS app_settings "
                           "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            info["copies"] = copy_to_destinations(target, get_destinations(system))
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


def prune_automatic(keep=KEEP_AUTOMATIC):
    """
    Remove the older automatic backups, keeping the newest few.

    Anything taken by hand is left alone, because somebody meant to take it.
    Gives back how many were actually removed, so the screen can say.
    """
    automatic = [b for b in list_backups() if b["kind"] != "manual"]
    removed = 0
    for old in automatic[keep:]:
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


def copy_to_destinations(zip_path, folders):
    """Copy a finished backup to each extra folder. A failure never loses the backup."""
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
            results.append({"folder": folder, "ok": True, "message": "Copied."})
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
