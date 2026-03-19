"""Pure helpers for comparison benchmark output (tables + JSON payload). Stdlib only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict


class ToolTotalsDict(TypedDict, total=False):
    total_seconds: float
    total_mbps: float
    total_mb: float
    status: str


def _format_total_seconds(sec: float) -> str:
    """Enough precision that sub-ms totals do not show as 0.000."""
    if sec <= 0:
        return "0.000000"
    if sec >= 10:
        return f"{sec:.3f}"
    if sec >= 1:
        return f"{sec:.4f}"
    if sec >= 0.01:
        return f"{sec:.5f}"
    return f"{sec:.6f}"


def _format_speedup_ratio(ratio: float) -> str:
    """
    Text for (competitor_total_seconds / omnichunk_total_seconds).
    Values > 1 mean omnichunk is faster on aggregate; < 1 mean omnichunk is slower.
    """
    if ratio <= 0:
        return "0"
    if ratio >= 100:
        return f"{ratio:.0f}"
    if ratio >= 10:
        return f"{ratio:.1f}".rstrip("0").rstrip(".")
    if ratio >= 1:
        return f"{ratio:.2f}".rstrip("0").rstrip(".")
    if ratio >= 0.0001:
        return f"{ratio:.4f}".rstrip("0").rstrip(".")
    return f"{ratio:.2e}"


def aggregate_tool_totals(
    *,
    tool_rows: dict[str, list[Any]],
) -> dict[str, ToolTotalsDict]:
    """Aggregate per-tool totals from lists of row objects with .data_bytes, .seconds, .status."""
    out: dict[str, ToolTotalsDict] = {}
    for tool_name, rows in tool_rows.items():
        statuses = {getattr(r, "status", "") for r in rows}
        ok_rows = [r for r in rows if getattr(r, "status", "") == "ok"]
        total_bytes = sum(int(getattr(r, "data_bytes", 0)) for r in ok_rows)
        total_seconds = sum(float(getattr(r, "seconds", 0.0)) for r in ok_rows)
        total_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0
        total_mbps = (total_bytes / (1024 * 1024)) / total_seconds if total_seconds > 0 else 0.0

        if statuses == {"ok"}:
            st = "ok"
        elif "ok" in statuses:
            st = "partial"
        elif "unavailable" in statuses and len(statuses) == 1:
            st = "unavailable"
        else:
            st = "error"

        out[tool_name] = {
            "total_seconds": total_seconds,
            "total_mbps": total_mbps,
            "total_mb": total_mb,
            "status": st,
        }
    return out


def format_comparison_summary_table(
    *,
    tool_order: list[str],
    aggregates: dict[str, ToolTotalsDict],
) -> str:
    """ASCII box table: Tool | Total MB | Seconds | MBps; SKIP for unavailable; ✓ on fastest."""
    rows_out: list[tuple[str, str, str, str, bool]] = []
    timed: list[tuple[str, float]] = []
    for name in tool_order:
        agg = aggregates.get(name, {})
        st = agg.get("status", "error")
        if st == "unavailable":
            rows_out.append((name, "SKIP", "SKIP", "SKIP", False))
            continue
        sec = float(agg.get("total_seconds", 0.0))
        if st in ("ok", "partial") and sec > 0:
            timed.append((name, sec))
        mb = float(agg.get("total_mb", 0.0))
        mbps = float(agg.get("total_mbps", 0.0))
        rows_out.append((name, f"{mb:.4f}", _format_total_seconds(sec), f"{mbps:.2f}", False))

    winner: str | None = None
    if timed:
        winner = min(timed, key=lambda x: (x[1], x[0]))[0]

    labeled: list[tuple[str, str, str, str]] = []
    for name, smb, ssec, smbps, _ in rows_out:
        mark = " ✓" if winner and name == winner else ""
        labeled.append((name + mark, smb, ssec, smbps))

    c0 = max(len("Tool"), *(len(r[0]) for r in labeled))
    c1 = max(len("Total MB"), *(len(r[1]) for r in labeled))
    c2 = max(len("Seconds"), *(len(r[2]) for r in labeled))
    c3 = max(len("MBps"), *(len(r[3]) for r in labeled))

    top = f"┌{'─' * (c0 + 2)}┬{'─' * (c1 + 2)}┬{'─' * (c2 + 2)}┬{'─' * (c3 + 2)}┐"
    hdr = (
        f"│ {'Tool'.ljust(c0)} │ {'Total MB'.rjust(c1)} │ "
        f"{'Seconds'.rjust(c2)} │ {'MBps'.rjust(c3)} │"
    )
    sep = f"├{'─' * (c0 + 2)}┼{'─' * (c1 + 2)}┼{'─' * (c2 + 2)}┼{'─' * (c3 + 2)}┤"
    bot = f"└{'─' * (c0 + 2)}┴{'─' * (c1 + 2)}┴{'─' * (c2 + 2)}┴{'─' * (c3 + 2)}┘"

    lines = [top, hdr, sep]
    for lab, smb, ssec, smbps in labeled:
        lines.append(
            f"│ {lab.ljust(c0)} │ {smb.rjust(c1)} │ {ssec.rjust(c2)} │ {smbps.rjust(c3)} │"
        )
    lines.append(bot)
    return "\n".join(lines)


def format_speedup_lines(
    *,
    omnichunk_seconds: float,
    aggregates: dict[str, ToolTotalsDict],
    tool_order: list[str],
) -> list[str]:
    """Lines like 'Speedup vs langchain_recursive: 4.9×' for each ok non-omnichunk tool."""
    lines: list[str] = []
    if omnichunk_seconds <= 0:
        return ["No baseline available"]

    competitors_ok = False
    for name in tool_order:
        if name == "omnichunk":
            continue
        agg = aggregates.get(name, {})
        if agg.get("status") != "ok":
            continue
        other = float(agg.get("total_seconds", 0.0))
        if other <= 0:
            continue
        competitors_ok = True
        ratio = other / omnichunk_seconds
        lines.append(f"Speedup vs {name}: {_format_speedup_ratio(ratio)}×")

    if not competitors_ok:
        return ["No baseline available"]
    return lines


def build_comparison_json_payload(
    *,
    scenario_names: list[str],
    tool_order: list[str],
    aggregates: dict[str, ToolTotalsDict],
    winner: str | None,
) -> dict[str, Any]:
    """Explicit dict for JSON (stable key order via insertion)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    tools_block: dict[str, Any] = {}
    for name in tool_order:
        agg = aggregates.get(name, {})
        st = str(agg.get("status", "error"))
        if st == "unavailable":
            tools_block[name] = {"total_seconds": 0.0, "total_mbps": 0.0, "status": "unavailable"}
        else:
            tools_block[name] = {
                "total_seconds": round(float(agg.get("total_seconds", 0.0)), 6),
                "total_mbps": round(float(agg.get("total_mbps", 0.0)), 6),
                "status": st,
            }

    omni = aggregates.get("omnichunk", {})
    omni_sec = float(omni.get("total_seconds", 0.0))

    speedup: dict[str, float] = {}
    for name in tool_order:
        if name == "omnichunk":
            continue
        agg = aggregates.get(name, {})
        if agg.get("status") != "ok":
            continue
        other = float(agg.get("total_seconds", 0.0))
        if omni_sec > 0 and other > 0:
            key = f"omnichunk_vs_{name}"
            speedup[key] = round(other / omni_sec, 4)

    payload: dict[str, Any] = {
        "timestamp": ts,
        "scenarios": list(scenario_names),
        "tools": tools_block,
        "speedup": speedup,
        "winner": winner if winner else "",
    }
    return payload


