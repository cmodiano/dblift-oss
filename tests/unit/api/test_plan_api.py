from pathlib import Path
from unittest.mock import MagicMock


def test_plan_forwards_options_to_executor():
    from api.client import DBLiftClient

    result = MagicMock()
    client = DBLiftClient.__new__(DBLiftClient)
    client.executor = MagicMock()
    client.executor.plan.return_value = result
    client.events = MagicMock()
    client._get_scripts_dir = lambda: Path("migrations")

    actual = client.plan(
        snapshot_model="prod.snapshot.json",
        skip_validate_sql=True,
        validate_scope="all",
        dir_recursive_map={Path("migrations"): False},
    )

    assert actual is result
    assert client.executor.plan.call_args.kwargs["scripts_dir"] == Path("migrations")
    assert client.executor.plan.call_args.kwargs["snapshot_model"] == Path("prod.snapshot.json")
    assert client.executor.plan.call_args.kwargs["skip_validate_sql"] is True
    assert client.executor.plan.call_args.kwargs["validate_scope"] == "all"
    assert client.executor.plan.call_args.kwargs["dir_recursive_map"] == {Path("migrations"): False}
