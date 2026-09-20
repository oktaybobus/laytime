"""GENCON laytime engine.

Pure function: input is a ``basis`` dict, output is a ``result`` dict. No I/O,
no clocks, no randomness. The same basis gives the same result six months
later; in a dispute the stored basis is the evidence.

Time convention: every timestamp in the basis is PORT LOCAL time as a naive
ISO 8601 string (``2026-03-01T06:00``). Sunday and holiday exclusions are
applied on the local calendar day.

Counting regimes (``cp.laytime_basis``):

- ``SHINC``: every hour counts; holidays are ignored.
- Anything else is an *excepting* regime. Its weekly excepted periods are
  written out in ``cp.excepted_periods`` as weekday + time windows
  (``SATPMSHEX``: Saturday 12:00 to Monday 08:00). The engine never derives
  hours from the regime name. Only ``SHEX`` and ``WWD`` may omit the list,
  which then means the whole of Sunday, as in 0.1.0.
- Weather and other stoppages are explicit interruption records, so ``WWD``
  behaves like ``SHEX`` inside the engine.
- ``cp.holidays``: a ``YYYY-MM-DD`` string is a whole day; a mapping
  ``{"date", "from", "to"}`` is part of one. ``cp.holiday_eve_from`` excepts
  the day before each whole-day holiday from that hour on;
  ``cp.holiday_resume_time`` stretches each holiday that runs to the end of
  its day until that hour on the following day.
- ``cp.unless_used``: with ``cp.unless_used_mode = "actual_time_used"`` only
  the ``port.worked`` intervals count inside excepted periods. Without a mode
  (``"whole_period"``, the 0.1.0 behaviour) excepted periods count in full and
  idle time is deducted through interruption records.

A basis without the 0.2.0 keys gives the result 0.1.0 gave.

Demurrage: once the allowed time is exhausted every hour counts from that
moment on (*once on demurrage, always on demurrage*). If the charter party
says otherwise, ``cp.interruptions_count_on_demurrage`` keeps deducting
interruption records after demurrage has started.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

DAY_SECONDS = Decimal(86400)
WEEK = timedelta(days=7)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SUNDAY_BASES = frozenset({"SHEX", "WWD"})
SUNDAY_WINDOW = (timedelta(days=6), WEEK)
UNLESS_USED_MODES = frozenset({"whole_period", "actual_time_used"})

Interval = tuple[datetime, datetime]


def _dt(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        raise ValueError(f"timestamps are port-local and carry no offset: {value!r}")
    return moment


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


def _time(value: str) -> time:
    if not re.fullmatch(r"\d{2}:\d{2}", str(value)):
        raise ValueError(f"time of day is written HH:MM: {value!r}")
    return time.fromisoformat(value)


def _day(value: str) -> date:
    # fromisoformat also reads 20260304 and 2026-W10-3; 0.1.0 matched YYYY-MM-DD only.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        raise ValueError(f"holiday dates are written YYYY-MM-DD: {value!r}")
    return date.fromisoformat(value)


def _week_offset(point: dict, *, closing: bool = False) -> timedelta:
    if point["weekday"] not in WEEKDAYS:
        raise ValueError(f"weekday must be one of {', '.join(WEEKDAYS)}: {point['weekday']!r}")
    day = timedelta(days=WEEKDAYS.index(point["weekday"]))
    if closing and point["time"] == "24:00":
        return day + timedelta(days=1)
    at = _time(point["time"])
    return day + timedelta(hours=at.hour, minutes=at.minute)


def _weekly_windows(cp: dict) -> list[tuple[timedelta, timedelta]]:
    """Excepted windows as offsets from Monday 00:00; a window may run into the next week."""
    regime = cp["laytime_basis"]
    periods = cp.get("excepted_periods")
    if regime == "SHINC":
        if periods:
            raise ValueError("SHINC counts every hour; cp.excepted_periods must be empty")
        return []
    if periods is None:
        if regime not in SUNDAY_BASES:
            raise ValueError(f"laytime_basis {regime!r} needs cp.excepted_periods")
        return [SUNDAY_WINDOW]

    if not isinstance(periods, list) or not all(isinstance(p, dict) for p in periods):
        raise ValueError("cp.excepted_periods is a list of {from, to} mappings")
    windows: list[tuple[timedelta, timedelta]] = []
    for period in periods:
        start = _week_offset(period["from"])
        end = _week_offset(period["to"], closing=True) % WEEK
        if start == end:
            raise ValueError("an excepted period cannot start and end at the same moment")
        windows.append((start, end if end > start else end + WEEK))

    monday = datetime(2001, 1, 1)
    one_week = [
        (monday + start - shift, monday + end - shift)
        for start, end in windows
        for shift in (timedelta(0), WEEK)
    ]
    if _overlap_seconds(one_week, monday, monday + WEEK) >= _secs(WEEK):
        raise ValueError("cp.excepted_periods cover the whole week; nothing would ever count")
    return windows


def _holiday_intervals(cp: dict) -> list[Interval]:
    eve_from = cp.get("holiday_eve_from")
    resume = cp.get("holiday_resume_time")
    intervals: list[Interval] = []
    for entry in cp.get("holidays", []):
        if isinstance(entry, str):
            entry = {"date": entry}
        day = _day(entry["date"])
        next_midnight = datetime.combine(day + timedelta(days=1), time.min)
        start = datetime.combine(day, _time(entry.get("from", "00:00")))
        until = entry.get("to", "24:00")
        end = next_midnight if until == "24:00" else datetime.combine(day, _time(until))
        if end <= start:
            raise ValueError(f"holiday {entry['date']} ends before it starts")

        whole_day = start.time() == time.min and end == next_midnight
        if whole_day and eve_from:
            intervals.append((datetime.combine(day - timedelta(days=1), _time(eve_from)), start))
        if end == next_midnight and resume:
            end = datetime.combine(next_midnight.date(), _time(resume))
        intervals.append((start, end))
    return intervals


def excepted_intervals(cp: dict, lo: datetime, hi: datetime) -> list[Interval]:
    """The periods between ``lo`` and ``hi`` that do not count under the charter party.

    Weekly windows and holidays merged and clipped. This is the charter-party
    calendar before *unless used* is applied: under ``whole_period`` these
    periods count in full, under ``actual_time_used`` the port's ``worked``
    intervals inside them count.
    """
    if hi < lo:
        raise ValueError("excepted_intervals: the range ends before it starts")
    windows = _weekly_windows(cp)
    intervals = _holiday_intervals(cp)
    if cp["laytime_basis"] == "SHINC":
        return []
    week_start = datetime.combine(lo.date() - timedelta(days=lo.weekday()), time.min) - WEEK
    while week_start < hi:
        intervals += [(week_start + start, week_start + end) for start, end in windows]
        week_start += WEEK
    return _merge(_clip(intervals, lo, hi))


def _unless_used_mode(cp: dict) -> str | None:
    mode = cp.get("unless_used_mode", "whole_period")
    if mode not in UNLESS_USED_MODES:
        raise ValueError(f"unless_used_mode must be one of {sorted(UNLESS_USED_MODES)}: {mode!r}")
    if not cp.get("unless_used", False):
        if "unless_used_mode" in cp:
            raise ValueError("cp.unless_used_mode is given but cp.unless_used is not true")
        return None
    return mode


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
        rate = Decimal(str(allowed["rate_per_day"]))
        if rate <= 0:
            raise ValueError(f"allowed.rate_per_day must be positive: {allowed['rate_per_day']!r}")
        days = Decimal(str(allowed["cargo_qty"])) / rate
    if days < 0:
        raise ValueError("the time allowed cannot be negative")
    return int((days * DAY_SECONDS).quantize(Decimal("1"), ROUND_HALF_UP))


def _prepare_port(port: dict, cp: dict) -> dict:
    nor = port.get("nor_accepted") or port["nor_tendered"]
    start = _dt(nor) + timedelta(hours=cp.get("nor_to_start_hours", 0))
    end = _dt(port["completed_at"])
    start = min(start, end)

    interruptions = [(_dt(item["from"]), _dt(item["to"])) for item in port.get("interruptions", [])]
    exclusions = list(interruptions)
    mode = _unless_used_mode(cp)
    excepted = excepted_intervals(cp, start, end)
    if mode == "actual_time_used":
        worked = [(_dt(item["from"]), _dt(item["to"])) for item in port.get("worked", [])]
        excepted = [idle for s, e in excepted for idle in _countable_segments(s, e, worked)]
    if mode != "whole_period":
        exclusions += excepted

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

    Needed for ``despatch_on = all_time_saved`` under an excepting regime: the
    saved time includes the excepted periods the ship would otherwise have sat
    through. No future work is assumed inside them.
    """
    skip_excepted = _unless_used_mode(cp) != "whole_period"
    cursor = start
    remaining = remaining_seconds
    while remaining > 0:
        lookahead = cursor + timedelta(seconds=remaining) + WEEK
        excepted = excepted_intervals(cp, cursor, lookahead) if skip_excepted else []
        for seg_start, seg_end in _countable_segments(cursor, lookahead, excepted):
            chunk = min(remaining, _secs(seg_end - seg_start))
            remaining -= chunk
            cursor = seg_start + timedelta(seconds=chunk)
            if remaining == 0:
                return cursor
        cursor = lookahead
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
        if not windows:
            raise ValueError("a reversible basis needs at least one port")
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
