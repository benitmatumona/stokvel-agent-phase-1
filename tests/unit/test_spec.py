import pytest
from pydantic import ValidationError

from agent.spec import GroupSpec


def test_valid_group_spec():
    spec = GroupSpec(
        contribution_lamports=500_000_000,
        max_members=10,
    )
    assert spec.is_complete is True
    assert spec.currency == "SOL"


def test_missing_details_make_spec_incomplete():
    spec = GroupSpec()
    assert spec.is_complete is False


def test_zero_contribution_is_rejected():
    with pytest.raises(ValidationError):
        GroupSpec(contribution_lamports=0)


def test_negative_contribution_is_rejected():
    with pytest.raises(ValidationError):
        GroupSpec(contribution_lamports=-100)


@pytest.mark.parametrize("size", [1, 21, 100])
def test_invalid_group_sizes_are_rejected(size):
    with pytest.raises(ValidationError):
        GroupSpec(max_members=size)


def test_valid_minimum_group_size():
    assert GroupSpec(max_members=2).max_members == 2


def test_valid_maximum_group_size():
    assert GroupSpec(max_members=20).max_members == 20


def test_unknown_currency_is_rejected():
    with pytest.raises(ValidationError):
        GroupSpec(currency="USDC")
