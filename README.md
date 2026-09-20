# laytime

GENCON-style laytime, demurrage and despatch calculator for dry-bulk voyage
charters. One pure function, no dependencies, no floats.

```python
from laytime import compute_laytime

result = compute_laytime(basis)
result["net_amount"]  # "8000.00"  (positive: demurrage due; negative: despatch due)
```

The engine was extracted unchanged from [MarOps](https://zdeck.tech/case-study-marops.html),
a back-office system for small shipowners, where it has produced every laytime
statement since the first release. It is published so that the calculation can
be read, checked and re-run by anyone who receives one of those statements.

## Install

```bash
pip install laytime
```

Python 3.12 or newer. No runtime dependencies.

## Command line

```bash
laytime basis.json            # pretty JSON result
laytime basis.json --compact  # one line
cat basis.json | laytime -    # from stdin
```

Exit code 1 and a message naming the missing field or the contradictory term
when the basis is incomplete; the engine never guesses a value.

## The basis

Everything the calculation needs is in one JSON document. Store it next to the
result: replaying the same basis gives the same result, which is what you want
when the claim is disputed months later.

```json
{
  "cp": {
    "laytime_basis": "SHINC",
    "unless_used": false,
    "reversible": false,
    "nor_to_start_hours": 12,
    "holidays": [],
    "demurrage_rate_per_day": "8000",
    "currency": "USD",
    "despatch_fraction": "half",
    "despatch_on": "working_time_saved",
    "interruptions_count_on_demurrage": false
  },
  "ports": [
    {
      "name": "Samsun",
      "purpose": "loading",
      "nor_tendered": "2026-03-01T06:00",
      "nor_accepted": "2026-03-01T06:00",
      "completed_at": "2026-03-06T06:00",
      "allowed": {"kind": "rate", "cargo_qty": "6000", "rate_per_day": "2000"},
      "interruptions": [
        {"from": "2026-03-02T06:00", "to": "2026-03-02T18:00", "reason": "rain"}
      ]
    }
  ]
}
```

### `cp` — charter-party terms

| Field | Values | Meaning |
|---|---|---|
| `laytime_basis` | `SHINC`, `SHEX`, `WWD`, or any label with `excepted_periods` | `SHINC` counts every hour. Every other regime skips its excepted periods and `holidays`. `SHEX` and `WWD` without `excepted_periods` mean the whole of Sunday. Weather stoppages are explicit interruptions, so `WWD` behaves like `SHEX` inside the engine. |
| `excepted_periods` | list of `{"from": {"weekday", "time"}, "to": {"weekday", "time"}}` | Weekly windows that do not count, written out from the charter party. Weekdays are `mon`…`sun`; a window may run over the end of the week. The engine never derives hours from the regime name: `SATPMSHEX` without this list is an error. |
| `unless_used` | bool | Work inside an excepted period counts. |
| `unless_used_mode` | `whole_period`, `actual_time_used` | `actual_time_used`: only the port's `worked` intervals count inside excepted periods. `whole_period` (default, the 0.1.0 behaviour): excepted periods count in full and idle time is deducted through interruptions. |
| `reversible` | bool | Pool the allowance of all ports into one ledger (time saved at loading carries to discharge) instead of settling each port on its own. |
| `nor_to_start_hours` | int | Hours between NOR acceptance and the start of laytime. |
| `holidays` | list of `YYYY-MM-DD` or `{"date", "from", "to"}` | A string is a whole local-calendar day. A mapping excepts part of one: `{"date": "2026-10-28", "from": "13:00"}` is a half-day holiday, `{"date": …, "to": "08:00"}` a morning. |
| `holiday_eve_from` | `HH:MM` | The day before each whole-day holiday does not count from this hour on. Partial holidays have no eve. |
| `holiday_resume_time` | `HH:MM` | Each holiday that runs to the end of its day stretches to this hour on the following day. If that day is excepted too the periods merge and its own rule applies. |
| `demurrage_rate_per_day` | decimal string | Per day, pro rata. |
| `currency` | string | Echoed into the result. |
| `despatch_fraction` | `half`, `full` | Half despatch is the dry-bulk default. |
| `despatch_on` | `working_time_saved`, `all_time_saved` | Under an excepting regime, all-time-saved projects the unused allowance across the calendar, excepted periods included. No future work is assumed inside them. |
| `interruptions_count_on_demurrage` | bool | Default `false`: *once on demurrage, always on demurrage*. Set `true` only when the charter party says interruptions are deducted after demurrage starts. |

### `ports[]`

| Field | Meaning |
|---|---|
| `name`, `purpose` | Free text; `purpose` is echoed, not interpreted. |
| `nor_tendered`, `nor_accepted` | Port-local naive ISO 8601. `nor_accepted` wins when both are present. |
| `completed_at` | End of cargo operations. |
| `allowed` | `{"kind": "fixed_days", "days": "2"}` or `{"kind": "rate", "cargo_qty": "6000", "rate_per_day": "2000"}`. |
| `interruptions[]` | Explicit `from`/`to`/`reason` records: rain, shifting, breakdown, waiting. There is no "deduct N hours" shortcut; every deduction has a start and an end. |
| `worked[]` | `from`/`to` records of work done inside excepted periods. Read only under `unless_used_mode: actual_time_used`; interruptions inside them are still deducted. |

All timestamps are **port local time**, naive. Excepted periods and holidays
are applied on the local calendar. Convert from UTC before building the
basis; the engine does not know about time zones on purpose.

## The result

```json
{
  "reversible": false,
  "laytime_basis": "SHINC",
  "allowed_days": "3.00000",
  "used_days": "3.00000",
  "demurrage_days": "1.00000",
  "despatch_days": "0.00000",
  "demurrage_amount": "8000.00",
  "despatch_amount": "0.00",
  "net_amount": "8000.00",
  "currency": "USD",
  "ports": [
    {
      "name": "Samsun",
      "laytime_start": "2026-03-01T18:00",
      "completed_at": "2026-03-06T06:00",
      "used_days": "3.00000",
      "demurrage_start": "2026-03-05T06:00",
      "demurrage_days": "1.00000",
      "allowed_days": "3.00000",
      "despatch_days": "0.00000"
    }
  ]
}
```

Days are strings with five decimals, money is a string with two decimals,
both rounded half-up from exact `Decimal` arithmetic on whole seconds. Nothing
in the result is a float. Under `reversible: true` the per-port rows omit
`allowed_days` and `despatch_days` because those only exist for the pool.

## Rules the engine commits to

- **Once on demurrage, always on demurrage.** After the allowance is
  exhausted nothing is deducted, unless `interruptions_count_on_demurrage`
  says the charter party carves out an exception.
- **Deductions are records, not numbers.** Every interruption has a start and
  an end. Overlapping interruptions and excepted days are merged before
  counting, so a rain stoppage on a Sunday is not deducted twice.
- **Half despatch by default**, on working time saved by default.
- **No time zones.** The basis is port-local; the caller converts.
- **No guessing.** A missing field raises `KeyError` rather than defaulting;
  contradictory or malformed terms raise `ValueError`.

## Golden tests

`tests/test_golden.py` pins every rule to a hand-verified example. The policy
is simple: a golden test is never fixed by updating the expected value. If a
change to the engine makes one fail, the engine is wrong or the rule has
changed, and the second case needs a new test with its own hand-verified
number.

## Scope

GENCON-type voyage charters only. Time charter, hire and off-hire are out of
scope, as are SOF parsing, PDF statements and charter-party text
interpretation; those live in the applications that use this package.

## License

MIT.
