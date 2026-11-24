"""Tests for the publish step (M2-7): fixed files to a branch and a pull request.

The GitHub transport is faked and the tar is built in the test. No network, no token, no agent.
"""
import io
import json
import tarfile

import pytest

from agents.fixer_agent import publish

TOKEN = "ghp_FAKEFIXTOKENMARKER123456"
BASE = "a" * 40
TASK = {"issue": 3, "file": "app/routes/login.ts", "rel_file": "routes/login.ts", "line": 34, "cwe": "CWE-89",
        "branch": "fix/issue-3-login-sqli", "title": "Fix: CWE-89 login SQL injection (closes #3)"}
SPEC = "test/server/loginSqlInjectionSpec.ts"
METRICS = {"model": "anthropic/claude-sonnet-5-5", "cost_usd": 0.1234, "input_tokens": 100, "output_tokens": 20,
           "max_budget": 1.0, "max_iterations": 40, "budget_cap_hit": False, "iteration_cap_hit": False}
SANITY = {"ok": True, "passing": 41, "failing": 0}


def make_tar(path, files, extra=()):
    with tarfile.open(path, "w") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for info in extra:
            tf.addfile(info)
    return path


def make_app(tmp_path, files):
    app = tmp_path / "app"
    for name, data in files.items():
        p = app / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return app


ORIGINAL = {"routes/login.ts": b"old login\n", "lib/insecurity.ts": b"insec\n", "test/server/insecuritySpec.ts": b"x\n"}
FIXED = {**ORIGINAL, "routes/login.ts": b"new login\n", SPEC: b"describe()\n"}


class Github:
    """A fake GitHub. Routes by method and path. Records every call."""

    def __init__(self, branch_exists=False, prs=(), fail_at=None):
        self.calls, self.branch_exists, self.prs, self.fail_at = [], branch_exists, list(prs), fail_at
        self.n = 0

    def __call__(self, method, url, headers, body):
        path = url.split("https://api.github.com/repos/o/r")[1]
        self.calls.append((method, path, json.loads(body) if body else None))
        if self.fail_at and path.startswith(self.fail_at):
            return 500, {}
        if method == "GET" and path == "/git/ref/heads/main":
            return 200, {"object": {"sha": BASE}}
        if method == "GET" and path.startswith("/git/ref/heads/fix/"):
            return (200, {"object": {"sha": "f" * 40}}) if self.branch_exists else (404, {})
        if method == "GET" and path.startswith("/pulls?"):
            return 200, self.prs
        if method == "GET" and path.startswith("/git/commits/"):
            return 200, {"tree": {"sha": "b" * 40}}
        if method == "POST" and path == "/git/blobs":
            self.n += 1
            return 201, {"sha": f"{self.n:040x}"}
        if method == "POST" and path == "/git/trees":
            return 201, {"sha": "c" * 40}
        if method == "POST" and path == "/git/commits":
            return 201, {"sha": "d" * 40}
        if method == "POST" and path == "/git/refs":
            return 201, {"ref": "x"}
        if method == "POST" and path == "/pulls":
            return 201, {"number": 7, "html_url": "https://github.com/o/r/pull/7"}
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def env(tmp_path):
    app = make_app(tmp_path, ORIGINAL)
    tar = make_tar(tmp_path / "tree.tar", FIXED)
    (tmp_path / "task.json").write_text(json.dumps(TASK))
    (tmp_path / "metrics.json").write_text(json.dumps(METRICS))
    (tmp_path / "sanity.json").write_text(json.dumps(SANITY))
    return tmp_path, app, tar


def run(tmp_path, app, tar, gh, token=TOKEN, base_sha=BASE):
    return publish.main(["--repo", "o/r", "--task", str(tmp_path / "task.json"), "--tree", str(tar),
                         "--base-dir", str(app), "--base-sha", base_sha, "--metrics", str(tmp_path / "metrics.json"),
                         "--sanity", str(tmp_path / "sanity.json"), "--pr-out", str(tmp_path / "pr.json")],
                        env={"GITHUB_FIX_TOKEN": token} if token else {}, transport=gh)


# ---- reading the tar safely ----

