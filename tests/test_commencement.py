"""The commencement clause (``cp.commencement``): when laytime starts after NOR.

These are RULE tests, not golden tests. Every expected value was worked out by
hand, in the test's docstring, before the engine was asked; the facts are
synthetic. A golden test needs a real statement of facts from a real user and
a real charter party; none has been seen for this clause yet, so
``test_golden.py`` holds no commencement case.

Counting time: a moment counts when it is not inside an excepted interval of
the charter-party calendar (weekly excepted period, whole or partial holiday,
holiday eve tail, holiday resume extension). Intervals are half open, as in
the ledger: the first moment of an excepted period does not count, the moment
it ends does (time counts from that instant on).

Calendar anchor (2026): Sun 01 Mar, Mon 02, Tue 03, Wed 04, Thu 05, Fri 06,
Sat 07, Sun 08, Mon 09, Tue 10, Wed 11, Thu 12.
"""

import pytest

from laytime import compute_laytime

SATPM = [{"from": {"weekday": "sat", "time": "12:00"}, "to": {"weekday": "mon", "time": "08:00"}}]
NEXT_0800 = {"kind": "next_working_day", "time": "08:00"}
GENCON = {"kind": "gencon", "cutoff": "12:00", "same_day": "13:00", "next_day": "06:00"}
OFFICE = {"from": "08:00", "to": "17:00"}
SATPMSHEX = {"laytime_basis": "SATPMSHEX", "excepted_periods": SATPM}


def basis(cp_extra=None, ports=None):
    cp = {
        "laytime_basis": "SHEX",
        "unless_used": False,
        "reversible": False,
        "demurrage_rate_per_day": "8000",
        "currency": "USD",
        "despatch_fraction": "half",
        "despatch_on": "working_time_saved",
        "holidays": [],
    }
    cp.update(cp_extra or {})
    return {"cp": cp, "ports": ports or []}


def port(nor, completed="2026-03-20T08:00", days="10", name="Novorossiysk", **kwargs):
    data = {
        "name": name,
        "purpose": "loading",
        "nor_tendered": nor,
        "completed_at": completed,
        "allowed": {"kind": "fixed_days", "days": days},
        "interruptions": [],
    }
    data.update(kwargs)
    return data


def row(cp_extra, nor, **port_kwargs):
    return compute_laytime(basis(cp_extra, [port(nor, **port_kwargs)]))["ports"][0]


def start(cp_extra, nor, **port_kwargs):
    return row(cp_extra, nor, **port_kwargs)["laytime_start"]


# --- next working day ---------------------------------------------------------------------


def test_shex_friday_afternoon_nor_starts_saturday_morning():
    """NOR Fri 06 Mar 16:00, SHEX, next working day 08:00.

    SHEX excepts Sunday only, so Saturday 08:00 is counting time: laytime starts Sat 07 08:00.
    To Tue 10 08:00 that is 72 h less Sunday's 24 h = 48 h = 2.00000 days.
    """
    result = row({"commencement": NEXT_0800}, "2026-03-06T16:00", completed="2026-03-10T08:00")
    assert result["laytime_start"] == "2026-03-07T08:00"
    assert result["used_days"] == "2.00000"


def test_satpmshex_friday_afternoon_nor_starts_saturday_morning():
    """NOR Fri 16:00, SATPMSHEX (Sat 12:00 -> Mon 08:00 excepted), next working day 08:00.

    Sat 08:00 is before the window opens at noon, so it counts: start Sat 07 08:00.
    To Tue 10 08:00: Sat 08:00-12:00 (4 h) + Mon 08:00 -> Tue 08:00 (24 h) = 28 h = 1.16667 days.
    """
    cp = {**SATPMSHEX, "commencement": NEXT_0800}
    result = row(cp, "2026-03-06T16:00", completed="2026-03-10T08:00")
    assert result["laytime_start"] == "2026-03-07T08:00"
    assert result["used_days"] == "1.16667"


