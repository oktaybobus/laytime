"""GENCON laytime engine.

Pure function: input is a ``basis`` dict, output is a ``result`` dict. No I/O,
no clocks, no randomness. The same basis gives the same result six months
later; in a dispute the stored basis is the evidence.

Time convention: every timestamp in the basis is PORT LOCAL time as a naive
ISO 8601 string (``2026-03-01T06:00``). Sunday and holiday exclusions are
applied on the local calendar day.

Counting regimes (``cp.laytime_basis``):

- ``SHINC``: every hour counts.
- ``SHEX`` / ``WWD``: Sundays and the days listed in ``cp.holidays`` do not
  count. Weather and other stoppages are explicit interruption records, so
  ``WWD`` behaves like ``SHEX`` inside the engine.
- ``cp.unless_used``: excepted days do count (the ship is assumed to have
  worked); idle periods are then deducted through interruption records.

Demurrage: once the allowed time is exhausted every hour counts from that
moment on (*once on demurrage, always on demurrage*). If the charter party
says otherwise, ``cp.interruptions_count_on_demurrage`` keeps deducting
interruption records after demurrage has started.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

DAY_SECONDS = Decimal(86400)
EXCLUDING_BASES = frozenset({"SHEX", "WWD"})

Interval = tuple[datetime, datetime]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def _secs(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _days(seconds: int) -> str:
    return str((Decimal(seconds) / DAY_SECONDS).quantize(Decimal("0.00001"), ROUND_HALF_UP))


def _money(seconds: int, rate_per_day: Decimal) -> Decimal:
    amount = Decimal(seconds) * rate_per_day / DAY_SECONDS
    return amount.quantize(Decimal("0.01"), ROUND_HALF_UP)


def _merge(intervals: Iterable[Interval]) -> list[Interval]:
    ordered = sorted((s, e) for s, e in intervals if e > s)
    merged: list[Interval] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _clip(intervals: Iterable[Interval], lo: datetime, hi: datetime) -> list[Interval]:
    clipped: list[Interval] = []
    for start, end in intervals:
        s, e = max(start, lo), min(end, hi)
        if s < e:
            clipped.append((s, e))
    return clipped


def _is_excepted_day(day: date, holidays: set[str]) -> bool:
    return day.weekday() == 6 or day.isoformat() in holidays


def _excepted_day_intervals(lo: datetime, hi: datetime, holidays: set[str]) -> list[Interval]:
    intervals: list[Interval] = []
    day = lo.date()
    while day <= hi.date():
        if _is_excepted_day(day, holidays):
            start = datetime.combine(day, time.min)
            intervals.append((start, start + timedelta(days=1)))
        day += timedelta(days=1)
    return intervals


def _countable_segments(
    lo: datetime, hi: datetime, exclusions: Iterable[Interval]
) -> list[Interval]:
    merged = _merge(_clip(exclusions, lo, hi))
    segments: list[Interval] = []
    cursor = lo
    for start, end in merged:
        if start > cursor:
            segments.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < hi:
        segments.append((cursor, hi))
    return segments


def _overlap_seconds(intervals: Iterable[Interval], lo: datetime, hi: datetime) -> int:
    return sum(_secs(e - s) for s, e in _merge(_clip(intervals, lo, hi)))


def _allowed_seconds(allowed: dict) -> int:
    if allowed["kind"] == "fixed_days":
        days = Decimal(str(allowed["days"]))
    else:
        days = Decimal(str(allowed["cargo_qty"])) / Decimal(str(allowed["rate_per_day"]))
    return int((days * DAY_SECONDS).quantize(Decimal("1"), ROUND_HALF_UP))


def _prepare_port(port: dict, cp: dict) -> dict:
    nor = port.get("nor_accepted") or port["nor_tendered"]
    start = _dt(nor) + timedelta(hours=cp.get("nor_to_start_hours", 0))
    end = _dt(port["completed_at"])
    start = min(start, end)

    interruptions = [(_dt(item["from"]), _dt(item["to"])) for item in port.get("interruptions", [])]
    exclusions = list(interruptions)
    holidays = set(cp.get("holidays", []))
    if cp["laytime_basis"] in EXCLUDING_BASES and not cp.get("unless_used", False):
        exclusions += _excepted_day_intervals(start, end, holidays)

    return {
        "name": port["name"],
        "start": start,
        "end": end,
        "interruptions": interruptions,
        "exclusions": exclusions,
        "allowed_seconds": _allowed_seconds(port["allowed"]),
    }


def _run_ledger(windows: list[dict], allowed_seconds: int, cp: dict):
    counted = 0
    demurrage_seconds = 0
    demurrage_start: datetime | None = None
    per_window: list[dict] = []

    for window in windows:
        w_counted = 0
        w_demurrage = 0
        w_demurrage_start: datetime | None = None

        if demurrage_start is None:
            for seg_start, seg_end in _countable_segments(
                window["start"], window["end"], window["exclusions"]
            ):
                seg = _secs(seg_end - seg_start)
                if counted + seg >= allowed_seconds:
                    offset = allowed_seconds - counted
                    moment = seg_start + timedelta(seconds=offset)
                    w_counted += offset
                    counted = allowed_seconds
                    demurrage_start = moment
                    w_demurrage_start = moment
                    w_demurrage = _secs(window["end"] - moment)
                    if cp.get("interruptions_count_on_demurrage", False):
                        w_demurrage -= _overlap_seconds(
                            window["interruptions"], moment, window["end"]
                        )
                    demurrage_seconds += w_demurrage
                    break
                counted += seg
                w_counted += seg
        else:
            w_demurrage = _secs(window["end"] - window["start"])
            if cp.get("interruptions_count_on_demurrage", False):
                w_demurrage -= _overlap_seconds(
                    window["interruptions"], window["start"], window["end"]
                )
            demurrage_seconds += w_demurrage

        per_window.append(
            {
                "name": window["name"],
                "laytime_start": _iso(window["start"]),
                "completed_at": _iso(window["end"]),
                "used_days": _days(w_counted),
                "demurrage_start": _iso(w_demurrage_start) if w_demurrage_start else None,
                "demurrage_days": _days(w_demurrage),
            }
        )

    return counted, demurrage_seconds, demurrage_start, per_window


def _project_expiry(start: datetime, remaining_seconds: int, cp: dict) -> datetime:
    """Where the unused allowance would have expired on the calendar.

    Needed for ``despatch_on = all_time_saved`` under SHEX: the saved time
    includes the Sundays and holidays the ship would otherwise have sat through.
    """
    excluding = cp["laytime_basis"] in EXCLUDING_BASES and not cp.get("unless_used", False)
    holidays = set(cp.get("holidays", []))
    cursor = start
    remaining = remaining_seconds
    while remaining > 0:
        if excluding and _is_excepted_day(cursor.date(), holidays):
            cursor = datetime.combine(cursor.date() + timedelta(days=1), time.min)
            continue
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min)
        chunk = min(remaining, _secs(next_midnight - cursor))
        cursor += timedelta(seconds=chunk)
        remaining -= chunk
    return cursor


def _settle(counted, allowed, demurrage_seconds, demurrage_start, last_end, cp, rate):
    despatch_seconds = 0
    if demurrage_start is None and counted < allowed:
        remaining = allowed - counted
        if cp.get("despatch_on", "working_time_saved") == "all_time_saved":
            despatch_seconds = _secs(_project_expiry(last_end, remaining, cp) - last_end)
        else:
            despatch_seconds = remaining

    fraction = Decimal("0.5") if cp.get("despatch_fraction", "half") == "half" else Decimal("1")
    demurrage_amount = _money(demurrage_seconds, rate)
    despatch_amount = _money(despatch_seconds, rate * fraction)
    return despatch_seconds, demurrage_amount, despatch_amount


def compute_laytime(basis: dict) -> dict:
    """Compute laytime used, demurrage and despatch for one voyage charter.

    See the module docstring and README for the ``basis`` schema. Raises
    ``KeyError`` when a required field is missing; the engine never guesses.
    """
    cp = basis["cp"]
    rate = Decimal(str(cp["demurrage_rate_per_day"]))
    windows = [_prepare_port(port, cp) for port in basis["ports"]]

    ports_out: list[dict] = []
    total_allowed = 0
    total_counted = 0
    total_demurrage = 0
    total_despatch = 0
    demurrage_amount = Decimal("0")
    despatch_amount = Decimal("0")

    if cp.get("reversible", False):
        total_allowed = sum(w["allowed_seconds"] for w in windows)
        counted, dem_secs, dem_start, ports_out = _run_ledger(windows, total_allowed, cp)
        total_counted, total_demurrage = counted, dem_secs
        despatch_secs, demurrage_amount, despatch_amount = _settle(
            counted, total_allowed, dem_secs, dem_start, windows[-1]["end"], cp, rate
        )
        total_despatch = despatch_secs
    else:
        for window in windows:
            allowed = window["allowed_seconds"]
            counted, dem_secs, dem_start, port_rows = _run_ledger([window], allowed, cp)
            despatch_secs, dem_amount, desp_amount = _settle(
                counted, allowed, dem_secs, dem_start, window["end"], cp, rate
            )
            row = port_rows[0]
            row["allowed_days"] = _days(allowed)
            row["despatch_days"] = _days(despatch_secs)
            ports_out.append(row)
            total_allowed += allowed
            total_counted += counted
            total_demurrage += dem_secs
            total_despatch += despatch_secs
            demurrage_amount += dem_amount
            despatch_amount += desp_amount

    net = demurrage_amount - despatch_amount
    return {
        "reversible": bool(cp.get("reversible", False)),
        "laytime_basis": cp["laytime_basis"],
        "allowed_days": _days(total_allowed),
        "used_days": _days(total_counted),
        "demurrage_days": _days(total_demurrage),
        "despatch_days": _days(total_despatch),
        "demurrage_amount": str(demurrage_amount),
        "despatch_amount": str(despatch_amount),
        "net_amount": str(net),
        "currency": cp.get("currency", "USD"),
        "ports": ports_out,
    }