def test_read_tree_returns_regular_files_and_strips_the_dot(tmp_path):
    tar = make_tar(tmp_path / "t.tar", {"./routes/a.ts": b"a", "b.ts": b"b"})
    assert publish.read_tree(tar) == {"routes/a.ts": b"a", "b.ts": b"b"}


@pytest.mark.parametrize("name", ["/etc/passwd", "../x", "a/../../x", "a\\b"])
def test_read_tree_refuses_dangerous_names(tmp_path, name):
    tar = make_tar(tmp_path / "t.tar", {name: b"x"})
    with pytest.raises(publish.PublishError, match="unsafe path"):
        publish.read_tree(tar)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE])
def test_read_tree_refuses_links_and_devices(tmp_path, kind):
    info = tarfile.TarInfo("routes/x")
    info.type, info.linkname = kind, "/etc/passwd"
    tar = make_tar(tmp_path / "t.tar", {}, extra=[info])
    with pytest.raises(publish.PublishError, match="not a plain file"):
        publish.read_tree(tar)


def test_read_tree_allows_directories_and_skips_noise_without_reading_it(tmp_path):
    d = tarfile.TarInfo("routes")
    d.type = tarfile.DIRTYPE
    tar = make_tar(tmp_path / "t.tar", {"node_modules/x/big.js": b"x" * 10, "routes/a.ts": b"a"}, extra=[d])
    assert publish.read_tree(tar) == {"routes/a.ts": b"a"}


def test_read_tree_refuses_a_file_above_the_hashing_ceiling_and_too_many_files(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "MAX_HASHED_BYTES", 1000)
    tar = make_tar(tmp_path / "t.tar", {"routes/big.ts": b"x" * 1001})
    with pytest.raises(publish.PublishError, match="too large"):
        publish.read_tree(tar)
    monkeypatch.undo()
    monkeypatch.setattr(publish, "MAX_MEMBERS", 2)
    tar = make_tar(tmp_path / "t2.tar", {f"routes/{i}.ts": b"x" for i in range(3)})
    with pytest.raises(publish.PublishError, match="too many"):
        publish.read_tree(tar)


def test_read_tree_refuses_a_file_that_is_not_a_tar(tmp_path):
    p = tmp_path / "t.tar"
    p.write_bytes(b"not a tar")
    with pytest.raises(publish.PublishError, match="cannot read"):
        publish.read_tree(p)


# ---- choosing the files ----

def test_changed_files_are_the_modified_and_added_ones_only(env):
    tmp, app, tar = env
    changes = publish.changed_files(publish.read_tree(tar), app, TASK)
    assert sorted(changes) == ["routes/login.ts", SPEC] and changes[SPEC] == b"describe()\n"


def test_noise_files_are_ignored(env):
    tmp, app, _ = env
    tree = {**FIXED, "package-lock.json": b"changed", "logs/access.log": b"x", "data/juiceshop.sqlite": b"x"}
    assert sorted(publish.changed_files(tree, app, TASK)) == ["routes/login.ts", SPEC]


@pytest.mark.parametrize("tree_changes,message", [
    ({"routes/other.ts": b"x"}, None),       # a new file under routes/ is allowed
    ({"config/default.yml": b"x"}, "outside the allowed folders"),
    ({".github/workflows/x.yml": b"x"}, "outside the allowed folders"),
    ({"package.json": b"{}"}, "outside the allowed folders"),
])
def test_files_outside_the_allowed_folders_are_refused(env, tree_changes, message):
    tmp, app, _ = env
    tree = {**FIXED, **tree_changes}
    if message is None:
        assert "routes/other.ts" in publish.changed_files(tree, app, TASK)
    else:
        with pytest.raises(publish.PublishError, match=message):
            publish.changed_files(tree, app, TASK)


def test_a_deleted_file_is_refused(env):
    tmp, app, _ = env
    tree = dict(FIXED)
    del tree["lib/insecurity.ts"]
    with pytest.raises(publish.PublishError, match="deleted"):
        publish.changed_files(tree, app, TASK)


