#!/usr/bin/env python3
"""Route Origin Validation (RFC 6811) for PREREG-RPKI-ROV-STALENESS.

A deliberately small, dependency-free validator: the cell grades
decisions made with stale VRP sets, so the validator itself must be
easy to read and is checked by planted cases (MC2) and against an
independent implementation (MC3) before anything is graded.

A VRP is (asn, prefix, max_length). For an announcement (prefix p,
origin o) against a VRP set:

- covering VRPs: those whose prefix covers p (same family, VRP prefix
  length <= len(p), p inside it);
- none -> NOT_FOUND;
- any covering VRP with asn == o, o != 0, and len(p) <= max_length
  -> VALID;
- otherwise -> INVALID.

AS0 VRPs (RFC 7607) cover but never match, so they make a prefix
INVALID for every origin.
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Iterable

VALID = "valid"
INVALID = "invalid"
NOT_FOUND = "not_found"


def _asn(value) -> int:
    s = str(value).strip().upper()
    return int(s[2:]) if s.startswith("AS") else int(s)


class VrpIndex:
    """VRPs keyed by (family, prefix length, network int) so a lookup
    walks only the prefix lengths that actually occur in the set."""

    def __init__(self, vrps: Iterable[tuple]):
        self._by_key: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
        self._lengths = {4: set(), 6: set()}
        self.size = 0
        for asn, prefix, max_length in vrps:
            net = ipaddress.ip_network(str(prefix).strip(), strict=False)
            fam = net.version
            self._by_key[(fam, net.prefixlen, int(net.network_address))].append(
                (_asn(asn), int(max_length)))
            self._lengths[fam].add(net.prefixlen)
            self.size += 1
        self._sorted = {f: sorted(ls) for f, ls in self._lengths.items()}

    def covering_key(self, fam: int, plen: int, addr: int) -> list[tuple[int, int]]:
        width = 32 if fam == 4 else 128
        out: list[tuple[int, int]] = []
        for length in self._sorted[fam]:
            if length > plen:
                break
            mask = ((1 << length) - 1) << (width - length) if length else 0
            out.extend(self._by_key.get((fam, length, addr & mask), ()))
        return out

    def validate_key(self, fam: int, plen: int, addr: int, origin: int) -> str:
        """validate() on a pre-parsed prefix: (family, length, network int)."""
        cover = self.covering_key(fam, plen, addr)
        if not cover:
            return NOT_FOUND
        if origin != 0:
            for asn, max_length in cover:
                if asn == origin and plen <= max_length:
                    return VALID
        return INVALID

    def covering(self, prefix) -> list[tuple[int, int]]:
        return self.covering_key(*prefix_key(prefix))

    def validate(self, prefix, origin) -> str:
        return self.validate_key(*prefix_key(prefix), _asn(origin))


def prefix_key(prefix) -> tuple[int, int, int]:
    """(family, length, network int) for a prefix in text or object form."""
    net = (prefix if isinstance(prefix, (ipaddress.IPv4Network,
                                         ipaddress.IPv6Network))
           else ipaddress.ip_network(str(prefix).strip(), strict=False))
    return net.version, net.prefixlen, int(net.network_address)


def decision_errors(announcements: Iterable[tuple], fresh: VrpIndex,
                    stale: VrpIndex) -> dict:
    """Counts of ROV state transitions stale -> fresh over distinct
    (prefix, origin) announcements, with the two graded error classes:
    accept (fresh INVALID, stale not INVALID) and drop (stale INVALID,
    fresh not INVALID)."""
    trans: dict[str, int] = defaultdict(int)
    n = 0
    for prefix, origin in announcements:
        f = fresh.validate(prefix, origin)
        s = stale.validate(prefix, origin)
        trans[f"{s}->{f}"] += 1
        n += 1
    accept = trans[f"{VALID}->{INVALID}"] + trans[f"{NOT_FOUND}->{INVALID}"]
    drop = trans[f"{INVALID}->{VALID}"] + trans[f"{INVALID}->{NOT_FOUND}"]
    return {
        "n": n,
        "transitions": dict(trans),
        "accept": accept,
        "accept_revoked": trans[f"{VALID}->{INVALID}"],
        "accept_unseen": trans[f"{NOT_FOUND}->{INVALID}"],
        "drop": drop,
        "e_accept": accept / n if n else 0.0,
        "e_drop": drop / n if n else 0.0,
    }
