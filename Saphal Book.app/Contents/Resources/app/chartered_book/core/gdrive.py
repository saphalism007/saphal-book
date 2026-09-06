"""
Putting a backup into Google Drive, without the Google Drive application.

The application that Google supplies keeps a copy of the whole of somebody's
Drive on their machine and reconciles the two in both directions forever. That
is a great deal of machinery for what is wanted here, which is to put one small
file into one folder once a day, and when it goes wrong it goes wrong across
everything at once.

This talks to Google directly instead. One file goes up. Nothing comes down,
nothing is mirrored, nothing on the disk is touched.

The permission asked for is the narrow one, drive.file. It allows this software
to create files and to see the files it created, and nothing else. It cannot
read, change or delete anything else in the owner's Drive, which is the whole
point after what happened when the full application was tried.
"""

import json
import time
import urllib.parse

from . import webcall

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FILES_URL = "https://www.googleapis.com/drive/v3/files"

# Create files, and see only the files created here. Nothing else in the Drive.
SCOPE = "https://www.googleapis.com/auth/drive.file"

TIMEOUT = 60


class DriveError(Exception):
    """Raised when Google will not do what was asked."""


def _post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    try:
        status, detail = webcall.call_json(
            url, "POST", data,
            {"Content-Type": "application/x-www-form-urlencoded"}, TIMEOUT)
    except webcall.CallFailed as error:
        raise DriveError(str(error))
    if status >= 400:
        detail = detail or {}
        raise DriveError(detail.get("error_description") or detail.get("error")
                         or "Google refused the request.")
    return detail or {}


def consent_url(client_id, redirect_uri):
    """The address the owner visits to say yes."""
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        # Force the consent screen, because Google only hands back the lasting
        # permission the first time somebody agrees, and without it a second
        # attempt looks like it worked and then stops in an hour.
        "prompt": "consent",
    })


def exchange_code(client_id, client_secret, code, redirect_uri):
    """Turn the one time code from the browser into a lasting permission."""
    answer = _post_form(TOKEN_URL, {
        "client_id": client_id, "client_secret": client_secret,
        "code": code, "grant_type": "authorization_code",
        "redirect_uri": redirect_uri})
    if not answer.get("refresh_token"):
        raise DriveError(
            "Google gave permission for an hour but not a lasting one. This happens "
            "when the same account has already agreed before. Remove Saphal Book at "
            "myaccount.google.com under Data and privacy, then try again.")
    return answer


