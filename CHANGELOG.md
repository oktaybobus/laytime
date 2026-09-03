# Changelog

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
