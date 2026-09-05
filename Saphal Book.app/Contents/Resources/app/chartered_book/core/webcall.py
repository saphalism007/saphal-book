"""
One request, from whichever kind of machine this happens to be.

On a computer this is urllib and nothing more. Inside a browser it cannot be,
because there the software is Python compiled to WebAssembly and WebAssembly
has no sockets: urllib has nothing to talk through and every call fails before
it leaves. The request has to be handed to the browser itself.

This was learned once already, for the account, and then not applied to Google
Drive, which went on using urllib. So on a tablet the backup button reported
success, wrote a file into the browser's own storage, and quietly failed to send
anything to Drive. A backup that says it worked and did not is worse than no
backup button at all, because somebody stops worrying.

The browser request is made the blocking way on purpose. Every caller is
ordinary top to bottom Python that expects an answer before the next line, and
taking a backup is a deliberate act with a message on the screen rather than
something happening quietly while somebody types.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 30


class CallFailed(Exception):
    """The request could not be made at all. Not the same as being refused."""


def in_browser():
    """Whether this is running as WebAssembly inside a browser."""
    import sys
    return sys.platform == "emscripten"


def call(url, method="GET", data=None, headers=None, timeout=TIMEOUT):
    """
    Make one request and give back (status, body as bytes).

    A refusal comes back as its status and body, the same as an acceptance,
    because the caller usually wants to read the reason. Only being unable to
    reach anything at all raises.
    """
    headers = dict(headers or {})
    if in_browser():
        return _browser(url, method, data, headers)
    return _machine(url, method, data, headers, timeout)


def call_json(url, method="GET", data=None, headers=None, timeout=TIMEOUT):
    """The same, with the body read as JSON where it is JSON."""
    status, raw = call(url, method, data, headers, timeout)
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
    if not text.strip():
        return status, None
    try:
        return status, json.loads(text)
    except ValueError:
        return status, {"message": text[:300]}


def _machine(url, method, data, headers, timeout):
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        answer = urllib.request.urlopen(request, timeout=timeout)
        return answer.status, answer.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except urllib.error.URLError as error:
        raise CallFailed("Could not reach %s. Check the internet connection. (%s)"
                         % (_host(url), error.reason))


def _browser(url, method, data, headers):
    try:
        from js import XMLHttpRequest
    except ImportError:
        raise CallFailed("This browser will not let Saphal Book reach %s." % _host(url))

    xhr = XMLHttpRequest.new()
    try:
        xhr.open(method, url, False)
        # No responseType here, and this is not an oversight. A blocking request
        # is forbidden from asking for anything but text, and setting it throws
        # rather than being ignored, which is how the first version of this
        # failed on every call. Everything read back is JSON, so text is right.
        # Sending bytes is the direction that matters, and that is allowed.
        for name, value in headers.items():
            xhr.setRequestHeader(name, value)
        xhr.send(_as_js(data) if data is not None else None)
    except Exception as error:                                      # noqa: BLE001
        raise CallFailed("Could not reach %s. Check the internet connection. (%s)"
                         % (_host(url), error))

    status = int(xhr.status or 0)
    if status == 0:
        raise CallFailed("Could not reach %s. Check the internet connection." % _host(url))
    return status, (xhr.responseText or "").encode("utf-8")


def _as_js(data):
    """Hand a body to the browser: text as text, bytes as a byte array."""
    if isinstance(data, str):
        return data
    from js import Uint8Array
    buffer = Uint8Array.new(len(data))
    buffer.assign(data)
    return buffer


def _host(url):
    try:
        return urllib.parse.urlparse(url).netloc or url
    except Exception:                                               # noqa: BLE001
        return url