def test_satpmshex_saturday_nor_starts_exactly_when_the_window_ends():
    """NOR Sat 07 10:00, SATPMSHEX, next working day 08:00.

    Sun 08 08:00 is inside the window. Mon 09 08:00 is the moment the window ends; intervals are
    half open, time counts from that instant, so it IS counting time: start Mon 09 08:00.
    To Tue 10 08:00 that is 24 h = 1.00000 days.
    """
    cp = {**SATPMSHEX, "commencement": NEXT_0800}
    result = row(cp, "2026-03-07T10:00", completed="2026-03-10T08:00")
    assert result["laytime_start"] == "2026-03-09T08:00"
    assert result["used_days"] == "1.00000"


def test_a_window_that_ends_after_the_start_time_pushes_to_the_next_day():
    """Same facts, but the window runs to Mon 09:00: Mon 08:00 is inside it, so Tue 10 08:00."""
    window = [
        {"from": {"weekday": "sat", "time": "12:00"}, "to": {"weekday": "mon", "time": "09:00"}}
    ]
    cp = {"laytime_basis": "SATPMSHEX", "excepted_periods": window, "commencement": NEXT_0800}
    assert start(cp, "2026-03-07T10:00") == "2026-03-10T08:00"


def test_the_first_moment_of_an_excepted_window_is_not_counting_time():
    """Window Sat 08:00 -> Mon 00:00, NOR Fri 16:00, start time 08:00.

    Sat 08:00 is the instant the window opens: nothing counts from it on, so it is not counting
    time. Sun 08:00 is inside. Mon 09 08:00 counts: start Mon 09 08:00.
    """
    window = [
        {"from": {"weekday": "sat", "time": "08:00"}, "to": {"weekday": "mon", "time": "00:00"}}
    ]
    cp = {"laytime_basis": "SSHEX", "excepted_periods": window, "commencement": NEXT_0800}
    assert start(cp, "2026-03-06T16:00") == "2026-03-09T08:00"


def test_next_working_day_is_strictly_after_the_nor_day():
    """NOR Mon 02 Mar 03:00, start time 08:00: not Monday 08:00 but Tue 03 08:00."""
    assert start({"commencement": NEXT_0800}, "2026-03-02T03:00") == "2026-03-03T08:00"


def test_a_holiday_on_the_candidate_day_pushes_one_day_further():
    """NOR Thu 05 16:00, SHEX, Fri 06 a holiday: Fri 08:00 does not count, Sat 07 08:00 does."""
    cp = {"holidays": ["2026-03-06"], "commencement": NEXT_0800}
    assert start(cp, "2026-03-05T16:00") == "2026-03-07T08:00"


def test_a_holiday_resume_time_later_than_the_start_time_pushes_to_the_following_day():
    """NOR Wed 04 16:00, SHEX, Thu 05 a holiday that resumes at 10:00 on Friday.

    Thu 08:00 is the holiday. Fri 06 08:00 is inside the resume extension (until Fri 10:00), so
    it does not count either. The clause names a time of day, not "when counting resumes", so
    the start is not Fri 10:00 but the next day whose 08:00 counts: Sat 07 08:00.
    """
    cp = {"holidays": ["2026-03-05"], "holiday_resume_time": "10:00", "commencement": NEXT_0800}
    assert start(cp, "2026-03-04T16:00") == "2026-03-07T08:00"


def test_a_holiday_eve_tail_is_not_counting_time():
    """NOR Tue 03 16:00, Thu 05 a holiday with its eve excepted from 13:00, start time 14:00.

    Wed 04 14:00 is in the eve tail (Wed 13:00 -> Thu 00:00), Thu 14:00 is the holiday,
    Fri 06 14:00 counts.
    """
    cp = {
        "holidays": ["2026-03-05"],
        "holiday_eve_from": "13:00",
        "commencement": {"kind": "next_working_day", "time": "14:00"},
    }
    assert start(cp, "2026-03-03T16:00") == "2026-03-06T14:00"