def access_token(client_id, client_secret, refresh_token):
    """A short lived key for one conversation, made from the lasting permission."""
    answer = _post_form(TOKEN_URL, {
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token"})
    if not answer.get("access_token"):
        raise DriveError("Google would not give a key. The permission may have been "
                         "withdrawn.")
    return answer["access_token"]


def _call(token, url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    send = {"Authorization": "Bearer " + token}
    if data is not None:
        send["Content-Type"] = "application/json"
    send.update(headers or {})
    try:
        status, detail = webcall.call_json(url, method, data, send, TIMEOUT)
    except webcall.CallFailed as error:
        raise DriveError(str(error))
    if status >= 400:
        message = ""
        if isinstance(detail, dict):
            message = (detail.get("error") or {}).get("message") if isinstance(
                detail.get("error"), dict) else detail.get("message", "")
        raise DriveError(message or "Google refused the request.")
    return detail or {}


def ensure_folder(token, name, parent=None):
    """
    Find the folder this software keeps its backups in, or make it.

    Only folders this software made are visible to it, so this never stumbles
    into somebody's own folder of the same name.
    """
    query = ("mimeType = 'application/vnd.google-apps.folder' and trashed = false "
             "and name = '%s'" % name.replace("'", "\\'"))
    if parent:
        query += " and '%s' in parents" % parent
    found = _call(token, FILES_URL + "?" + urllib.parse.urlencode({
        "q": query, "fields": "files(id,name)", "pageSize": "10"}))
    files = found.get("files") or []
    if files:
        return files[0]["id"]
    made = _call(token, FILES_URL + "?fields=id", "POST", {
        "name": name, "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent] if parent else []})
    return made["id"]


def find_by_name(token, name, folder_id):
    """The id of a file this software already put there under that name."""
    query = "name = '%s' and trashed = false" % name.replace("'", "\\'")
    if folder_id:
        query += " and '%s' in parents" % folder_id
    found = _call(token, FILES_URL + "?" + urllib.parse.urlencode({
        "q": query, "fields": "files(id,name)", "pageSize": "10"}))
    files = found.get("files") or []
    return files[0]["id"] if files else None


def upload(token, path, folder_id=None, name=None):
    """
    Send one file up, replacing what is there under the same name.

    Drive is happy to keep several files with identical names in one folder, so
    sending today's backup twice used to leave two of them, and then three.
    Today's backup replaces today's backup: the file that is already there is
    updated in place, keeping its own id and its own link.
    """
    import os
    name = name or os.path.basename(path)
    existing = None
    try:
        existing = find_by_name(token, name, folder_id)
    except DriveError:
        existing = None
    with open(path, "rb") as handle:
        payload = handle.read()

    boundary = "saphalbook%d" % int(time.time() * 1000)
    meta = {"name": name}
    if folder_id:
        meta["parents"] = [folder_id]
    body = (
        ("--%s\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" % boundary).encode()
        + json.dumps(meta).encode("utf-8")
        + ("\r\n--%s\r\nContent-Type: application/zip\r\n\r\n" % boundary).encode()
        + payload
        + ("\r\n--%s--\r\n" % boundary).encode())

    if existing:
        # Replacing: the parent is already set and Drive refuses to be told it
        # again on an update.
        meta.pop("parents", None)
        body = (
            ("--%s\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" % boundary).encode()
            + json.dumps(meta).encode("utf-8")
            + ("\r\n--%s\r\nContent-Type: application/zip\r\n\r\n" % boundary).encode()
            + payload
            + ("\r\n--%s--\r\n" % boundary).encode())
        where = UPLOAD_URL + "/" + existing + "?uploadType=multipart&fields=id,name,size"
        how = "PATCH"
    else:
        where = UPLOAD_URL + "?uploadType=multipart&fields=id,name,size"
        how = "POST"

    try:
        status, answer = webcall.call_json(
            where, how, body,
            {"Authorization": "Bearer " + token,
             "Content-Type": "multipart/related; boundary=%s" % boundary},
            TIMEOUT * 4)
    except webcall.CallFailed as error:
        raise DriveError(str(error))
    if status >= 400:
        message = ""
        if isinstance(answer, dict):
            message = (answer.get("error") or {}).get("message") if isinstance(
                answer.get("error"), dict) else answer.get("message", "")
        raise DriveError(message or "Google would not take the file.")
    return answer or {}


def tidy(token, folder_id, keep=30):
    """
    Keep the newest backups in Drive and remove the rest.

    Clicking backup twice in a day is dealt with by the upload, which replaces
    that day's file rather than adding another. What this removes is old days,
    and it keeps a month of them.

    This is deliberately generous, because the thing it is guarding against is
    a mistake that is not noticed the same afternoon. A wrong opening balance
    or a deleted party can sit there for a fortnight before anybody sees it,
    and a backup history that only goes back to yesterday is no use at all
    then. A month of these is under 4 MB.

    Only files this software put there are visible to it, because the access
    asked for is drive.file, which is per file. Nothing else in the Drive can
    be seen by this, let alone caught by it.
    """
    found = _call(token, FILES_URL + "?" + urllib.parse.urlencode({
        "q": "'%s' in parents and trashed = false" % folder_id,
        "orderBy": "createdTime desc", "fields": "files(id,name,createdTime)",
        "pageSize": "200"}))
    files = found.get("files") or []
    removed = 0
    for old in files[keep:]:
        try:
            _call(token, FILES_URL + "/" + old["id"], "DELETE")
            removed += 1
        except DriveError:
            pass
    return removed
