import zlib
from decimal import Decimal

import pytest

from meridian.delta.book import BookError, ChecksumMismatch, ObUpdatesBook, SequenceGap

D = Decimal


def snap(seq=6199, a=None, b=None, cs=None):
    m = {
        "action": "snapshot",
        "a": a or [["16919.0", "1087"], ["16919.5", "1193"], ["16920.0", "510"]],
        "b": b or [["16918.0", "602"], ["16917.5", "1792"], ["16917.0", "2039"]],
        "seq": seq,
        "sy": "BTCUSD",
        "type": "ob_updates",
        "ts": 1,
    }
    if cs is not None:
        m["cs"] = cs
    return m


def upd(seq, a=(), b=(), cs=None):
    m = {"action": "update", "a": list(a), "b": list(b), "seq": seq, "sy": "BTCUSD", "ts": 2}
    if cs is not None:
        m["cs"] = cs
    return m


def test_snapshot_then_docs_example_update():
    book = ObUpdatesBook("BTCUSD")
    book.on_message(snap())
    book.on_message(upd(6200, a=[["16919.0", "0"], ["16919.5", "710"]], b=[["16918.5", "304"]]))
    assert book.synced and book.seq == 6200
    assert book.best_ask() == D("16919.5")
    assert book.asks[D("16919.5")].size == "710"
    assert book.best_bid() == D("16918.5")
    assert D("16919.0") not in book.asks


def test_sequence_gap_resets_and_raises():
    book = ObUpdatesBook("BTCUSD")
    book.on_message(snap())
    with pytest.raises(SequenceGap):
        book.on_message(upd(6202, a=[["16919.5", "1"]]))
    assert not book.synced and not book.asks


def test_updates_before_snapshot_are_ignored():
    book = ObUpdatesBook("BTCUSD")
    book.on_message(upd(5, a=[["1", "1"]]))
    assert not book.synced and not book.asks


def test_checksum_matches_docs_format():
    book = ObUpdatesBook("BTCUSD")
    a = [["100.00", "23"], ["100.05", "34"]]
    b = [["99.04", "87"], ["98.65", "102"], ["98.30", "16"]]
    expected = "100.00:23,100.05:34|99.04:87,98.65:102,98.30:16"
    cs = zlib.crc32(expected.encode()) & 0xFFFFFFFF
    book.on_message(snap(a=a, b=b, cs=cs))
    assert book.checksum_string() == expected
    assert book.synced


def test_checksum_mismatch_raises_and_resets():
    book = ObUpdatesBook("BTCUSD")
    with pytest.raises(ChecksumMismatch):
        book.on_message(snap(cs=12345))
    assert not book.synced and book.checksum_failures == 1


def test_checksum_uses_only_top_ten_levels():
    asks = [[f"{100 + i}.0", "1"] for i in range(15)]
    bids = [[f"{99 - i}.0", "1"] for i in range(15)]
    book = ObUpdatesBook("BTCUSD")
    book.on_message(snap(a=asks, b=bids), verify_checksum=False)
    left, right = book.checksum_string().split("|")
    assert len(left.split(",")) == 10 and len(right.split(",")) == 10
    assert right.startswith("99.0:1,98.0:1")


def test_error_action_raises_book_error():
    book = ObUpdatesBook("BTCUSD")
    book.on_message(snap())
    with pytest.raises(BookError):
        book.on_message({"action": "error", "msg": "Snapshot load failed"})
    assert not book.synced