def test_a_partial_holiday_only_blocks_its_own_hours():
    """Thu 05 is a holiday from 13:00 only; Thu 08:00 counts, so a Wed NOR starts Thu 05 08:00."""
    cp = {"holidays": [{"date": "2026-03-05", "from": "13:00"}], "commencement": NEXT_0800}
    assert start(cp, "2026-03-04T16:00") == "2026-03-05T08:00"


def test_shinc_counts_every_moment():
    """NOR Sat 07 16:00 under SHINC: Sunday 08:00 counts, holidays are not read: Sun 08 08:00."""
    cp = {"laytime_basis": "SHINC", "holidays": ["2026-03-08"], "commencement": NEXT_0800}
    assert start(cp, "2026-03-07T16:00") == "2026-03-08T08:00"


def test_unless_used_and_interruptions_do_not_move_the_start():
    """NOR Sat 07 10:00 SATPMSHEX unless used, rain Mon 07:00-09:00, work on Sunday.

    Commencement reads the charter-party calendar only: Mon 09 08:00, as without them.
    """
    cp = {
        **SATPMSHEX,
        "unless_used": True,
        "unless_used_mode": "actual_time_used",
        "commencement": NEXT_0800,
    }
    got = start(
        cp,
        "2026-03-07T10:00",
        interruptions=[{"from": "2026-03-09T07:00", "to": "2026-03-09T09:00", "reason": "rain"}],
        worked=[{"from": "2026-03-08T06:00", "to": "2026-03-08T12:00"}],
    )
    assert got == "2026-03-09T08:00"


def test_a_start_after_completion_is_clamped_as_with_nor_to_start_hours():
    """NOR Fri 16:00, cargo completed Fri 20:00, before Sat 08:00: start = completion, 0 used."""
    result = row({"commencement": NEXT_0800}, "2026-03-06T16:00", completed="2026-03-06T20:00")
    assert result["laytime_start"] == "2026-03-06T20:00"
    assert result["used_days"] == "0.00000"


# --- gencon -------------------------------------------------------------------------------


def test_gencon_nor_before_the_cutoff_starts_the_same_afternoon():
    """NOR Mon 02 09:00, cutoff 12:00, same day 13:00: start Mon 02 13:00."""
    assert start({"commencement": GENCON}, "2026-03-02T09:00") == "2026-03-02T13:00"


def test_gencon_nor_exactly_at_the_cutoff_counts_as_before_it():
    """NOR Mon 02 12:00 is "at or before" 12:00: start Mon 02 13:00."""
    assert start({"commencement": GENCON}, "2026-03-02T12:00") == "2026-03-02T13:00"


def test_gencon_nor_after_the_cutoff_starts_next_morning():
    """NOR Mon 02 12:01: start Tue 03 06:00."""
    assert start({"commencement": GENCON}, "2026-03-02T12:01") == "2026-03-03T06:00"


def test_gencon_friday_afternoon_under_shex_starts_saturday():
    """NOR Fri 06 15:00, SHEX: Sat 07 06:00 counts (only Sunday is excepted)."""
    assert start({"commencement": GENCON}, "2026-03-06T15:00") == "2026-03-07T06:00"


def test_gencon_saturday_afternoon_under_shex_skips_sunday():
    """NOR Sat 07 15:00, SHEX: Sun 08 06:00 does not count, Mon 09 06:00 does."""
    assert start({"commencement": GENCON}, "2026-03-07T15:00") == "2026-03-09T06:00"


def test_gencon_same_day_moment_inside_an_excepted_period_falls_to_the_next_day_rule():
    """NOR Sat 07 09:00, SATPMSHEX: before the cutoff, but Sat 13:00 is inside the window.

    So the next-day rule applies: Sun 08 06:00 is inside the window, Mon 09 06:00 is inside it
    too (it runs to 08:00), Tue 10 06:00 counts. The clause names 06:00, so the start is
    Tue 10 06:00 and not Mon 08:00 when the window ends.
    """
    cp = {**SATPMSHEX, "commencement": GENCON}
    assert start(cp, "2026-03-07T09:00") == "2026-03-10T06:00"