def test_the_target_file_must_change(env):
    tmp, app, _ = env
    tree = {**FIXED, "routes/login.ts": ORIGINAL["routes/login.ts"]}
    with pytest.raises(publish.PublishError, match="target file"):
        publish.changed_files(tree, app, TASK)


def test_the_regression_test_must_be_present(env):
    tmp, app, _ = env
    tree = {k: v for k, v in FIXED.items() if k != SPEC}
    with pytest.raises(publish.PublishError, match="regression test"):
        publish.changed_files(tree, app, TASK)


def test_too_many_files_and_binary_files_are_refused(env):
    tmp, app, _ = env
    many = {**FIXED, **{f"routes/n{i}.ts": b"x" for i in range(publish.MAX_FILES)}}
    with pytest.raises(publish.PublishError, match="too many changed files"):
        publish.changed_files(many, app, TASK)
    with pytest.raises(publish.PublishError, match="not text"):
        publish.changed_files({**FIXED, "routes/login.ts": b"\x00\xff\xfe"}, app, TASK)


# ---- the pull request text ----

def test_the_pull_request_body_links_the_issue_and_says_it_is_unverified():
    body = publish.build_body(TASK, ["routes/login.ts", SPEC], METRICS, SANITY)
    assert "Closes #3" in body and "$0.1234" in body and "anthropic/claude-sonnet-5-5" in body
    assert "routes/login.ts" in body and SPEC in body
    assert "not yet verified" in body.lower() and "do not merge" in body.lower()
    assert "41 passing" in body


def test_the_body_copes_with_missing_metrics():
    body = publish.build_body(TASK, [SPEC], None, None)
    assert "Closes #3" in body and "cost: unknown" in body.lower()


# ---- the whole step ----

def test_a_good_run_makes_one_commit_one_branch_and_one_pull_request(env, capsys):
    tmp, app, tar = env
    gh = Github()
    assert run(tmp, app, tar, gh) == 0
    posts = [(p, b) for m, p, b in gh.calls if m == "POST"]
    assert [p for p, _ in posts] == ["/git/blobs", "/git/blobs", "/git/trees", "/git/commits", "/git/refs", "/pulls"]
    tree = dict(posts)["/git/trees"]
    assert sorted(e["path"] for e in tree["tree"]) == ["app/routes/login.ts", "app/" + SPEC]
    assert tree["base_tree"] == "b" * 40
    commit = dict(posts)["/git/commits"]
    assert commit["parents"] == [BASE] and "closes #3" in commit["message"].lower()
    assert dict(posts)["/git/refs"] == {"ref": "refs/heads/fix/issue-3-login-sqli", "sha": "d" * 40}
    pr = dict(posts)["/pulls"]
    assert pr["head"] == "fix/issue-3-login-sqli" and pr["base"] == "main"
    assert pr["title"] == TASK["title"] and "Closes #3" in pr["body"]
    assert json.loads((tmp / "pr.json").read_text())["number"] == 7
    assert "pull/7" in capsys.readouterr().out


def test_the_token_is_never_in_a_body_or_a_message(env, capsys):
    tmp, app, tar = env
    gh = Github()
    run(tmp, app, tar, gh)
    assert all(TOKEN not in json.dumps(b) for _, _, b in gh.calls)
    assert TOKEN not in capsys.readouterr().out


def test_an_existing_branch_stops_the_step_before_any_write(env, capsys):
    tmp, app, tar = env
    gh = Github(branch_exists=True)
    assert run(tmp, app, tar, gh) == 1
    assert not [c for c in gh.calls if c[0] == "POST"]
    assert "already exists" in capsys.readouterr().err


def test_an_existing_pull_request_stops_the_step_before_any_write(env, capsys):
    tmp, app, tar = env
    gh = Github(prs=[{"number": 5}])
    assert run(tmp, app, tar, gh) == 1
    assert not [c for c in gh.calls if c[0] == "POST"]
    assert "pull request" in capsys.readouterr().err


def test_a_failure_after_the_branch_exists_says_so(env, capsys):
    tmp, app, tar = env
    gh = Github()

    def flaky(method, url, headers, body):
        if method == "POST" and url.endswith("/pulls"):
            return 500, {}
        return gh(method, url, headers, body)
    assert run(tmp, app, tar, flaky) == 1
    err = capsys.readouterr().err
    assert "branch fix/issue-3-login-sqli was created" in err and "no pull request" in err


