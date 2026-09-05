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
import urllib.error
import urllib.parse
import urllib.request

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
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        answer = urllib.request.urlopen(request, timeout=TIMEOUT)
        return json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body)
        except ValueError:
            detail = {"error_description": body[:300]}
        raise DriveError(detail.get("error_description") or detail.get("error")
                         or "Google refused the request.")
    except urllib.error.URLError as error:
        raise DriveError("Could not reach Google. Check the internet connection. (%s)"
                         % error.reason)


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
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", "Bearer " + token)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        answer = urllib.request.urlopen(request, timeout=TIMEOUT)
        raw = answer.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body).get("error", {}).get("message")
        except ValueError:
            detail = body[:300]
        raise DriveError(detail or "Google refused the request.")
    except urllib.error.URLError as error:
        raise DriveError("Could not reach Google. (%s)" % error.reason)


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


def upload(token, path, folder_id=None, name=None):
    """Send one file up. Nothing else on the machine is read or changed."""
    import os
    name = name or os.path.basename(path)
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

    request = urllib.request.Request(
        UPLOAD_URL + "?uploadType=multipart&fields=id,name,size", data=body, method="POST")
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("Content-Type", "multipart/related; boundary=%s" % boundary)
    try:
        answer = urllib.request.urlopen(request, timeout=TIMEOUT * 4)
        return json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw).get("error", {}).get("message")
        except ValueError:
            detail = raw[:300]
        raise DriveError(detail or "Google would not take the file.")
    except urllib.error.URLError as error:
        raise DriveError("Could not reach Google. (%s)" % error.reason)


def tidy(token, folder_id, keep=20):
    """
    Keep the newest few backups in Drive and remove the rest.

    Only files this software put there are visible to it, so nothing else can
    be caught by this.
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
