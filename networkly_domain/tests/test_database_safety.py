"""The domain test harness must never reset a maintenance or app database."""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _module(name):
    spec = importlib.util.spec_from_file_location(f"domain_safety_{name}", Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("database", ["postgres", "coverage", "production"])
@pytest.mark.parametrize("module_name", ["conftest", "test_pipeline_postgres"])
def test_non_test_databases_are_closed_before_any_sql(database, module_name):
    module = _module(module_name)
    connection = MagicMock()
    connection.info.dbname = database
    with patch("psycopg.connect", return_value=connection):
        with pytest.raises(pytest.fail.Exception, match="test_"):
            if module_name == "conftest":
                module.make_postgres_conn("postgresql:///ignored")
            else:
                module._connect()
    connection.close.assert_called_once()
    connection.execute.assert_not_called()