def test_a_github_failure_before_any_write_is_reported(env, capsys):
    tmp, app, tar = env
    assert run(tmp, app, tar, Github(fail_at="/git/ref/heads/fix")) == 1
    assert "HTTP 500" in capsys.readouterr().err


def test_a_refused_tree_creates_nothing(env, capsys):
    tmp, app, _ = env
    tar = make_tar(tmp / "bad.tar", {**FIXED, "package.json": b"{}"})
    gh = Github()
    assert run(tmp, app, tar, gh) == 1
    assert gh.calls == []
    assert "outside the allowed folders" in capsys.readouterr().err


def test_missing_token_stops_the_step(env, capsys):
    tmp, app, tar = env
    assert run(tmp, app, tar, Github(), token="") == 1
    assert "GITHUB_FIX_TOKEN" in capsys.readouterr().err


def test_a_missing_task_file_or_a_bad_repo_is_an_error(env, capsys):
    tmp, app, tar = env
    (tmp / "task.json").unlink()
    assert run(tmp, app, tar, Github()) == 1
    assert publish.main(["--repo", "bad", "--task", "x", "--tree", "x", "--base-dir", "x", "--base-sha", BASE,
                         "--metrics", "x", "--sanity", "x", "--pr-out", "x"], env={"GITHUB_FIX_TOKEN": TOKEN}) == 1


def test_missing_metrics_or_sanity_files_do_not_stop_the_step(env):
    tmp, app, tar = env
    (tmp / "metrics.json").unlink()
    (tmp / "sanity.json").write_text("{nope")
    assert run(tmp, app, tar, Github()) == 0


# ---- the two bugs found in the third live run ----
# 1. A large file that is byte-identical to origin/main's version must not stop the run. Anything new or changed
#    is held to the size cap, whatever its size.
# 2. A .git/ folder (the agent ran "git init" in its copy) is scratch and must be ignored.

BIG = b"B" * (publish.MAX_FILE_BYTES + 25_000)


def test_read_tree_keeps_a_large_file_as_a_hash_not_as_bytes(tmp_path):
    tar = make_tar(tmp_path / "t.tar", {"test/files/big.pdf": BIG, "routes/a.ts": b"a"})
    tree = publish.read_tree(tar)
    assert tree["routes/a.ts"] == b"a"
    big = tree["test/files/big.pdf"]
    assert isinstance(big, publish.LargeFile) and big.size == len(BIG)


def test_a_large_file_identical_to_the_base_is_not_a_change(env):
    tmp, app, _ = env
    (app / "test/files").mkdir(parents=True, exist_ok=True)
    (app / "test/files/big.pdf").write_bytes(BIG)
    (app / "screenshots").mkdir()
    (app / "screenshots/s.png").write_bytes(BIG)
    tar = make_tar(tmp / "real.tar", {**FIXED, "test/files/big.pdf": BIG, "screenshots/s.png": BIG})
    assert sorted(publish.changed_files(publish.read_tree(tar), app, TASK)) == ["routes/login.ts", SPEC]


def test_a_large_file_that_differs_by_one_byte_is_refused(env):
    tmp, app, _ = env
    (app / "test/files").mkdir(parents=True, exist_ok=True)
    (app / "test/files/big.pdf").write_bytes(BIG)
    tar = make_tar(tmp / "t.tar", {**FIXED, "test/files/big.pdf": BIG[:-1] + b"X"})
    with pytest.raises(publish.PublishError, match="too large"):
        publish.changed_files(publish.read_tree(tar), app, TASK)


def test_a_new_large_file_is_refused_even_in_an_allowed_folder(env):
    tmp, app, _ = env
    tar = make_tar(tmp / "t.tar", {**FIXED, "routes/huge.ts": BIG})
    with pytest.raises(publish.PublishError, match="too large"):
        publish.changed_files(publish.read_tree(tar), app, TASK)


