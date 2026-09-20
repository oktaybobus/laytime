"""Weekly excepted periods, partial holidays, holiday eve/resume and *unless used*.

Every expected value is worked out by hand in the test's docstring. These are
rule tests on synthetic statements of facts; the golden file holds the cases
verified against real documents.

Calendar anchor (2026): Sun 01 Mar, Mon 02, Tue 03, Wed 04, Thu 05, Fri 06,
Sat 07, Sun 08, Mon 09, Tue 10.
"""

from datetime import datetime

import pytest

from laytime import compute_laytime, excepted_intervals

SATPM = [{"from": {"weekday": "sat", "time": "12:00"}, "to": {"weekday": "mon", "time": "08:00"}}]
SUNDAY = [{"from": {"weekday": "sun", "time": "00:00"}, "to": {"weekday": "mon", "time": "00:00"}}]
FRIDAY = [{"from": {"weekday": "fri", "time": "00:00"}, "to": {"weekday": "sat", "time": "00:00"}}]


def basis(cp_extra=None, ports=None):
    cp = {
        "laytime_basis": "SHEX",
        "unless_used": False,
        "reversible": False,
        "demurrage_rate_per_day": "8000",
        "currency": "USD",
        "despatch_fraction": "half",
        "despatch_on": "working_time_saved",
        "nor_to_start_hours": 0,
        "holidays": [],
    }
    cp.update(cp_extra or {})
    return {"cp": cp, "ports": ports or []}


def port(nor="2026-03-06T08:00", completed="2026-03-10T08:00", days="10", **kwargs):
    data = {
        "name": "Novorossiysk",
        "purpose": "loading",
        "nor_tendered": nor,
        "nor_accepted": nor,
        "completed_at": completed,
        "allowed": {"kind": "fixed_days", "days": days},
        "interruptions": [],
    }
    data.update(kwargs)
    return data


def used(cp_extra, **port_kwargs):
    return compute_laytime(basis(cp_extra, [port(**port_kwargs)]))["used_days"]


# --- weekly windows -----------------------------------------------------------------------


