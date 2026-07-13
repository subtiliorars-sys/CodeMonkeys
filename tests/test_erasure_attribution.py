"""M-7 follow-up — per-user attribution + message-content erasure (issue #70).

Sessions are single-owner (S6 Layer 1), so a member's message content is
attributed at the session level; typed `user` events additionally carry an
`author` tag at write time (emit()). The erasure cascade must:

  - delete the erased member's OWN sessions whole (events JSONL + history +
    index row + in-memory entry) and nothing of anyone else's,
  - content-scrub any author-tagged event of theirs inside a session they do
    NOT own, leaving every other line byte-identical,
  - delete their isolated user_<uname>/ workspace subtree (uploads,
    blackboards) without touching other members' subtrees or the shared root,
  - refuse to delete anything when the target does not resolve to a direct
    user_ child of WORKSPACE_DIR (crafted names, symlinks),
  - record what happened in the receipt (store names appear only when that
    content actually existed),
  - and blackboard_write from a member session must land in THEIR workspace
    (write-time attribution), matching the read path.

Run: ./.venv/bin/python -m pytest tests/test_erasure_attribution.py -q
"""
import json
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated users/tombstone/receipt stores + isolated SESSIONS_DIR and
    WORKSPACE_DIR. Seeds an Owner and two Members; authed as the Owner."""
    monkeypatch.setattr(server, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(server, "ERASED_FILE", str(tmp_path / "erased_accounts.json"))
    monkeypatch.setattr(server, "ERASURE_RECEIPTS_FILE",
                        str(tmp_path / "erasure_receipts.jsonl"))
    monkeypatch.setattr(server, "LOGIN_THROTTLE_FILE",
                        str(tmp_path / "login_throttle.json"))
    monkeypatch.setattr(server, "SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    os.makedirs(str(tmp_path / "sessions"), exist_ok=True)
    os.makedirs(str(tmp_path / "workspace"), exist_ok=True)

    server.save_users({
        "boss":  {"role": "Owner",  "created": 1},
        "alice": {"role": "Member", "created": 2},
        "bob":   {"role": "Member", "created": 3},
    })
    server.app.dependency_overrides[server.verify_owner] = lambda: "boss"

    created = []
    orig = server.new_session

    def _track(*a, **kw):
        s = orig(*a, **kw)
        created.append(s["id"])
        return s
    monkeypatch.setattr(server, "new_session", _track)

    yield tmp_path
    server.app.dependency_overrides.pop(server.verify_owner, None)
    for sid in created:
        server.SESSIONS.pop(sid, None)


def _receipts(tmp_path):
    p = tmp_path / "erasure_receipts.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _events_file(sid):
    return server._events_path(sid)


# --------------------------------------------------- write-time attribution

def test_user_events_are_author_tagged(env):
    s = server.new_session(title="t", username="alice")
    evt = server.emit(s, "user", text="hello world")
    assert evt["author"] == "alice"
    # persisted line carries the tag too
    line = json.loads(open(_events_file(s["id"])).readlines()[-1])
    assert line["author"] == "alice" and line["text"] == "hello world"
    # non-message events are not tagged
    assert "author" not in server.emit(s, "status", message="x")


def test_legacy_session_user_events_untagged(env):
    s = server.new_session(title="t", username=None)
    assert "author" not in server.emit(s, "user", text="webhook task")


# --------------------------------------------------- own-session hard delete

def test_erasure_deletes_only_erased_members_sessions(env):
    sa = server.new_session(title="alice-s", username="alice")
    sb = server.new_session(title="bob-s", username="bob")
    server.emit(sa, "user", text="alice private message")
    server.emit(sb, "user", text="bob keeps this")
    server.persist_history(sa)
    server.persist_history(sb)
    bob_events_before = open(_events_file(sb["id"])).read()

    r = client.delete("/api/users/alice")
    assert r.status_code == 200, r.text
    assert "sessions" in r.json()["stores"]

    # alice: memory, events file, history file and index row all gone
    assert sa["id"] not in server.SESSIONS
    assert not os.path.exists(_events_file(sa["id"]))
    assert not os.path.exists(
        os.path.join(server.SESSIONS_DIR, f"{sa['id']}.history.json"))
    idx = json.load(open(server._session_index_path()))
    assert sa["id"] not in idx
    # bob: everything intact, file byte-identical
    assert sb["id"] in server.SESSIONS
    assert open(_events_file(sb["id"])).read() == bob_events_before
    assert sb["id"] in idx


def test_erased_session_cannot_repersist(env):
    """An in-flight run still holds the session dict; after erasure its
    emit()/persist_history() must not re-materialize the deleted files."""
    sa = server.new_session(title="alice-s", username="alice")
    server.emit(sa, "user", text="hi")
    assert server._erase_user_sessions("alice") == 1
    assert sa["stop_flag"].is_set()
    server.emit(sa, "agent", text="late output from a dying thread")
    server.persist_history(sa)
    assert not os.path.exists(_events_file(sa["id"]))
    assert not os.path.exists(
        os.path.join(server.SESSIONS_DIR, f"{sa['id']}.history.json"))


# --------------------------------------------------- tagged-event scrubbing

def test_scrub_removes_only_tagged_events_from_foreign_session(env):
    """The precise-erasure backstop: alice's author-tagged message inside a
    session she does NOT own is scrubbed; bob's lines stay byte-identical."""
    sb = server.new_session(title="shared", username="bob")
    server.emit(sb, "user", text="bob line one")
    server.emit(sb, "user", text="alice was here", author="alice")
    server.emit(sb, "user", text="bob line two")
    bob_lines_before = [l for l in open(_events_file(sb["id"])).readlines()
                        if "alice" not in l]

    r = client.delete("/api/users/alice")
    assert r.status_code == 200
    assert "session_events_scrubbed" in r.json()["stores"]
    # bob's session survives; alice's content is gone from memory and disk
    assert sb["id"] in server.SESSIONS
    assert not any("alice was here" in json.dumps(e) for e in sb["events"])
    lines = open(_events_file(sb["id"])).readlines()
    assert len(lines) == 3
    tagged = json.loads(lines[1])
    assert tagged["text"] == server._M7_ERASED_MARKER
    assert tagged["author"] == server._M7_ERASED_MARKER
    assert tagged["i"] == 1 and tagged["type"] == "user"   # skeleton kept
    # every non-alice line is byte-identical
    assert [lines[0], lines[2]] == bob_lines_before


