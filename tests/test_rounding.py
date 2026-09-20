"""The rounding rule, pinned.

Time is kept in whole seconds; money is rounded half-up to 0.01 once per
settlement. A reversible voyage is one settlement. Without ``reversible`` each
port is its own settlement, and the voyage totals are exact sums of the
rounded per-port amounts. They are therefore not "total days times the rate":
with n ports the two figures can be up to n // 2 cents apart. That gap is the
rule, not an error, and a stored basis must keep reproducing it; the expected
values below were worked out by hand and are never updated to make a test
pass.

Arithmetic used below (86400 seconds in a day):

- 10000 a day:  60 s ->  6.9444.. ->  6.94     120 s -> 13.8888.. -> 13.89
- 8000 a day:  180 s -> 16.6666.. -> 16.67     (demurrage)
- 4000 a day:  180 s ->  8.3333.. ->  8.33     360 s -> 16.6666.. -> 16.67
  (half despatch on an 8000 rate)
"""

from decimal import ROUND_HALF_UP, Decimal
from itertools import product

from laytime import compute_laytime


def basis(ports, **cp_extra):
    cp = {"laytime_basis": "SHINC", "demurrage_rate_per_day": "10000"}
    cp.update(cp_extra)
    return {"cp": cp, "ports": ports}


def port(name, nor, completed, days="1"):
    return {
        "name": name,
        "nor_tendered": nor,
        "completed_at": completed,
        "allowed": {"kind": "fixed_days", "days": days},
    }


def one_minute_over_at_each_port():
    return [
        port("Samsun", "2026-03-02T00:00", "2026-03-03T00:01"),
        port("Iskenderun", "2026-03-09T00:00", "2026-03-10T00:01"),
    ]


def cents(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), ROUND_HALF_UP)


def test_golden_per_port_laytime_rounds_money_at_each_port_and_adds():
    """One day allowed and one minute over at each of two ports, 10000 a day. Each port owes
    60 s = 6.9444.. -> 6.94, and the voyage owes 6.94 + 6.94 = 13.88."""
    ports = one_minute_over_at_each_port()
    result = compute_laytime(basis(ports))
    assert result["demurrage_amount"] == "13.88"
    assert result["net_amount"] == "13.88"

    alone = [compute_laytime(basis([p]))["demurrage_amount"] for p in ports]
    assert alone == ["6.94", "6.94"]
    assert sum(map(Decimal, alone)) == Decimal(result["demurrage_amount"])


def test_total_time_times_rate_is_a_different_figure_and_is_not_the_result():
    """The same two minutes priced in one go are 120 s = 13.8888.. -> 13.89, one cent more than
    the result. The engine produces 13.89 only where the voyage really is one settlement:
    under reversible laytime."""
    ports = one_minute_over_at_each_port()
    in_one_go = cents(Decimal(120) * Decimal("10000") / Decimal(86400))
    assert in_one_go == Decimal("13.89")
    assert compute_laytime(basis(ports))["demurrage_amount"] == "13.88"
    assert compute_laytime(basis(ports, reversible=True))["demurrage_amount"] == "13.89"


def test_day_figures_are_rounded_each_from_its_own_seconds():
    """60 s = 0.000694.. -> 0.00069 at each port, 120 s = 0.001388.. -> 0.00139 for the voyage:
    the per-port days do not add up to the total in the fifth decimal, and neither day figure
    times the rate gives the amount. Day figures are for display; money comes from seconds."""
    result = compute_laytime(basis(one_minute_over_at_each_port()))
    assert [p["demurrage_days"] for p in result["ports"]] == ["0.00069", "0.00069"]
    assert result["demurrage_days"] == "0.00139"
    assert cents(Decimal(result["demurrage_days"]) * Decimal("10000")) == Decimal("13.90")
    assert result["demurrage_amount"] == "13.88"


def test_golden_per_port_despatch_is_rounded_at_each_port_too():
    """Three minutes saved at each port, half despatch on 8000 = 4000 a day: 180 s = 8.3333..
    -> 8.33 a port, 16.66 for the voyage. 360 s in one go would be 16.6666.. -> 16.67."""
    ports = [
        port("Samsun", "2026-03-02T00:00", "2026-03-02T23:57"),
        port("Iskenderun", "2026-03-09T00:00", "2026-03-09T23:57"),
    ]
    result = compute_laytime(basis(ports, demurrage_rate_per_day="8000"))
    assert result["despatch_days"] == "0.00417"
    assert result["despatch_amount"] == "16.66"
    assert result["net_amount"] == "-16.66"


def test_golden_net_is_the_difference_of_the_per_port_amounts():
    """Three minutes over at the load port (180 s at 8000 = 16.6666.. -> 16.67), three minutes
    saved at discharge (180 s at 4000 -> 8.33): net 16.67 - 8.33 = 8.34 due to Owners."""
    ports = [
        port("Samsun", "2026-03-02T00:00", "2026-03-03T00:03"),
        port("Iskenderun", "2026-03-09T00:00", "2026-03-09T23:57"),
    ]
    result = compute_laytime(basis(ports, demurrage_rate_per_day="8000"))
    assert result["demurrage_amount"] == "16.67"
    assert result["despatch_amount"] == "8.33"
    assert result["net_amount"] == "8.34"


def test_totals_are_exact_sums_of_single_port_results_and_stay_within_the_bound():
    """Without reversible a port's share is what the engine gives for that port alone, so the
    per-port money can always be shown next to a total it adds up to. Against total time times
    the rate the gap never exceeds n // 2 cents."""
    rate = Decimal("10000")
    widest = {2: Decimal(0), 3: Decimal(0), 4: Decimal(0)}
    for n in widest:
        for minutes in product((1, 4, 7, 10, 13), repeat=n):
            ports = [
                port(f"P{i}", f"2026-03-{day:02d}T00:00", f"2026-03-{day + 1:02d}T00:{over:02d}")
                for i, (day, over) in enumerate(zip((2, 5, 8, 11), minutes, strict=False))
            ]
            total = Decimal(compute_laytime(basis(ports))["demurrage_amount"])
            alone = sum(Decimal(compute_laytime(basis([p]))["demurrage_amount"]) for p in ports)
            assert total == alone

            in_one_go = cents(Decimal(60 * sum(minutes)) * rate / Decimal(86400))
            widest[n] = max(widest[n], abs(total - in_one_go))
    assert widest == {2: Decimal("0.01"), 3: Decimal("0.01"), 4: Decimal("0.02")}


def test_single_port_and_reversible_results_carry_no_gap():
    """One settlement, one rounding: the amount is total time times the rate, to the cent."""
    rate = Decimal("10000")
    for minutes in (1, 4, 7, 10, 13):
        single = [port("Samsun", "2026-03-02T00:00", f"2026-03-03T00:{minutes:02d}")]
        expected = str(cents(Decimal(60 * minutes) * rate / Decimal(86400)))
        assert compute_laytime(basis(single))["demurrage_amount"] == expected
        assert compute_laytime(basis(single, reversible=True))["demurrage_amount"] == expected
