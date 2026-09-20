"""Conversão estrita de dinheiro, sem ponto flutuante."""
import re
from decimal import Decimal, InvalidOperation

MAX_CENTAVOS = 9_223_372_036_854_775_807


def parse_money_to_centavos(value: str | None) -> int | None:
    raw = (value or '').strip()
    if raw.startswith('R$'):
        raw = raw[2:].strip()
    if not raw or len(raw) > 32:
        return None
    # Aceita decimal brasileiro ou decimal sem separador de milhares.
    # Um ponto seguido de três dígitos conserva o formato brasileiro 1.234.
    if re.fullmatch(r'-?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?', raw):
        normalized = raw.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'-?\d+(?:[,.]\d{1,2})?', raw):
        normalized = raw.replace(',', '.')
    else:
        return None
    try:
        cents = int(Decimal(normalized) * 100)
    except (InvalidOperation, ValueError, OverflowError):
        return None
    return cents if abs(cents) <= MAX_CENTAVOS else None
