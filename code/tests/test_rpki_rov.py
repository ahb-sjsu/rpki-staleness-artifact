"""MC2 of PREREG-RPKI-ROV-STALENESS: the validator against planted
RFC 6811 cases. Any failure voids the cell."""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "analysis", "rpki"))
from rov import INVALID, NOT_FOUND, VALID, VrpIndex, decision_errors  # noqa: E402

VRPS = [
    ("AS64500", "192.0.2.0/24", 24),
    ("AS64501", "198.51.100.0/22", 24),
    ("AS64502", "198.51.100.0/22", 22),
    ("AS0", "203.0.113.0/24", 24),
    ("64503", "2001:db8::/32", 48),
]


@pytest.fixture(scope="module")
def idx():
    return VrpIndex(VRPS)


@pytest.mark.parametrize("prefix,origin,want", [
    ("192.0.2.0/24", 64500, VALID),          # exact match
    ("192.0.2.0/25", 64500, INVALID),        # longer than maxLength
    ("192.0.2.0/24", 64999, INVALID),        # wrong origin
    ("198.51.101.0/24", 64501, VALID),       # within maxLength of a /22
    ("198.51.101.0/24", 64502, INVALID),     # other VRP's maxLength is 22
    ("198.51.100.0/22", 64502, VALID),       # second covering VRP matches
    ("198.51.100.0/23", 64999, INVALID),     # covered, no match
    ("203.0.113.0/24", 64500, INVALID),      # AS0 covers, never matches
    ("203.0.113.0/24", 0, INVALID),          # origin 0 never valid
    ("10.0.0.0/8", 64500, NOT_FOUND),        # no cover
    ("192.0.0.0/16", 64500, NOT_FOUND),      # less specific than any VRP
    ("2001:db8:1::/48", 64503, VALID),       # IPv6 within maxLength
    ("2001:db8:1::/49", 64503, INVALID),     # IPv6 beyond maxLength
    ("2001:db9::/32", 64503, NOT_FOUND),     # IPv6 no cover
])
def test_rfc6811_cases(idx, prefix, origin, want):
    assert idx.validate(prefix, origin) == want


def test_asn_forms_agree(idx):
    assert idx.validate("192.0.2.0/24", "AS64500") == VALID
    assert idx.validate("192.0.2.0/24", "64500") == VALID


def test_decision_errors_classes():
    fresh = VrpIndex([("AS1", "192.0.2.0/24", 24),
                      ("AS3", "198.51.100.0/24", 24)])
    stale = VrpIndex([("AS2", "192.0.2.0/24", 24),
                      ("AS4", "203.0.113.0/24", 24)])
    ann = [
        ("192.0.2.0/24", 2),       # stale VALID -> fresh INVALID: accept (revoked)
        ("198.51.100.0/24", 9),    # stale NOT_FOUND -> fresh INVALID: accept (unseen)
        ("203.0.113.0/24", 5),     # stale INVALID -> fresh NOT_FOUND: drop
        ("192.0.2.0/24", 1),       # stale INVALID -> fresh VALID: drop
        ("10.0.0.0/8", 7),         # NOT_FOUND both: no change
    ]
    r = decision_errors(ann, fresh, stale)
    assert r["n"] == 5
    assert r["accept"] == 2 and r["accept_revoked"] == 1 and r["accept_unseen"] == 1
    assert r["drop"] == 2
    assert r["e_accept"] == pytest.approx(0.4)
    assert r["e_drop"] == pytest.approx(0.4)


def test_unit_runner_matches_decision_errors():
    """rov_unit._errors re-implements decision_errors for speed; the two
    must agree on every count."""
    from rov_unit import _errors, _parsed, _states

    fresh = VrpIndex([("AS1", "192.0.2.0/24", 24),
                      ("AS3", "198.51.100.0/24", 24)])
    stale = VrpIndex([("AS2", "192.0.2.0/24", 24),
                      ("AS4", "203.0.113.0/24", 24)])
    peers = {("192.0.2.0/24", 2): 3, ("198.51.100.0/24", 9): 1,
             ("203.0.113.0/24", 5): 2, ("192.0.2.0/24", 1): 4,
             ("10.0.0.0/8", 7): 1}
    rows = _parsed(peers)
    got = _errors(rows, _states(rows, fresh), stale)
    want = decision_errors(list(peers), fresh, stale)
    for key in ("n", "accept", "accept_revoked", "accept_unseen", "drop",
                "e_accept", "e_drop"):
        assert got[key] == want[key], key
    assert got["transitions"] == want["transitions"]
    assert got["weighted"]["accept_peer"] == 3 + 1
    assert got["weighted"]["drop_peer"] == 2 + 4
    assert sorted(f[0] for f in got["accept_flips"]) == ["192.0.2.0/24",
                                                         "198.51.100.0/24"]