def test_gencon_same_day_may_equal_the_cutoff():
    """cutoff 12:00, same day 12:00: a NOR at 12:00 starts laytime at once."""
    clause = {**GENCON, "same_day": "12:00"}
    assert start({"commencement": clause}, "2026-03-02T12:00") == "2026-03-02T12:00"


# --- which NOR ----------------------------------------------------------------------------


def test_nor_accepted_is_the_reference_when_present():
    """Tendered Fri 06 11:00, accepted Fri 12:30: accepted is after the cutoff: Sat 07 06:00."""
    got = start({"commencement": GENCON}, "2026-03-06T11:00", nor_accepted="2026-03-06T12:30")
    assert got == "2026-03-07T06:00"


def test_nor_tendered_is_the_reference_without_an_acceptance():
    """Tendered Fri 06 11:00 and no acceptance recorded: before the cutoff: Fri 06 13:00."""
    assert start({"commencement": GENCON}, "2026-03-06T11:00") == "2026-03-06T13:00"


# --- office hours -------------------------------------------------------------------------


def test_office_hours_move_a_night_nor_to_the_next_opening_then_next_working_day():
    """NOR Mon 02 22:00, office 08:00-17:00, next working day 08:00.

    The NOR is treated as given at Tue 03 08:00; the first day strictly after Tuesday is
    Wed 04: start Wed 04 08:00. Without office hours the same NOR starts Tue 03 08:00.
    """
    clause = {**NEXT_0800, "office_hours": OFFICE}
    assert start({"commencement": clause}, "2026-03-02T22:00") == "2026-03-04T08:00"
    assert start({"commencement": NEXT_0800}, "2026-03-02T22:00") == "2026-03-03T08:00"


def test_office_hours_move_a_night_nor_before_the_gencon_cutoff():
    """NOR Mon 02 22:00, office 08:00-17:00, gencon 12:00 / 13:00 / 06:00.

    Treated as given Tue 03 08:00, which is before the cutoff: start Tue 03 13:00. Without
    office hours the NOR is after Monday's cutoff: Tue 03 06:00.
    """
    clause = {**GENCON, "office_hours": OFFICE}
    assert start({"commencement": clause}, "2026-03-02T22:00") == "2026-03-03T13:00"
    assert start({"commencement": GENCON}, "2026-03-02T22:00") == "2026-03-03T06:00"


def test_a_nor_before_opening_is_given_at_the_same_days_opening():
    """NOR Mon 02 03:00 -> treated as Mon 08:00 -> before the cutoff -> Mon 02 13:00."""
    clause = {**GENCON, "office_hours": OFFICE}
    assert start({"commencement": clause}, "2026-03-02T03:00") == "2026-03-02T13:00"


def test_office_hours_include_both_ends():
    """NOR Mon 08:00 sharp and Mon 17:00 sharp are inside office hours and are not moved.

    08:00 -> before the cutoff -> Mon 02 13:00. 17:00 -> after the cutoff -> Tue 03 06:00.
    One minute later, 17:01, is outside: given Tue 08:00 -> before the cutoff -> Tue 03 13:00.
    """
    cp = {"commencement": {**GENCON, "office_hours": OFFICE}}
    assert start(cp, "2026-03-02T08:00") == "2026-03-02T13:00"
    assert start(cp, "2026-03-02T17:00") == "2026-03-03T06:00"
    assert start(cp, "2026-03-02T17:01") == "2026-03-03T13:00"


def test_a_nor_in_office_hours_but_in_an_excepted_period_waits_for_a_counting_opening():
    """NOR Sat 07 14:00, SATPMSHEX, office 08:00-17:00.

    Sat 14:00 is inside office hours but inside the window. Sun 08:00 opening is inside the
    window; Mon 09 08:00 is the moment it ends and counts: given Mon 09 08:00.
    gencon: before the cutoff, Mon 13:00 counts -> Mon 09 13:00.
    next working day 08:00: strictly after Monday -> Tue 10 08:00.
    """
    assert (
        start({**SATPMSHEX, "commencement": {**GENCON, "office_hours": OFFICE}}, "2026-03-07T14:00")
        == "2026-03-09T13:00"
    )
    assert (
        start(
            {**SATPMSHEX, "commencement": {**NEXT_0800, "office_hours": OFFICE}},
            "2026-03-07T14:00",
        )
        == "2026-03-10T08:00"
    )


