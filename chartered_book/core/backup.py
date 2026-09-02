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
    name = "chartered_book_%s_%s.zip" % (kind, stamp)
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
            "Chartered Book backup\n"
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
    automatic = [b for b in list_backups() if b["kind"] == "automatic"]
    for old in automatic[keep:]:
        try:
            os.remove(old["path"])
        except OSError:
            pass


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
            problems.append("%s is not a folder on this computer." % folder)
            continue
        if not os.access(folder, os.W_OK):
            problems.append("%s cannot be written to." % folder)
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
            target = os.path.join(folder, os.path.basename(zip_path))
            shutil.copy2(zip_path, target)
            results.append({"folder": folder, "ok": True, "message": "Copied."})
        except OSError as exc:
            results.append({"folder": folder, "ok": False, "message": str(exc)})
    return results


def likely_cloud_folders():
    """Folders on this machine that a cloud service keeps in step with the internet."""
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
    for label, path in candidates:
        if not os.path.isdir(path) or path in seen:
            continue
        seen.add(path)
        if os.path.basename(path) == "CloudStorage":
            # macOS puts each connected account in its own folder under here.
            try:
                for entry in sorted(os.listdir(path)):
                    full = os.path.join(path, entry)
                    if os.path.isdir(full) and full not in seen:
                        seen.add(full)
                        found.append({"label": entry, "path": full})
            except OSError:
                pass
            continue
        found.append({"label": label, "path": path})
    return found
