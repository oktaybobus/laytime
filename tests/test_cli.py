import json

import pytest

from laytime.cli import main

BASIS = {
    "cp": {
        "laytime_basis": "SHEX",
        "demurrage_rate_per_day": "6000",
        "currency": "USD",
        "despatch_fraction": "half",
        "despatch_on": "working_time_saved",
        "nor_to_start_hours": 0,
        "holidays": [],
    },
    "ports": [
        {
            "name": "Samsun",
            "purpose": "loading",
            "nor_tendered": "2026-03-02T08:00",
            "nor_accepted": "2026-03-02T08:00",
            "completed_at": "2026-03-04T08:00",
            "allowed": {"kind": "fixed_days", "days": "6"},
            "interruptions": [],
        }
    ],
}


def test_cli_reads_file_and_prints_result(tmp_path, capsys):
    path = tmp_path / "basis.json"
    path.write_text(json.dumps(BASIS), encoding="utf-8")

    assert main([str(path), "--compact"]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["despatch_amount"] == "12000.00"
    assert out["net_amount"] == "-12000.00"


def test_cli_reads_stdin(monkeypatch, capsys):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(BASIS)))
    assert main(["-"]) == 0
    assert '"despatch_days": "4.00000"' in capsys.readouterr().out


def test_cli_reports_missing_field(tmp_path, capsys):
    broken = {"cp": {"laytime_basis": "SHINC"}, "ports": []}
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main([str(path)])
    assert exc.value.code == 1
    assert "demurrage_rate_per_day" in capsys.readouterr().err


def test_cli_reports_unreadable_file(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / "missing.json")])
    assert exc.value.code == 2
    assert "cannot read basis" in capsys.readouterr().err
