"""Operator board filters select the intended catalog subset in stable order."""
import pytest

from directory import boards
from networkly_connectors.models import GreenhouseBoard, LeverBoard


@pytest.fixture
def catalog(monkeypatch):
    rows = [
        ("alpha", LeverBoard(firm="Alpha", org="alpha-general")),
        ("beta", GreenhouseBoard(firm="Beta", token="beta")),
        ("alpha", GreenhouseBoard(firm="Alpha", token="alpha-campus")),
        ("gamma", GreenhouseBoard(firm="Gamma", token="gamma")),
        ("alpha", LeverBoard(firm="Alpha", org="alpha-campus")),
    ]
    monkeypatch.setattr(boards, "BOARDS", rows)
    return rows


def test_unfiltered_selection_preserves_order_and_board_identity(catalog):
    selected = boards.select_boards()
    assert selected == catalog
    assert all(actual[1] is expected[1] for actual, expected in zip(selected, catalog))


def test_provider_and_firm_filters_intersect_instead_of_broadening(catalog):
    assert boards.select_boards(provider="greenhouse") == [catalog[1], catalog[2], catalog[3]]
    assert boards.select_boards(firm_slug="alpha") == [catalog[0], catalog[2], catalog[4]]
    assert boards.select_boards(provider="greenhouse", firm_slug="alpha") == [catalog[2]]
    assert boards.select_boards(provider="lever", firm_slug="beta") == []


@pytest.mark.parametrize("limit,positions", [(0, []), (1, [1]), (2, [1, 2]), (20, [1, 2, 3])])
def test_limit_applies_after_filtering_and_preserves_catalog_order(catalog, limit, positions):
    assert boards.select_boards(provider="greenhouse", limit=limit) == [catalog[i] for i in positions]
    assert [board[1].provider for board in catalog] == ["lever", "greenhouse", "greenhouse", "greenhouse", "lever"]


@pytest.mark.parametrize("filters", [{"provider": "unknown"}, {"firm_slug": "absent"}])
def test_unknown_filter_does_not_fall_back_to_scraping_the_entire_catalog(catalog, filters):
    assert boards.select_boards(**filters) == []


def test_sequential_selection_does_not_mutate_the_next_run_catalog(catalog):
    original = list(catalog)
    assert boards.select_boards(provider="lever", firm_slug="alpha", limit=1) == [catalog[0]]
    assert boards.select_boards(firm_slug="gamma") == [catalog[3]]
    assert boards.select_boards() == original and catalog == original
