"""Tests for the verify step's legitimate-login check (M2-8). The transport and the clock are faked."""
import json

import pytest

from agents.verify_agent import login_check as lc

GOOD = (200, json.dumps({"authentication": {"token": "T"}}).encode())


def test_login_ok_with_a_token():
    code, result = lc.run("http://juice-shop-prod:3000", transport=lambda url, body: GOOD, wait=0)
    assert code == 0 and result["ok"] is True and "T" not in json.dumps(result)


def test_login_not_ok_when_refused_or_no_token():
    code, result = lc.run("http://juice-shop-prod:3000", transport=lambda u, b: (401, b"{}"), wait=0)
    assert code == 1 and result == {**result, "ok": False, "status": 401}
    code, result = lc.run("http://juice-shop-prod:3000", transport=lambda u, b: (200, b"not json"), wait=0)
    assert code == 1 and result["ok"] is False


def test_waits_for_the_app_then_gives_up():
    calls = []

    def flaky(url, body):
        calls.append(url)
        if len(calls) < 3:
            raise OSError("down")
        return GOOD

    ticks = iter(range(0, 1000))
    code, _ = lc.run("http://juice-shop-prod:3000", transport=flaky, wait=100,
                     clock=lambda: next(ticks), sleep=lambda s: None)
    assert code == 0 and len(calls) == 3
    ticks = iter(range(0, 1000, 10))
    code, result = lc.run("http://juice-shop-prod:3000", transport=lambda u, b: (_ for _ in ()).throw(OSError()),
                          wait=30, clock=lambda: next(ticks), sleep=lambda s: None)
    assert code == 2 and result["ok"] is False


def test_refuses_any_other_host_before_a_request(tmp_path, capsys):
    sent = []
    code = lc.main(["--target", "http://example.com:3000", "--out", str(tmp_path / "o.json")],
                   transport=lambda u, b: sent.append(u))
    assert code == 3 and not sent and "refusing" in capsys.readouterr().err


def test_main_writes_the_result_file(tmp_path):
    out = tmp_path / "r.json"
    assert lc.main(["--out", str(out), "--wait", "0"], transport=lambda u, b: GOOD) == 0
    assert json.loads(out.read_text())["ok"] is True