def test_scrub_reports_nothing_when_no_tagged_events(env):
    sb = server.new_session(title="bob-s", username="bob")
    server.emit(sb, "user", text="only bob")
    r = client.delete("/api/users/alice")
    assert r.status_code == 200
    stores = r.json()["stores"]
    assert "session_events_scrubbed" not in stores
    assert "sessions" not in stores            # alice had no sessions either


# --------------------------------------------------- workspace subtree

def test_workspace_subtree_deleted_others_untouched(env):
    ws = server.WORKSPACE_DIR
    a_bb = os.path.join(ws, "user_alice", ".codemonkeys")
    a_up = os.path.join(ws, "user_alice", "uploads", "sid1")
    b_bb = os.path.join(ws, "user_bob", ".codemonkeys")
    root_bb = os.path.join(ws, ".codemonkeys")
    for d in (a_bb, a_up, b_bb, root_bb):
        os.makedirs(d, exist_ok=True)
    open(os.path.join(a_bb, "blackboard-t.md"), "w").write("alice notes")
    open(os.path.join(a_up, "f.txt"), "w").write("alice upload")
    open(os.path.join(b_bb, "blackboard-t.md"), "w").write("bob notes")
    open(os.path.join(root_bb, "blackboard-legacy.md"), "w").write("shared")

    r = client.delete("/api/users/alice")
    assert r.status_code == 200
    assert "workspace" in r.json()["stores"]
    assert not os.path.exists(os.path.join(ws, "user_alice"))
    # other members' and the shared root's data survive
    assert open(os.path.join(b_bb, "blackboard-t.md")).read() == "bob notes"
    assert open(os.path.join(root_bb, "blackboard-legacy.md")).read() == "shared"


def test_workspace_guard_refuses_crafted_names(env):
    ws = server.WORKSPACE_DIR
    os.makedirs(os.path.join(ws, "user_bob"), exist_ok=True)
    marker = os.path.join(ws, "user_bob", "keep.txt")
    open(marker, "w").write("keep")
    # a name that would resolve outside a direct user_ child is refused
    assert server._erase_user_workspace("../../etc") is False
    assert server._erase_user_workspace("bob/../bob") is False
    assert server._erase_user_workspace("") is False
    assert open(marker).read() == "keep"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlink support")
def test_workspace_guard_refuses_symlinked_userdir(env):
    ws = server.WORKSPACE_DIR
    victim = os.path.join(ws, "user_bob")
    os.makedirs(victim, exist_ok=True)
    open(os.path.join(victim, "keep.txt"), "w").write("keep")
    try:
        os.symlink(victim, os.path.join(ws, "user_mallory"),
                   target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    assert server._erase_user_workspace("mallory") is False
    assert open(os.path.join(victim, "keep.txt")).read() == "keep"


# --------------------------------------------------- receipt

def test_receipt_records_content_stores(env):
    sa = server.new_session(title="alice-s", username="alice")
    server.emit(sa, "user", text="mine")
    os.makedirs(os.path.join(server.WORKSPACE_DIR, "user_alice"), exist_ok=True)
    client.delete("/api/users/alice")
    rec = _receipts(env)
    assert len(rec) == 1
    assert {"sessions", "workspace"} <= set(rec[0]["stores"])
    # no message content leaks into the receipt — subject id + store names only
    assert "mine" not in json.dumps(rec[0])


# --------------------------------------------------- blackboard attribution

def test_blackboard_write_lands_in_member_workspace(env):
    s = server.new_session(title="alice-s", username="alice")
    execute = server.make_executor(s, ["blackboard_write", "blackboard_read"])
    r, ok = execute({"name": "blackboard_write",
                     "args": {"slug": "proj", "section": "FACTS",
                              "content": "alice fact"}})
    assert ok, r
    member_board = os.path.join(server.WORKSPACE_DIR, "user_alice",
                                ".codemonkeys", "blackboard-proj.md")
    global_board = os.path.join(server.WORKSPACE_DIR,
                                ".codemonkeys", "blackboard-proj.md")
    assert os.path.exists(member_board)          # attributed at write time
    assert not os.path.exists(global_board)      # no commingling on the root
    # the same session's read path sees its own write back (was broken before)
    out, ok = execute({"name": "blackboard_read", "args": {"slug": "proj"}})
    assert ok and "alice fact" in out
    # erasing alice erases her board with her workspace
    client.delete("/api/users/alice")
    assert not os.path.exists(member_board)
