"""Phase 1c batch CLI — runs fully offline, prints a summary, exits cleanly.

No DB and no network: ``run`` is driven with an offline ``Settings`` so ``init_db``
returns False and the connection stays ``None``.
"""

from agentic_scd.ingestion import batch_cli

if __package__:
    from .fakes import make_settings
else:
    from fakes import make_settings


def test_run_offline_loads_seed_and_skips_retention() -> None:
    batch, retention = batch_cli.run(make_settings())
    assert batch is not None and retention is not None
    assert batch.db_persisted is False
    assert batch.totals.loaded == 16
    assert batch.totals.persisted == 0  # no DB -> nothing persisted
    assert retention.ran is False  # no DB -> retention no-op


def test_run_load_only_skips_retention() -> None:
    batch, retention = batch_cli.run(make_settings(), do_load=True, do_retain=False)
    assert batch is not None
    assert retention is None


def test_run_retain_only_skips_load() -> None:
    batch, retention = batch_cli.run(make_settings(), do_load=False, do_retain=True)
    assert batch is None
    assert retention is not None and retention.ran is False


def test_print_summary_offline_smoke(capsys) -> None:
    batch, retention = batch_cli.run(make_settings())
    batch_cli.print_summary(batch, retention)
    out = capsys.readouterr().out
    assert "Batch run complete" in out
    assert "freightos_baltic_index" in out
    assert "kaggle_supplychainnet" in out
    assert "Retention:" in out


def test_main_runs_offline_without_crashing(monkeypatch, capsys) -> None:
    # Force the offline path regardless of any local Postgres.
    monkeypatch.setattr(batch_cli, "get_settings", make_settings)
    batch_cli.main([])
    out = capsys.readouterr().out
    assert "Batch run complete" in out


def test_parse_args_flags() -> None:
    assert batch_cli.parse_args(["--load"]).load is True
    assert batch_cli.parse_args(["--retain"]).retain is True
    ns = batch_cli.parse_args([])
    assert ns.load is False and ns.retain is False
