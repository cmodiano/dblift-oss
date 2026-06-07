"""Tests couvrant le contrat @abstractmethod de OutputFormatter.format() pour les formateurs concrets."""

from abc import ABC

import pytest

from core.sql_validator.linting.formatters import (
    CompactFormatter,
    ConsoleFormatter,
    GitHubActionsFormatter,
    GitLabFormatter,
    JSONFormatter,
    OutputFormatter,
    SarifFormatter,
)

pytestmark = [pytest.mark.unit]

ALL_CONCRETE_FORMATTERS = (
    ConsoleFormatter,
    JSONFormatter,
    CompactFormatter,
    SarifFormatter,
    GitHubActionsFormatter,
    GitLabFormatter,
)


def test_output_formatter_is_abstract_base_class():
    """OutputFormatter est une ABC et format() est abstraite."""
    assert issubclass(OutputFormatter, ABC)
    assert "format" in OutputFormatter.__abstractmethods__


def test_all_concrete_formatters_is_exhaustive():
    """ALL_CONCRETE_FORMATTERS couvre exactement toutes les sous-classes directes d'OutputFormatter."""
    assert set(ALL_CONCRETE_FORMATTERS) == set(OutputFormatter.__subclasses__())


@pytest.mark.parametrize("formatter_class", ALL_CONCRETE_FORMATTERS)
def test_concrete_formatter_implements_format(formatter_class):
    """Chaque formateur concret implémente format() dans son propre __dict__."""
    assert "format" in formatter_class.__dict__


@pytest.mark.parametrize("formatter_class", ALL_CONCRETE_FORMATTERS)
def test_concrete_formatter_instantiation(formatter_class):
    """Chaque formateur concret peut être instancié et est une instance de OutputFormatter."""
    instance = formatter_class()
    assert isinstance(instance, OutputFormatter)
    assert callable(instance.format)


def test_output_formatter_direct_instantiation_raises():
    """OutputFormatter ne peut pas être instancié directement."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        OutputFormatter()