def test_a_saturday_night_nor_under_shex_is_given_monday_morning():
    """NOR Sat 07 20:00, SHEX, office 08:00-17:00: Sun opening does not count -> Mon 09 08:00.

    gencon: Mon 09 13:00.
    """
    clause = {**GENCON, "office_hours": OFFICE}
    assert start({"commencement": clause}, "2026-03-07T20:00") == "2026-03-09T13:00"


# --- reversible ---------------------------------------------------------------------------


def two_ports(cp_extra, first_nor="2026-03-06T16:00", second_nor="2026-03-10T10:00"):
    ports = [
        port(first_nor, completed="2026-03-09T08:00", days="2", name="Novorossiysk"),
        port(second_nor, completed="2026-03-12T08:00", days="2", name="Iskenderun"),
    ]
    return basis({"reversible": True, "commencement": NEXT_0800, **cp_extra}, ports)


def test_reversible_applies_the_clause_at_each_port():
    """SHEX, reversible, 2 + 2 days, next working day 08:00.

    Loading: NOR Fri 06 16:00 -> Sat 07 08:00; to Mon 09 08:00 is 48 h less Sunday = 24 h.
    Discharge: NOR Tue 10 10:00 -> Wed 11 08:00; to Thu 12 08:00 = 24 h.
    Used 48 h = 2.00000 of 4 days; 2 days saved at half of 8000 = 8000.00 despatch.
    """
    result = compute_laytime(two_ports({}))
    assert [p["laytime_start"] for p in result["ports"]] == ["2026-03-07T08:00", "2026-03-11T08:00"]
    assert result["used_days"] == "2.00000"
    assert result["despatch_days"] == "2.00000"
    assert result["despatch_amount"] == "8000.00"
    assert result["net_amount"] == "-8000.00"


def test_reversible_order_check_works_on_the_commenced_starts():
    """The second port's NOR (Thu 05) commences Fri 06 08:00, before the first port's Sat 07."""
    with pytest.raises(ValueError, match="list the ports in voyage order"):
        compute_laytime(two_ports({}, second_nor="2026-03-05T10:00"))


# --- results stay the same shape ----------------------------------------------------------


def test_no_new_result_keys():
    with_clause = compute_laytime(basis({"commencement": GENCON}, [port("2026-03-02T09:00")]))
    without = compute_laytime(basis({"nor_to_start_hours": 4}, [port("2026-03-02T09:00")]))
    assert with_clause == without
    assert with_clause["ports"][0]["laytime_start"] == "2026-03-02T13:00"


def test_a_null_clause_and_zero_hours_are_the_absent_clause():
    plain = compute_laytime(basis(None, [port("2026-03-02T09:00")]))
    assert compute_laytime(basis({"commencement": None}, [port("2026-03-02T09:00")])) == plain
    zero = {"commencement": NEXT_0800, "nor_to_start_hours": 0}
    assert start(zero, "2026-03-02T09:00") == "2026-03-03T08:00"


# --- refusals -----------------------------------------------------------------------------


def refuses(cp_extra, message, nor="2026-03-02T09:00"):
    with pytest.raises(ValueError, match=message) as info:
        compute_laytime(basis(cp_extra, [port(nor)]))
    assert "\n" not in str(info.value)


def test_refuses_the_clause_together_with_nor_to_start_hours():
    refuses(
        {"commencement": NEXT_0800, "nor_to_start_hours": 12},
        "cp.commencement and cp.nor_to_start_hours",
    )


def test_refuses_an_unknown_kind():
    refuses({"commencement": {"kind": "wibon", "time": "08:00"}}, "kind must be one of")


