"""HW report parsers."""

from .parse_vitis import parse_vitis_qor
from .parse_vivado import parse_vivado_qor

__all__ = ["parse_vitis_qor", "parse_vivado_qor"]
