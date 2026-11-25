"""A legitimate login against the throwaway build in the verify step (M2-8).

Why: an attack that fails proves little if the fix also broke every login. This waits for the app to answer,
then logs in with Juice Shop's documented default admin account and checks that a token comes back.
It is not exploit logic. It reuses the exploit's host rule: only the app's own compose service name is allowed
(it is a network alias of the throwaway container, on the throwaway network).

Exit code: 0 login works, 1 login refused, 2 the app never answered, 3 target refused.
The token is never stored or printed, only whether one came back.

    python -m agents.verify_agent.login_check [--target URL] [--wait SECONDS] [--out FILE]
"""
import argparse
import json
import sys
import time
from pathlib import Path

from agents.exploit_agent import login_sqli

EMAIL = "admin@juice-sh.op"
PASSWORD = "admin123"   # Juice Shop's published default, in its own documentation


def run(target, transport=login_sqli.urllib_transport, wait=120, clock=time.monotonic, sleep=time.sleep):
    login_sqli.check_allowed_host(target)
    body = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
    url = target.rstrip("/") + login_sqli.LOGIN_PATH
    end = clock() + wait
    while True:
        try:
            status, data = transport(url, body)
            break
        except OSError:
            if clock() >= end:
                return 2, {"ok": False, "status": None, "outcome": "the app never answered"}
            sleep(2)
    ok = status == 200 and login_sqli._token_in(data)
    return (0 if ok else 1), {"ok": ok, "status": status,
                              "outcome": "a legitimate login works" if ok else "a legitimate login failed"}


def main(argv=None, transport=None):
    ap = argparse.ArgumentParser(description="Check that a legitimate login works on the throwaway build.")
    ap.add_argument("--target", default=f"http://{login_sqli.ALLOWED_HOST}:3000")
    ap.add_argument("--wait", type=int, default=120)
    ap.add_argument("--out", default="out/verify/login-check.json")
    args = ap.parse_args(argv)
    try:
        code, result = run(args.target, wait=args.wait, **({"transport": transport} if transport else {}))
    except login_sqli.ExploitError as e:
        print(f"login-check: FAILED: {e}", file=sys.stderr)
        return 3
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(f"login-check: {result['outcome']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
