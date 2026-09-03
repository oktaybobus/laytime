"""Golden laytime tests.

Every expected value was verified by hand against the charter-party rule it
exercises. If the engine changes and one of these fails, the engine is wrong;
these tests are never "fixed" by updating the expected value.

Calendar anchor: 2026-03-01 is a Sunday; 02 Mon, 08 Sun, 09 Mon.
"""

import pytest

from laytime import compute_laytime


def basis(cp_extra=None, ports=None):
    cp = {
        "laytime_basis": "SHINC",
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


def port(name="Samsun", nor="2026-03-02T08:00", completed="2026-03-04T08:00", **kwargs):
    data = {
        "name": name,
        "purpose": "loading",
        "nor_tendered": nor,
        "nor_accepted": nor,
        "completed_at": completed,
        "allowed": {"kind": "fixed_days", "days": "2"},
        "interruptions": [],
    }
    data.update(kwargs)
    return data


def test_golden_demurrage_shinc_with_interruption():
    """6000 mt at 2000 mt/day = 3 days allowed; a 12 h rain stoppage shifts the count."""
    result = compute_laytime(
        basis(
            {"nor_to_start_hours": 12},
            [
                port(
                    nor="2026-03-01T06:00",
                    completed="2026-03-06T06:00",
                    allowed={"kind": "rate", "cargo_qty": "6000", "rate_per_day": "2000"},
                    interruptions=[
                        {"from": "2026-03-02T06:00", "to": "2026-03-02T18:00", "reason": "rain"}
                    ],
                )
            ],
        )
    )
    assert result["allowed_days"] == "3.00000"
    assert result["used_days"] == "3.00000"
    assert result["ports"][0]["laytime_start"] == "2026-03-01T18:00"
    assert result["ports"][0]["demurrage_start"] == "2026-03-05T06:00"
    assert result["demurrage_days"] == "1.00000"
    assert result["demurrage_amount"] == "8000.00"
    assert result["despatch_amount"] == "0.00"
    assert result["net_amount"] == "8000.00"


def test_golden_despatch_shex_half():
    """6 days allowed, done in 2; WTS saves 4 days, ATS skips the Sunday and saves 5."""
    common_port = port(completed="2026-03-04T08:00", allowed={"kind": "fixed_days", "days": "6"})

    wts = compute_laytime(
        basis({"laytime_basis": "SHEX", "demurrage_rate_per_day": "6000"}, [common_port])
    )
    assert wts["used_days"] == "2.00000"
    assert wts["despatch_days"] == "4.00000"
    assert wts["despatch_amount"] == "12000.00"
    assert wts["demurrage_amount"] == "0.00"
    assert wts["net_amount"] == "-12000.00"

    ats = compute_laytime(
        basis(
            {
                "laytime_basis": "SHEX",
                "demurrage_rate_per_day": "6000",
                "despatch_on": "all_time_saved",
            },
            [common_port],
        )
    )
    assert ats["despatch_days"] == "5.00000"
    assert ats["despatch_amount"] == "15000.00"


def test_golden_once_on_demurrage():
    """After demurrage starts neither rain nor Sunday is deducted."""
    rain_after = {"from": "2026-03-04T10:00", "to": "2026-03-04T16:00", "reason": "rain"}
    result = compute_laytime(
        basis(
            {"laytime_basis": "SHEX"},
            [
                port(
                    completed="2026-03-09T08:00",
                    allowed={"kind": "fixed_days", "days": "1"},
                    interruptions=[rain_after],
                )
            ],
        )
    )
    assert result["ports"][0]["demurrage_start"] == "2026-03-03T08:00"
    assert result["demurrage_days"] == "6.00000"
    assert result["demurrage_amount"] == "48000.00"


def test_same_rain_before_demurrage_does_reduce():
    result = compute_laytime(
        basis(
            {"laytime_basis": "SHEX"},
            [
                port(
                    completed="2026-03-09T08:00",
                    allowed={"kind": "fixed_days", "days": "1"},
                    interruptions=[
                        {"from": "2026-03-02T10:00", "to": "2026-03-02T16:00", "reason": "rain"}
                    ],
                )
            ],
        )
    )
    assert result["ports"][0]["demurrage_start"] == "2026-03-03T14:00"
    assert result["demurrage_days"] == "5.75000"
    assert result["demurrage_amount"] == "46000.00"


def test_cp_exception_lets_interruptions_count_on_demurrage():
    result = compute_laytime(
        basis(
            {"laytime_basis": "SHEX", "interruptions_count_on_demurrage": True},
            [
                port(
                    completed="2026-03-09T08:00",
                    allowed={"kind": "fixed_days", "days": "1"},
                    interruptions=[
                        {"from": "2026-03-04T10:00", "to": "2026-03-04T16:00", "reason": "rain"}
                    ],
                )
            ],
        )
    )
    assert result["demurrage_days"] == "5.75000"


def test_shex_excludes_sunday_before_demurrage():
    result = compute_laytime(
        basis(
            {"laytime_basis": "SHEX"},
            [port(nor="2026-03-06T08:00", completed="2026-03-10T08:00")],
        )
    )
    assert result["ports"][0]["demurrage_start"] == "2026-03-09T08:00"
    assert result["used_days"] == "2.00000"
    assert result["demurrage_days"] == "1.00000"


def test_unless_used_counts_sunday():
    result = compute_laytime(
        basis(
            {"laytime_basis": "SHEX", "unless_used": True},
            [port(nor="2026-03-06T08:00", completed="2026-03-09T08:00")],
        )
    )
    assert result["ports"][0]["demurrage_start"] == "2026-03-08T08:00"
    assert result["demurrage_days"] == "1.00000"


def test_holiday_is_excepted_like_sunday():
    """A listed holiday (Tuesday 2026-03-03) is skipped under SHEX."""
    result = compute_laytime(
        basis(
            {"laytime_basis": "SHEX", "holidays": ["2026-03-03"]},
            [port(nor="2026-03-02T08:00", completed="2026-03-05T08:00")],
        )
    )
    assert result["ports"][0]["demurrage_start"] == "2026-03-05T08:00"
    assert result["used_days"] == "2.00000"
    assert result["demurrage_days"] == "0.00000"


def test_reversible_combines_ports():
    """Time saved at the load port carries over to discharge under reversible laytime."""
    ports = [
        port(name="Samsun", nor="2026-03-02T08:00", completed="2026-03-03T08:00"),
        port(
            name="İskenderun",
            purpose="discharging",
            nor="2026-03-05T08:00",
            nor_accepted="2026-03-05T08:00",
            nor_tendered="2026-03-05T08:00",
            completed="2026-03-08T20:00",
        ),
    ]
    result = compute_laytime(basis({"reversible": True}, ports))
    assert result["allowed_days"] == "4.00000"
    assert result["ports"][1]["demurrage_start"] == "2026-03-08T08:00"
    assert result["demurrage_days"] == "0.50000"
    assert result["demurrage_amount"] == "4000.00"

    split = compute_laytime(basis({"reversible": False}, ports))
    assert split["demurrage_days"] == "1.50000"
    assert split["despatch_days"] == "1.00000"


def test_result_is_reproducible():
    payload = basis(
        {"laytime_basis": "SHEX", "nor_to_start_hours": 12},
        [
            port(
                nor="2026-03-01T06:00",
                completed="2026-03-06T06:00",
                allowed={"kind": "rate", "cargo_qty": "6000", "rate_per_day": "2000"},
                interruptions=[
                    {"from": "2026-03-02T06:00", "to": "2026-03-02T18:00", "reason": "rain"}
                ],
            )
        ],
    )
    assert compute_laytime(payload) == compute_laytime(payload)


def test_result_is_json_serialisable_without_floats():
    import json

    result = compute_laytime(basis(None, [port()]))
    text = json.dumps(result)
    assert '"demurrage_amount": "0.00"' in text
    assert "float" not in {type(v).__name__ for v in result.values()}


def test_invalid_allowed_kind_raises():
    with pytest.raises(KeyError):
        compute_laytime(basis(None, [port(allowed={"kind": "rate"})]))