def test_satpmshex_excludes_saturday_noon_to_monday_morning():
    """Fri 08:00 -> Tue 08:00 is 96 h; Sat 12:00 -> Mon 08:00 (44 h) is excepted: 52 h."""
    assert used({"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM}) == "2.16667"


def test_explicit_sunday_window_equals_legacy_shex():
    """Writing the Sunday window out must not change a single field of a 0.1.0 SHEX result."""
    legacy = compute_laytime(basis(None, [port(days="1")]))
    explicit = compute_laytime(basis({"excepted_periods": SUNDAY}, [port(days="1")]))
    assert explicit == legacy


def test_fhex_excludes_friday_and_counts_sunday():
    """Thu 08:00 -> Mon 08:00 is 96 h; only Friday (24 h) is excepted: 72 h."""
    result = used(
        {"laytime_basis": "FHEX", "excepted_periods": FRIDAY},
        nor="2026-03-05T08:00",
        completed="2026-03-09T08:00",
    )
    assert result == "3.00000"


def test_window_may_wrap_over_the_end_of_the_week():
    """Sun 18:00 -> Mon 06:00 wraps Sunday into Monday. Sun 12:00 -> Mon 12:00: 24 h - 12 h."""
    wrap = [
        {"from": {"weekday": "sun", "time": "18:00"}, "to": {"weekday": "mon", "time": "06:00"}}
    ]
    result = used({"excepted_periods": wrap}, nor="2026-03-08T12:00", completed="2026-03-09T12:00")
    assert result == "0.50000"


def test_laytime_starting_inside_a_window_waits_for_its_end():
    """NOR Sun 10:00 sits inside Sat 12:00 -> Mon 08:00; counting runs Mon 08:00 -> 20:00."""
    result = used(
        {"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM},
        nor="2026-03-01T10:00",
        completed="2026-03-02T20:00",
    )
    assert result == "0.50000"


def test_empty_window_list_leaves_only_holidays():
    """'Holidays excepted' without a weekly day: Sunday counts, the holiday does not."""
    result = used({"excepted_periods": [], "holidays": ["2026-03-09"]})
    # 96 h less Mon 09 00:00 -> Tue 10 00:00 (24 h) = 72 h.
    assert result == "3.00000"


# --- holidays -----------------------------------------------------------------------------


def test_half_day_holiday_from_an_hour():
    """Mon 08:00 -> Thu 08:00 is 72 h; Wed 13:00 -> 24:00 (11 h) is excepted: 61 h."""
    result = used(
        {"holidays": [{"date": "2026-03-04", "from": "13:00"}]},
        nor="2026-03-02T08:00",
        completed="2026-03-05T08:00",
    )
    assert result == "2.54167"


def test_partial_holiday_until_an_hour():
    """Wed 00:00 -> 08:00 (8 h) excepted out of 72 h: 64 h."""
    result = used(
        {"holidays": [{"date": "2026-03-04", "to": "08:00"}]},
        nor="2026-03-02T08:00",
        completed="2026-03-05T08:00",
    )
    assert result == "2.66667"


def test_holiday_eve_applies_to_full_day_holidays():
    """Mon 08:00 -> Fri 08:00 is 96 h; Wed 17:00 -> Fri 00:00 (7 h + 24 h) excepted: 65 h."""
    result = used(
        {"holidays": ["2026-03-05"], "holiday_eve_from": "17:00"},
        nor="2026-03-02T08:00",
        completed="2026-03-06T08:00",
    )
    assert result == "2.70833"


def test_holiday_eve_does_not_apply_to_partial_holidays():
    """A half-day holiday is itself the eve; only Thu 13:00 -> 24:00 (11 h) goes: 85 h."""
    result = used(
        {"holidays": [{"date": "2026-03-05", "from": "13:00"}], "holiday_eve_from": "17:00"},
        nor="2026-03-02T08:00",
        completed="2026-03-06T08:00",
    )
    assert result == "3.54167"


def test_holiday_runs_until_the_resume_hour_next_day():
    """Wed 00:00 -> Thu 08:00 (32 h) excepted out of 96 h: 64 h."""
    result = used(
        {"holidays": ["2026-03-04"], "holiday_resume_time": "08:00"},
        nor="2026-03-02T08:00",
        completed="2026-03-06T08:00",
    )
    assert result == "2.66667"


def test_resume_hour_yields_to_the_next_days_own_rule():
    """Holiday Sat, Sunday window to Mon 00:00: Sat 00:00 -> Mon 00:00 (48 h) of 96 h."""
    result = used({"holidays": ["2026-03-07"], "holiday_resume_time": "08:00"})
    assert result == "2.00000"


def test_holidays_are_ignored_under_shinc():
    assert used({"laytime_basis": "SHINC", "holidays": ["2026-03-07"]}) == "4.00000"


# --- unless used --------------------------------------------------------------------------

ACTUAL = {
    "laytime_basis": "SATPMSHEX",
    "excepted_periods": SATPM,
    "unless_used": True,
    "unless_used_mode": "actual_time_used",
}


def test_actual_time_used_counts_only_the_worked_hours():
    """52 h outside the weekend plus Sat 13:00 -> 17:00 worked: 56 h."""
    worked = [{"from": "2026-03-07T13:00", "to": "2026-03-07T17:00"}]
    assert used(ACTUAL, worked=worked) == "2.33333"


def test_interruption_inside_worked_time_is_still_deducted():
    """Rain Sat 14:00 -> 15:00 inside the overtime: 55 h."""
    worked = [{"from": "2026-03-07T13:00", "to": "2026-03-07T17:00"}]
    rain = [{"from": "2026-03-07T14:00", "to": "2026-03-07T15:00", "reason": "rain"}]
    assert used(ACTUAL, worked=worked, interruptions=rain) == "2.29167"


def test_actual_time_used_without_work_records_counts_nothing_extra():
    assert used(ACTUAL) == "2.16667"


def test_work_outside_excepted_periods_changes_nothing():
    worked = [{"from": "2026-03-06T10:00", "to": "2026-03-06T12:00"}]
    assert used(ACTUAL, worked=worked) == "2.16667"


def test_worked_is_ignored_when_the_cp_has_no_unless_used():
    worked = [{"from": "2026-03-07T13:00", "to": "2026-03-07T17:00"}]
    cp = {"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM}
    assert used(cp, worked=worked) == "2.16667"


def test_legacy_unless_used_still_counts_the_whole_period():
    """0.1.0 bases carry ``unless_used: true`` without a mode: every hour counts."""
    cp = {"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM, "unless_used": True}
    assert used(cp) == "4.00000"


# --- demurrage and despatch ---------------------------------------------------------------


def test_once_on_demurrage_the_weekend_is_not_deducted():
    """1 day allowed from Fri 08:00: demurrage from Sat 08:00 straight to Tue 08:00."""
    result = compute_laytime(
        basis({"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM}, [port(days="1")])
    )
    assert result["ports"][0]["demurrage_start"] == "2026-03-07T08:00"
    assert result["demurrage_days"] == "3.00000"
    assert result["demurrage_amount"] == "24000.00"


def test_allowance_running_out_after_the_weekend():
    """36 h allowed: 28 h to Sat 12:00, the other 8 h from Mon 08:00 -> demurrage Mon 16:00."""
    result = compute_laytime(
        basis({"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM}, [port(days="1.5")])
    )
    assert result["ports"][0]["demurrage_start"] == "2026-03-09T16:00"
    assert result["demurrage_days"] == "0.66667"


def test_all_time_saved_projects_across_the_excepted_weekend():
    """6 days allowed, Mon 08:00 -> Wed 08:00 used. The 96 h left run Wed 08:00 -> Sat 12:00
    (76 h), then 20 h from Mon 08:00 -> Tue 10 04:00. Saved: 5 d 20 h = 140 h."""
    cp = {
        "laytime_basis": "SATPMSHEX",
        "excepted_periods": SATPM,
        "despatch_on": "all_time_saved",
        "demurrage_rate_per_day": "6000",
    }
    result = compute_laytime(
        basis(cp, [port(nor="2026-03-02T08:00", completed="2026-03-04T08:00", days="6")])
    )
    assert result["used_days"] == "2.00000"
    assert result["despatch_days"] == "5.83333"
    assert result["despatch_amount"] == "17500.00"


def test_all_time_saved_assumes_no_future_work_under_actual_time_used():
    cp = {**ACTUAL, "despatch_on": "all_time_saved"}
    result = compute_laytime(
        basis(cp, [port(nor="2026-03-02T08:00", completed="2026-03-04T08:00", days="6")])
    )
    assert result["despatch_days"] == "5.83333"


def test_all_time_saved_ending_inside_a_long_holiday_block():
    """1 h left at Fri 23:30 with Sat + Sun excepted: 30 min Friday, 30 min from Mon 00:00."""
    cp = {"holidays": ["2026-03-07"], "despatch_on": "all_time_saved"}
    result = compute_laytime(
        basis(cp, [port(nor="2026-03-06T00:00", completed="2026-03-06T23:30", days="1.0208333333")])
    )
    # allowed 88200 s (24.5 h), used 23.5 h, 1 h left; expiry Mon 09 00:30 -> 49 h saved.
    assert result["despatch_days"] == "2.04167"


# --- the calendar helper ------------------------------------------------------------------


def test_excepted_intervals_are_merged_and_clipped():
    cp = basis(
        {"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM, "holidays": ["2026-03-09"]}
    )
    intervals = excepted_intervals(
        cp["cp"], datetime(2026, 3, 7, 18, 0), datetime(2026, 3, 16, 0, 0)
    )
    assert intervals == [
        (datetime(2026, 3, 7, 18, 0), datetime(2026, 3, 10, 0, 0)),
        (datetime(2026, 3, 14, 12, 0), datetime(2026, 3, 16, 0, 0)),
    ]


def test_excepted_intervals_are_empty_under_shinc():
    cp = basis({"laytime_basis": "SHINC", "holidays": ["2026-03-09"]})["cp"]
    assert excepted_intervals(cp, datetime(2026, 3, 1), datetime(2026, 3, 31)) == []


# --- the engine never guesses -------------------------------------------------------------


@pytest.mark.parametrize(
    "cp_extra",
    [
        {"laytime_basis": "SHINC", "excepted_periods": SATPM},
        {"laytime_basis": "SATPMSHEX"},
        {"excepted_periods": [{"from": {"weekday": "cmt", "time": "12:00"}, "to": SATPM[0]["to"]}]},
        {"excepted_periods": [{"from": SATPM[0]["from"], "to": SATPM[0]["from"]}]},
        {
            "excepted_periods": [
                {
                    "from": {"weekday": "mon", "time": "00:00"},
                    "to": {"weekday": "fri", "time": "00:00"},
                },
                {
                    "from": {"weekday": "fri", "time": "00:00"},
                    "to": {"weekday": "mon", "time": "00:00"},
                },
            ]
        },
        {"unless_used": True, "unless_used_mode": "half_time"},
        {"unless_used": False, "unless_used_mode": "actual_time_used"},
        {"excepted_periods": "SATPMSHEX"},
        {
            "excepted_periods": [
                {"from": {"weekday": "sat", "time": "12:00:59"}, "to": SATPM[0]["to"]}
            ]
        },
        {"excepted_periods": [{"from": {"weekday": "sat", "time": "24:00"}, "to": SATPM[0]["to"]}]},
        {"holidays": ["20260304"]},
        {"holidays": ["2026-W10-3"]},
        {"laytime_basis": "SHINC", "holidays": ["not-a-date"]},
        {"holidays": [{"date": "2026-03-04", "from": "13:00", "to": "09:00"}]},
        {"holidays": ["2026-3-4"]},
    ],
    ids=[
        "shinc-with-windows",
        "unknown-basis-without-windows",
        "bad-weekday",
        "zero-length-window",
        "windows-cover-the-whole-week",
        "unknown-unless-used-mode",
        "mode-without-unless-used",
        "windows-not-a-list",
        "window-time-with-seconds",
        "window-starting-at-24",
        "holiday-in-basic-iso-format",
        "holiday-in-week-format",
        "malformed-holiday-under-shinc",
        "holiday-ends-before-it-starts",
        "malformed-holiday-date",
    ],
)
def test_contradictory_or_malformed_terms_raise(cp_extra):
    with pytest.raises(ValueError):
        compute_laytime(basis(cp_extra, [port()]))


def test_window_may_end_at_twenty_four_hundred():
    """'Saturday noon to Sunday 24:00' is Saturday 12:00 to Monday 00:00: 36 h of 96 h."""
    window = [
        {"from": {"weekday": "sat", "time": "12:00"}, "to": {"weekday": "sun", "time": "24:00"}}
    ]
    assert used({"excepted_periods": window}) == "2.50000"


@pytest.mark.parametrize(
    "port_kwargs",
    [
        {"nor": "2026-03-02T08:00+03:00"},
        {"completed": "2026-03-10T08:00+03:00"},
        {"allowed": {"kind": "rate", "cargo_qty": "6000", "rate_per_day": "0"}},
        {"allowed": {"kind": "fixed_days", "days": "-1"}},
    ],
    ids=["nor-with-offset", "completion-with-offset", "zero-rate", "negative-allowance"],
)
def test_port_facts_the_engine_cannot_honour_raise(port_kwargs):
    with pytest.raises(ValueError):
        compute_laytime(basis({"laytime_basis": "SHINC"}, [port(**port_kwargs)]))


def test_reversible_basis_without_ports_raises():
    with pytest.raises(ValueError):
        compute_laytime(basis({"reversible": True}, []))


def test_excepted_intervals_reject_an_inverted_range():
    with pytest.raises(ValueError):
        excepted_intervals(basis()["cp"], datetime(2026, 3, 10), datetime(2026, 3, 1))