def test_refuses_a_clause_that_is_not_a_mapping():
    refuses({"commencement": "gencon"}, "cp.commencement is a mapping")


@pytest.mark.parametrize(
    ("clause", "message"),
    [
        ({"time": "08:00"}, "is missing 'kind'"),
        ({"kind": "next_working_day"}, "is missing 'time'"),
        ({"kind": "gencon", "cutoff": "12:00", "same_day": "13:00"}, "is missing 'next_day'"),
        ({"kind": "gencon", "time": "08:00"}, "is missing 'cutoff', 'next_day', 'same_day'"),
    ],
)
def test_refuses_missing_keys(clause, message):
    refuses({"commencement": clause}, message)


@pytest.mark.parametrize(
    ("clause", "message"),
    [
        ({**NEXT_0800, "cutoff": "12:00"}, "does not take 'cutoff'"),
        ({**GENCON, "time": "08:00"}, "does not take 'time'"),
        ({**GENCON, "unless_sooner_commenced": True}, "does not take 'unless_sooner_commenced'"),
    ],
)
def test_refuses_extra_keys(clause, message):
    refuses({"commencement": clause}, message)


@pytest.mark.parametrize("value", ["8:00", "24:00", "08.00", "0800", "25:00", "08:60", 800, None])
def test_refuses_a_malformed_time_of_day(value):
    refuses({"commencement": {"kind": "next_working_day", "time": value}}, "time is written HH:MM")


def test_refuses_a_malformed_gencon_hour_naming_the_field():
    refuses({"commencement": {**GENCON, "next_day": "6am"}}, "next_day is written HH:MM")


def test_refuses_same_day_earlier_than_the_cutoff():
    refuses({"commencement": {**GENCON, "same_day": "11:00"}}, "same_day .11:00. is earlier than")


@pytest.mark.parametrize(
    "hours", [{"from": "17:00", "to": "08:00"}, {"from": "08:00", "to": "08:00"}]
)
def test_refuses_office_hours_that_do_not_run_forward(hours):
    refuses({"commencement": {**NEXT_0800, "office_hours": hours}}, "must be earlier than")


@pytest.mark.parametrize(
    ("hours", "message"),
    [
        ({"from": "08:00"}, "office_hours is missing 'to'"),
        ({"from": "08:00", "to": "17:00", "days": "mon-fri"}, "office_hours does not take 'days'"),
        ("08:00-17:00", "office_hours is a mapping"),
        ({"from": "08:00", "to": "17h"}, "office_hours.to is written HH:MM"),
    ],
)
def test_refuses_malformed_office_hours(hours, message):
    refuses({"commencement": {**NEXT_0800, "office_hours": hours}}, message)


def test_refuses_a_timestamp_with_an_offset():
    refuses({"commencement": NEXT_0800}, "carry no offset", nor="2026-03-02T09:00+03:00")


EVERY_MORNING = [
    {"from": {"weekday": day, "time": "07:00"}, "to": {"weekday": day, "time": "09:00"}}
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
]


def test_refuses_rather_than_loops_when_the_start_time_never_counts():
    """07:00-09:00 is excepted every day, so 08:00 never counts: raise after 60 days."""
    cp = {"laytime_basis": "CUSTOM", "excepted_periods": EVERY_MORNING, "commencement": NEXT_0800}
    refuses(cp, "no counting time at 08:00 within 60 days")


def test_refuses_rather_than_loops_when_the_office_never_opens_in_counting_time():
    cp = {
        "laytime_basis": "CUSTOM",
        "excepted_periods": EVERY_MORNING,
        "commencement": {"kind": "next_working_day", "time": "10:00", "office_hours": OFFICE},
    }
    refuses(cp, "no counting time at 08:00 within 60 days", nor="2026-03-02T22:00")


def test_the_validation_runs_without_ports():
    """A basis with no ports still refuses a malformed clause."""
    with pytest.raises(ValueError, match="kind must be one of"):
        compute_laytime(basis({"commencement": {"kind": "wibon"}}))