def test_a_large_changed_file_is_refused(env):
    tmp, app, _ = env
    (app / "routes").mkdir(exist_ok=True)
    (app / "routes/login.ts").write_bytes(BIG)
    tar = make_tar(tmp / "t.tar", {**FIXED, "routes/login.ts": BIG + b"more"})
    with pytest.raises(publish.PublishError, match="too large"):
        publish.changed_files(publish.read_tree(tar), app, TASK)


def test_the_same_large_content_at_a_new_path_is_refused(env):
    tmp, app, _ = env
    (app / "test/files").mkdir(parents=True, exist_ok=True)
    (app / "test/files/big.pdf").write_bytes(BIG)
    tar = make_tar(tmp / "t.tar", {**FIXED, "test/files/copy-of-big.pdf": BIG})
    with pytest.raises(publish.PublishError, match="too large"):
        publish.changed_files(publish.read_tree(tar), app, TASK)


def test_a_large_file_the_base_does_not_have_is_refused(env):
    # (a path on the ignore list, such as ftp/, is dropped and never committed, so it is not a way in either)
    tmp, app, _ = env
    tar = make_tar(tmp / "t.tar", {**FIXED, "config/new-big.bin": BIG})
    with pytest.raises(publish.PublishError, match="too large"):
        publish.changed_files(publish.read_tree(tar), app, TASK)


def real_shaped_tar(tmp, extra=None):
    """A tar shaped like the one the sandbox gave us: the fix, a big unchanged file, and a .git folder."""
    link = tarfile.TarInfo(".git/hooks/odd-link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    folder = tarfile.TarInfo(".git")
    folder.type = tarfile.DIRTYPE
    files = {**FIXED, "test/files/big.pdf": BIG, ".git/HEAD": b"ref: refs/heads/main\n", ".git/config": b"[core]\n",
             ".git/hooks/pre-commit.sample": b"#!/bin/sh\n"}
    files.update(extra or {})
    return make_tar(tmp / "real.tar", files, extra=[folder, link])


def test_a_git_folder_is_ignored_even_with_a_symlink_inside_it(env):
    tmp, app, _ = env
    (app / "test/files").mkdir(parents=True, exist_ok=True)
    (app / "test/files/big.pdf").write_bytes(BIG)
    tree = publish.read_tree(real_shaped_tar(tmp))
    assert not [p for p in tree if p.startswith(".git")]
    assert sorted(publish.changed_files(tree, app, TASK)) == ["routes/login.ts", SPEC]


def test_the_whole_step_publishes_a_real_shaped_tar(env, capsys):
    tmp, app, _ = env
    (app / "test/files").mkdir(parents=True, exist_ok=True)
    (app / "test/files/big.pdf").write_bytes(BIG)
    gh = Github()
    assert run(tmp, app, real_shaped_tar(tmp), gh) == 0
    tree = [b for m, p, b in gh.calls if p == "/git/trees"][0]
    assert sorted(e["path"] for e in tree["tree"]) == ["app/routes/login.ts", "app/" + SPEC]
    assert "pull/7" in capsys.readouterr().out


def test_a_git_path_is_not_a_way_around_the_allowed_folders(env):
    # ".git" is ignored, but a folder that only starts with the same letters is not
    tmp, app, _ = env
    tar = make_tar(tmp / "t.tar", {**FIXED, ".github/workflows/x.yml": b"x", ".gitignore": b"x"})
    with pytest.raises(publish.PublishError, match="outside the allowed folders"):
        publish.changed_files(publish.read_tree(tar), app, TASK)


# ---- the base must be what GitHub's main is now ----

def test_a_base_that_is_not_the_current_main_stops_the_step_before_any_write(env, capsys):
    tmp, app, tar = env
    gh = Github()
    assert run(tmp, app, tar, gh, base_sha="9" * 40) == 1
    assert not [c for c in gh.calls if c[0] == "POST"]
    assert "main has moved" in capsys.readouterr().err


def test_a_new_large_file_in_an_ignored_folder_is_dropped_not_committed(env):
    tmp, app, _ = env
    tar = make_tar(tmp / "t.tar", {**FIXED, "ftp/new-big.bin": BIG})
    assert sorted(publish.changed_files(publish.read_tree(tar), app, TASK)) == ["routes/login.ts", SPEC]
