from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from omnichunk.types import Chunk

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def dedup_chunks(
    chunks: Sequence[Chunk],
    *,
    method: Literal["exact", "simhash", "minhash"] = "simhash",
    threshold: float = 0.85,
) -> tuple[list[Chunk], dict[int, int]]:
    """Remove near-duplicate chunks; ``duplicate_map`` maps removed index → kept index."""
    if not chunks:
        return [], {}
    if method == "exact":
        return _dedup_exact(chunks)
    if method == "simhash":
        return _dedup_simhash(chunks, threshold=threshold)
    return _dedup_minhash(chunks, threshold=threshold)


def _dedup_exact(chunks: Sequence[Chunk]) -> tuple[list[Chunk], dict[int, int]]:
    seen: dict[str, int] = {}
    unique: list[Chunk] = []
    dup: dict[int, int] = {}
    order_key = sorted(range(len(chunks)), key=lambda i: chunks[i].index)
    for i in order_key:
        ch = chunks[i]
        h = hashlib.sha256(ch.text.encode("utf-8")).hexdigest()
        if h in seen:
            dup[ch.index] = seen[h]
        else:
            seen[h] = ch.index
            unique.append(ch)
    unique.sort(key=lambda c: c.index)
    return unique, dup


def _simhash_64(text: str) -> int:
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return 0
    weights: dict[str, int] = {}
    for t in tokens:
        weights[t] = weights.get(t, 0) + 1
    vec = [0] * 64
    for tok, w in weights.items():
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for bit in range(64):
            if (h >> bit) & 1:
                vec[bit] += w
            else:
                vec[bit] -= w
    out = 0
    for bit in range(64):
        if vec[bit] >= 0:
            out |= 1 << bit
    return out


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _dedup_simhash(
    chunks: Sequence[Chunk],
    *,
    threshold: float,
) -> tuple[list[Chunk], dict[int, int]]:
    max_h = max(0, min(64, int((1.0 - threshold) * 64)))
    sigs = [_simhash_64(c.text) for c in chunks]
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    dup: dict[int, int] = {}
    kept: list[Chunk] = []

    order = sorted(range(len(chunks)), key=lambda i: chunks[i].index)
    for i in order:
        sig = sigs[i]
        candidates: set[int] = set()
        for b in range(4):
            band = (sig >> (16 * b)) & 0xFFFF
            candidates.update(buckets[(b, band)])

        match_rep: int | None = None
        for j in sorted(candidates):
            if _hamming(sig, sigs[j]) <= max_h:
                match_rep = chunks[j].index
                break

        if match_rep is not None:
            dup[chunks[i].index] = match_rep
        else:
            kept.append(chunks[i])
            for b in range(4):
                band = (sig >> (16 * b)) & 0xFFFF
                buckets[(b, band)].append(i)

    kept.sort(key=lambda c: c.index)
    return kept, dup


def _token_set(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(text.lower()))


def _perm_mixed(token_hash: int, perm: int) -> int:
    """Deterministic permuted hash from one 32-bit token digest (LSH banding only)."""
    return (token_hash ^ (perm * 0x9E3779B9) ^ ((perm & 31) << 27)) & 0xFFFFFFFF


def _dedup_minhash(
    chunks: Sequence[Chunk],
    *,
    threshold: float,
) -> tuple[list[Chunk], dict[int, int]]:
    sets = [_token_set(c.text) for c in chunks]
    n_bands = 8
    rows = 4
    n_perm = n_bands * rows

    def _sig(toks: frozenset[str]) -> list[int]:
        if not toks:
            return [0] * n_perm
        items = sorted(toks)
        token_hashes = [
            int(hashlib.md5(t.encode("utf-8")).hexdigest()[:8], 16) for t in items
        ]
        out: list[int] = []
        for k in range(n_perm):
            m = min((_perm_mixed(th, k) for th in token_hashes), default=0)
            out.append(m)
        return out

    sigs = [_sig(s) for s in sets]
    buckets: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
    dup: dict[int, int] = {}
    order = sorted(range(len(chunks)), key=lambda i: chunks[i].index)

    for i in order:
        sig = sigs[i]
        candidates: set[int] = set()
        for b in range(n_bands):
            start = b * rows
            band_tuple = tuple(sig[start : start + rows])
            candidates.update(buckets[(b, band_tuple)])

        match_rep: int | None = None
        for j in sorted(candidates):
            a, bset = sets[i], sets[j]
            if a and bset:
                jac = len(a & bset) / len(a | bset)
            elif not a and not bset:
                jac = 1.0
            else:
                jac = 0.0
            if jac >= threshold:
                match_rep = chunks[j].index
                break

        if match_rep is not None:
            dup[chunks[i].index] = match_rep
        else:
            for b in range(n_bands):
                start = b * rows
                band_tuple = tuple(sig[start : start + rows])
                buckets[(b, band_tuple)].append(i)

    kept = [c for c in chunks if c.index not in dup]
    kept.sort(key=lambda c: c.index)
    return kept, dup
