# Changelog

## 0.3.0 — 2026-09-21

- `cp.commencement`, optional: when laytime starts after the NOR, as a clause
  instead of a fixed number of hours.
  `{"kind": "next_working_day", "time"}` starts at `time` on the first day
  strictly after the NOR day on which that moment is counting time.
  `{"kind": "gencon", "cutoff", "same_day", "next_day"}` is the GENCON 1976
  cl. 6(c) shape: NOR at or before `cutoff` starts at `same_day` that day if
  that moment counts, otherwise at `next_day` on the first later day on which
  it counts. The hours come from the charter party; the engine has no
  defaults. Optional `office_hours: {"from", "to"}` on either kind: a NOR
  outside them, or at a moment that does not count, is treated as given at the
  next office opening that counts, then the kind's rule applies.
- **Counting time is the existing calendar**, the one `excepted_intervals`
  returns: weekly excepted periods, whole and partial holidays, eve tails and
  resume extensions. Half open, as in the ledger: the moment a period ends is
  counting time, the moment it starts is not. Every moment counts under
  `SHINC`. Interruptions and *unless used* do not move the start.
- The reference NOR is unchanged (`nor_accepted`, else `nor_tendered`), the
  start is still `ports[].laytime_start`, and **no result key is added**.
  Reversible calculations apply the clause per port and check voyage order on
  the resulting starts.
- Refusals, all `ValueError`: the clause together with a non-zero
  `nor_to_start_hours`, an unknown kind, missing or extra keys, a malformed
  `HH:MM`, `same_day` earlier than `cutoff`, `office_hours.from` not earlier
  than `to`, and no counting moment within 60 days.
- **No result changes for a basis without `cp.commencement`**: it takes the
  code path it took before. 40,000 generated bases (0.1.0-shaped and with the
  0.2.0 keys) give the 0.2.0 result, errors included.
- The tests for the clause are rule tests with the hand calculation in each
  docstring, on synthetic facts. There is no golden test for it yet: a golden
  test needs a real statement of facts.
- Known limits, not implemented: NOR validity, "unless sooner commenced",
  "when counting resumes" starts, office hours per weekday, WIBON and its
  relatives. See README *Commencement*.

## 0.2.1 — 2026-09-20

Documentation and tests only. No result changes: 40,000 generated bases
(0.1.0-shaped and with the 0.2.0 keys, 22,572 of them multi-port and
non-reversible) give the 0.2.0 result, errors included.

- The rounding rule is written down (README *Rounding*, engine docstrings) and
  pinned by `tests/test_rounding.py`. Money is rounded half-up once per
  settlement: per voyage under `reversible`, per port otherwise, and the
  voyage totals are exact sums of the rounded per-port amounts. In a
  multi-port non-reversible result the totals can therefore differ by up to
  n // 2 cents from the rate applied to the total time. That is the rule, not
  an error: each port is its own account. It has been so since 0.1.0, stored
  bases reproduce it, and it does not change.
- Day figures are display values, each rounded to five decimals from its own
  seconds; no amount is derived from them, and a day figure times the rate is
  not expected to match an amount to the cent.

## 0.2.0 — 2026-09-20

- `cp.excepted_periods`: weekly excepted windows as weekday + time, so
  SATPMSHEX, FHEX, Thursday-afternoon-and-Friday and whole-weekend clauses are
  expressible with the hours the charter party states. Until now the only
  weekly excepted day was Sunday.
- `cp.holidays` accepts part of a day (`{"date", "from", "to"}`);
  `cp.holiday_eve_from` and `cp.holiday_resume_time` cover "from 17:00 on the
  day before a holiday" and "until 08:00 on the next day".
- `cp.unless_used_mode = "actual_time_used"` with `port.worked`: only the work
  actually done inside an excepted period counts.
- `excepted_intervals(cp, lo, hi)`: the calendar the engine applies, for
  statements that list the excepted periods.
- All-time-saved despatch projects across the same calendar.
- **Fix:** a reversible basis whose ports were not listed in voyage order gave
  a different result for the same facts (the pooled allowance is consumed in
  list order, and all-time-saved despatch is projected from the last port in
  the list). The engine now raises instead of taking the list as written; it
  does not sort, because the order is part of the evidence.
- A weekly window may end at `24:00` ("Saturday noon to Sunday 24:00").
- Stricter input, all `ValueError`. Contradictory terms: `SHINC` with excepted
  periods, a regime other than `SHEX`/`WWD` without them, windows that cover
  the whole week, `unless_used_mode` without `unless_used`, an unknown mode.
  Facts the engine cannot honour: a timestamp with a UTC offset, a rate of
  zero or less, a negative allowance, a reversible basis without ports.
  Malformed values: a holiday that is not `YYYY-MM-DD` (checked under `SHINC`
  too), a time of day that is not `HH:MM`.
- **Compatibility, precisely.** A well-formed 0.1.0 basis gives the 0.1.0
  result (checked against 0.1.0 on 20,000 generated bases). Four shapes that
  0.1.0 computed now raise instead: a reversible basis with its ports out of
  voyage order (see the fix above), a regime name other than the three it knew
  (it silently counted every hour), a holiday string not in `YYYY-MM-DD` (it
  silently ignored it; `20260304` would otherwise have started to count as a
  holiday), and offset-bearing timestamps (they worked only when no Sunday or
  holiday fell inside the port stay).

## 0.1.0 — 2026-09-03

First public release. Extracted unchanged from the laytime engine that has run
inside [MarOps](https://zdeck.tech/case-study-marops.html) since Phase 0.

- `compute_laytime(basis)`: SHINC / SHEX / WWD, `unless used`, holidays,
  NOR-to-start offset, fixed days or cargo ÷ rate allowance, explicit
  interruption records, once-on-demurrage with charter-party override,
  half or full despatch on working time saved or all time saved,
  reversible or per-port laytime.
- `laytime` command line: JSON basis in, JSON result out.
- Golden test suite with hand-verified expected values.
