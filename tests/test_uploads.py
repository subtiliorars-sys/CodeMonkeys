"""Tests for upload/message input hardening (server._save_uploads / _cap_message).

The upload path used to base64-decode the full payload into memory before a
10 MB truncation (memory spike), 500'd on a '..' filename, wrote outside the
_jail, and accepted unbounded message text. These tests lock in the fixes.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import base64
import os
import shutil
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

SID = "sess-upl"
_UPDIR = os.path.join(server.WORKSPACE_DIR, "uploads", SID)


def _f(name, raw=b"hello"):
    return server.FileUpload(name=name, content_b64=base64.b64encode(raw).decode())


def setup_function(_):
    shutil.rmtree(_UPDIR, ignore_errors=True)


def teardown_function(_):
    shutil.rmtree(_UPDIR, ignore_errors=True)


def test_cap_message_truncates_and_passes_through():
    assert server._cap_message("hi") == "hi"
    assert server._cap_message("") == ""
    big = "x" * (server.MAX_MSG_CHARS + 50)
    out = server._cap_message(big)
    assert len(out) <= server.MAX_MSG_CHARS + len("\n…[message truncated]")
    assert out.endswith("[message truncated]")


def test_normal_upload_is_written():
    names = server._save_uploads(SID, [_f("notes.txt", b"data here")])
    assert names == [f"uploads/{SID}/notes.txt"]
    with open(os.path.join(_UPDIR, "notes.txt"), "rb") as fh:
        assert fh.read() == b"data here"


def test_oversized_payload_skipped_before_decode():
    huge_b64 = "A" * (server.MAX_UPLOAD_B64 + 10)   # valid b64 chars, over the cap
    assert server._save_uploads(SID, [server.FileUpload(name="big.bin", content_b64=huge_b64)]) == []


def test_dotdot_and_dot_names_are_skipped_not_500():
    assert server._save_uploads(SID, [_f(".."), _f("."), _f("")]) == [
        # ".." and "." skipped; "" -> basename "" -> "file" is written
        f"uploads/{SID}/file"]


def test_path_traversal_name_stays_in_updir():
    names = server._save_uploads(SID, [_f("../../etc/evil.txt", b"x")])
    # basename reduces it to evil.txt, _jail confirms containment
    assert names == [f"uploads/{SID}/evil.txt"]
    for n in names:
        full = os.path.realpath(os.path.join(server.WORKSPACE_DIR, n))
        assert full.startswith(os.path.realpath(server.WORKSPACE_DIR) + os.sep)


def test_file_count_is_capped():
    many = [_f(f"f{i}.txt") for i in range(server.MAX_UPLOAD_FILES + 15)]
    names = server._save_uploads(SID, many)
    assert len(names) == server.MAX_UPLOAD_FILES


def test_no_files_returns_empty():
    assert server._save_uploads(SID, None) == []
    assert server._save_uploads(SID, []) == []


def test_nul_byte_filename_is_skipped_not_500():
    # A NUL in the name makes os.open raise ValueError (not OSError); it must be
    # skipped, never propagate as a 500 that aborts the whole message.
    bad = _f("evil\x00.txt", b"x")
    good = _f("ok.txt", b"y")
    names = server._save_uploads(SID, [bad, good])
    assert names == [f"uploads/{SID}/ok.txt"]   # bad skipped, good still written
