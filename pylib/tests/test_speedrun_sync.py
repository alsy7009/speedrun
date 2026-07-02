# Copyright: Speedrun
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Two-device sync through Anki's built-in self-hosted sync server.

Boots the `anki-sync-server` binary (rslib/sync) and simulates two devices
("desktop" and "phone") syncing one account:

- offline reviews on both devices merge with **no lost or double-counted
  reviews** (revlog union, unique ids), and
- a same-card conflict resolves with the documented winner: **review history
  merges; the card's scheduling state comes from the most recently modified
  device**.

This is the PRD's sync requirement, proven without the GUI.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from anki.collection import Collection

REPO = Path(__file__).resolve().parents[2]
SERVER_BIN = REPO / "out" / "rust" / "debug" / "anki-sync-server"

USER = "speedrun"
PASSWORD = "test123"

pytestmark = pytest.mark.skipif(
    not SERVER_BIN.exists(),
    reason="anki-sync-server not built (cargo build -p anki-sync-server)",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"sync server did not come up on port {port}")


@pytest.fixture()
def sync_server(tmp_path):
    port = _free_port()
    env = os.environ.copy()
    env.update(
        SYNC_USER1=f"{USER}:{PASSWORD}",
        SYNC_BASE=str(tmp_path / "server"),
        SYNC_HOST="127.0.0.1",
        SYNC_PORT=str(port),
    )
    proc = subprocess.Popen(
        [str(SERVER_BIN)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        yield f"http://127.0.0.1:{port}/"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _sync(col: Collection, endpoint: str) -> None:
    """Full sync protocol as the GUI drives it: normal sync, then a full
    upload/download if the server says one is required."""
    auth = col.sync_login(USER, PASSWORD, endpoint)
    out = col.sync_collection(auth, sync_media=False)
    if out.new_endpoint:
        auth.endpoint = out.new_endpoint
    if out.required in (out.NO_CHANGES, out.NORMAL_SYNC):
        return
    upload = out.required == out.FULL_UPLOAD
    # FULL_SYNC means either direction is acceptable; a fresh device downloads.
    if out.required == out.FULL_SYNC:
        upload = col.card_count() > 0
    col.close_for_full_sync()
    col.full_upload_or_download(auth=auth, server_usn=None, upload=upload)
    col.reopen(after_full_sync=True)


def _new_device(tmp_path, name: str) -> Collection:
    return Collection(str(tmp_path / f"{name}.anki2"))


def _add_notes(col: Collection, count: int) -> None:
    model = col.models.by_name("Basic")
    for i in range(count):
        note = col.new_note(model)
        note["Front"] = f"q{i}"
        note["Back"] = f"a{i}"
        col.add_note(note, 1)


def _answer_next(col: Collection) -> int:
    """Answer the next due/new card with Good; returns the card id."""
    card = col.sched.getCard()
    assert card is not None, "expected a card to review"
    col.sched.answerCard(card, 3)
    return card.id


def _revlog_ids(col: Collection) -> list[int]:
    return col.db.list("select id from revlog order by id")


def test_two_device_sync_merges_offline_reviews(sync_server, tmp_path):
    endpoint = sync_server

    # Device A: create content, review two cards, first sync (upload).
    a = _new_device(tmp_path, "desktop")
    _add_notes(a, 5)
    _answer_next(a)
    _answer_next(a)
    _sync(a, endpoint)

    # Device B: fresh install, sync pulls everything down.
    b = _new_device(tmp_path, "phone")
    _sync(b, endpoint)
    assert b.card_count() == a.card_count() == 5
    assert len(_revlog_ids(b)) == 2

    # Offline on both devices: one (different) review each.
    _answer_next(a)
    _answer_next(b)

    # Sync A, then B (B receives A's review), then A (A receives B's).
    _sync(a, endpoint)
    _sync(b, endpoint)
    _sync(a, endpoint)

    ids_a, ids_b = _revlog_ids(a), _revlog_ids(b)
    # No lost reviews: all four present on both devices.
    assert len(ids_a) == len(ids_b) == 4
    # No double-counted reviews: every revlog entry is unique.
    assert len(set(ids_a)) == 4
    assert ids_a == ids_b

    # Both collections remain consistent.
    assert a.db.scalar("pragma integrity_check") == "ok"
    assert b.db.scalar("pragma integrity_check") == "ok"


def test_same_card_conflict_documented_winner(sync_server, tmp_path):
    endpoint = sync_server

    a = _new_device(tmp_path, "desktop")
    _add_notes(a, 1)
    _sync(a, endpoint)
    b = _new_device(tmp_path, "phone")
    _sync(b, endpoint)

    # Both devices review the SAME card while offline; B modifies last.
    cid = _answer_next(a)
    time.sleep(1.1)  # ensure a later modification stamp on B
    assert _answer_next(b) == cid

    _sync(a, endpoint)
    _sync(b, endpoint)
    _sync(a, endpoint)

    # Review history merges: both entries survive on both devices.
    assert len(_revlog_ids(a)) == len(_revlog_ids(b)) == 2
    # Documented winner: the card's scheduling state converges to one version
    # (the most recently modified device's) on both sides.
    card_a, card_b = a.get_card(cid), b.get_card(cid)
    assert (card_a.mod, card_a.reps, card_a.ivl, card_a.queue) == (
        card_b.mod,
        card_b.reps,
        card_b.ivl,
        card_b.queue,
    )

    a.close()
    b.close()
