"""Tests added after the seal, for the ungraded reports (rov_ungraded.py).
The sealed planted-case tests (MC2) are test_rpki_rov.py, unchanged."""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "analysis", "rpki"))
from rov import INVALID, VALID, VrpIndex  # noqa: E402


def test_ungraded_attribution():
    """rov_ungraded._attribute must reproduce the graded transitions and
    attribute each flip to the collectors that saw it, its family and the
    trust anchors whose covering VRPs changed. 192.0.2.0/24 moves from
    RIPE NCC (AS2) to ARIN (AS1), so its flips involve both anchors."""
    from rov_unit import TALS, _errors, _parsed, _states
    from rov_ungraded import _attribute, _union

    fresh_ta = {t: set() for t in TALS} | {
        "arin": {("1", "192.0.2.0/24", "24")},
        "ripencc": {("3", "198.51.100.0/24", "24")}}
    stale_ta = {t: set() for t in TALS} | {
        "ripencc": {("2", "192.0.2.0/24", "24")},
        "apnic": {("4", "203.0.113.0/24", "24")}}
    peers = {("192.0.2.0/24", 2): 3, ("198.51.100.0/24", 9): 1,
             ("203.0.113.0/24", 5): 2, ("192.0.2.0/24", 1): 4,
             ("10.0.0.0/8", 7): 1}
    masks_by_key = {("192.0.2.0/24", 2): 0b001, ("198.51.100.0/24", 9): 0b011,
                    ("203.0.113.0/24", 5): 0b100, ("192.0.2.0/24", 1): 0b111,
                    ("10.0.0.0/8", 7): 0b001}
    rows = _parsed(peers)
    masks = [masks_by_key[(r[0], r[4])] for r in rows]
    fresh, stale = _union(fresh_ta), _union(stale_ta)
    fst = _states(rows, fresh)
    got = _attribute(rows, masks, fst, stale, ["rrc00", "rrc01", "rrc03"],
                     {t: VrpIndex(s) for t, s in fresh_ta.items()},
                     {t: VrpIndex(s) for t, s in stale_ta.items()})
    assert got["transitions"] == _errors(rows, fst, stale)["transitions"]
    acc, drp = got["accept"], got["drop"]
    assert acc["by_collector"] == {"rrc00": 2, "rrc01": 1, "rrc03": 0}
    assert drp["by_collector"] == {"rrc00": 1, "rrc01": 1, "rrc03": 2}
    assert (acc["v4"], acc["v6"], drp["v4"], drp["v6"]) == (2, 0, 2, 0)
    assert acc["by_ta"]["arin"] == 1 and acc["by_ta"]["ripencc"] == 2
    assert acc["by_ta"]["multi"] == 1 and acc["by_ta"]["none"] == 0
    assert drp["by_ta"]["apnic"] == 1 and drp["by_ta"]["multi"] == 1
    assert sorted(f[0] for f in got["drop_flips"]) == ["192.0.2.0/24",
                                                       "203.0.113.0/24"]


def test_ungraded_rib_fetch_rejects_cut_gzip(tmp_path):
    """rov_ungraded._fetch_rib parses only a complete dump: a gzip cut short
    (here served whole, so the length matches) must fail its gzip check."""
    import gzip

    from rov_ungraded import _fetch_rib

    good = tmp_path / "good.gz"
    good.write_bytes(gzip.compress(os.urandom(1 << 16)))
    cut = tmp_path / "cut.gz"
    cut.write_bytes(good.read_bytes()[:-100])
    out = _fetch_rib(good.as_uri(), tmp_path / "dl" / "a.gz", tries=1)
    assert out == {"bytes": good.stat().st_size, "attempts": 1}
    with pytest.raises(SystemExit):
        _fetch_rib(cut.as_uri(), tmp_path / "dl" / "b.gz", tries=2)


def test_as0_does_not_override_a_matching_vrp():
    """RFC 6483 / 6811 precedence: an AS0 VRP covering a route does not
    make it Invalid when another covering VRP matches its origin and
    length (review, 2026-10-26). Overlap of the AS0 and a matching VRP,
    at the same and at a shorter prefix length."""
    idx = VrpIndex([("AS0", "203.0.113.0/24", 24), ("AS64510", "203.0.113.0/24", 24),
                    ("AS0", "198.18.0.0/15", 15), ("AS64511", "198.18.0.0/16", 24)])
    assert idx.validate("203.0.113.0/24", 64510) == VALID
    assert idx.validate("203.0.113.0/24", 64999) == INVALID
    assert idx.validate("198.18.5.0/24", 64511) == VALID
    assert idx.validate("198.19.0.0/16", 64511) == INVALID
    assert idx.validate("198.18.0.0/15", 0) == INVALID
