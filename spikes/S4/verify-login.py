#!/usr/bin/env python3
"""Spike S4 helper: confirm a legitimate login still works.

Registers a fresh, throwaway user through Juice Shop's own registration
API, then logs in with the right password (expect success) and the wrong
password (expect 401). Used after the manual fix, so we are not just
checking that the exploit fails -- we check that normal login still
works too.

Exit 0 if both checks pass. Thrown away with the rest of spikes/S4/.
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("TARGET_URL", "http://target:3000")
EMAIL = f"s4-{uuid.uuid4().hex[:12]}@example.invalid"
PASSWORD = "S4-spike-" + uuid.uuid4().hex[:10]


def _call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except urllib.error.URLError as e:
        return None, {"error": str(e)}


def main():
    status, _ = _call("POST", "/api/Users", {
        "email": EMAIL, "password": PASSWORD,
        "securityQuestion": None, "securityAnswer": "n/a",
    })
    print(f"[register] {EMAIL} -> {status}")
    if status not in (200, 201):
        print("RESULT: 2 (could not register a test user)")
        return 2

    status, body = _call("POST", "/rest/user/login", {"email": EMAIL, "password": PASSWORD})
    ok_correct = status == 200 and bool((body or {}).get("authentication", {}).get("token"))
    print(f"[login, correct password] -> {status}, ok={ok_correct}")

    status, _ = _call("POST", "/rest/user/login", {"email": EMAIL, "password": "wrong-" + PASSWORD})
    ok_wrong = status == 401
    print(f"[login, wrong password] -> {status}, ok={ok_wrong}")

    if ok_correct and ok_wrong:
        print("RESULT: 0 (a legitimate login still works, and a wrong password is still rejected)")
        return 0
    print("RESULT: 1 (legitimate-login check failed)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