def comparison_exit_code(
    *,
    aggregates: dict[str, ToolTotalsDict],
    tool_order: list[str],
) -> int:
    """
    0 if omnichunk is fastest or within 5% of fastest among timed tools; else 1.
    If omnichunk has no timing, or no other tool has status ok with time > 0, return 0.
    """
    omni = aggregates.get("omnichunk", {})
    omni_sec = float(omni.get("total_seconds", 0.0))
    omni_st = omni.get("status", "")
    if omni_st not in ("ok", "partial") or omni_sec <= 0:
        return 0

    has_ok_competitor = False
    for name in tool_order:
        if name == "omnichunk":
            continue
        agg = aggregates.get(name, {})
        if agg.get("status") != "ok":
            continue
        if float(agg.get("total_seconds", 0.0)) > 0:
            has_ok_competitor = True
            break
    if not has_ok_competitor:
        return 0

    timed: list[float] = []
    for name in tool_order:
        agg = aggregates.get(name, {})
        if agg.get("status") not in ("ok", "partial"):
            continue
        t = float(agg.get("total_seconds", 0.0))
        if t > 0:
            timed.append(t)
    if not timed:
        return 0

    fastest_sec = min(timed)
    if omni_sec <= fastest_sec * 1.05:
        return 0
    return 1


def _kb_label(nbytes: int) -> str:
    if nbytes >= 1024:
        return f"{nbytes // 1024} KB"
    return f"{nbytes} B"


def format_scenario_benchmark_table(
    rows: list[tuple[str, int, int, float, float]],
) -> str:
    """
    Plain summary after CSV: Scenario | Bytes | Chunks | Seconds | MBps.
    rows: (name, data_bytes, chunk_count, seconds, mbps)
    """
    if not rows:
        return ""

    body: list[tuple[str, str, str, str, str]] = []
    tb, tc, ts = 0, 0, 0.0
    for name, b, c, sec, mbps in rows:
        tb += b
        tc += c
        ts += sec
        body.append((_kb_label(b), str(c), f"{sec:.3f}", f"{mbps:.1f}", name))

    total_mbps_val = (tb / (1024 * 1024)) / ts if ts > 0 else 0.0
    body.append((_kb_label(tb), str(tc), f"{ts:.3f}", f"{total_mbps_val:.1f}", "TOTAL"))

    c0 = max(len("Scenario"), *(len(r[4]) for r in body))
    c1 = max(len("Bytes"), *(len(r[0]) for r in body))
    c2 = max(len("Chunks"), *(len(r[1]) for r in body))
    c3 = max(len("Seconds"), *(len(r[2]) for r in body))
    c4 = max(len("MBps"), *(len(r[3]) for r in body))

    sep = "─" * (c0 + c1 + c2 + c3 + c4 + 12)
    lines = [
        f"{'Scenario'.ljust(c0)}  {'Bytes'.rjust(c1)}  {'Chunks'.rjust(c2)}  "
        f"{'Seconds'.rjust(c3)}  {'MBps'.rjust(c4)}",
        sep,
    ]
    for bb, ch, sec, mb, name in body[:-1]:
        lines.append(
            f"{name.ljust(c0)}  {bb.rjust(c1)}  {ch.rjust(c2)}  {sec.rjust(c3)}  {mb.rjust(c4)}"
        )
    bb, ch, sec, mb, name = body[-1]
    lines.append(
        f"{name.ljust(c0)}  {bb.rjust(c1)}  {ch.rjust(c2)}  {sec.rjust(c3)}  {mb.rjust(c4)}"
    )
    return "\n".join(lines)
