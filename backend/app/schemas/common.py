"""Piezas compartidas por los schemas del contrato."""

from __future__ import annotations


def is_absent(value: object) -> bool:
    """Predicado para `Field(exclude_if=...)`: la clave se omite si no tiene valor.

    El contrato (`docs/12-api.md` §2.3 y §2.4) muestra cada objeto sólo con las claves que le
    corresponden: el feedback del tipo 2 no lleva `consensus`, y un lado con campeones no lleva
    `label`. Mandarlas en `null` no es lo mismo, porque el cliente distingue «ausente» de «nulo»
    —`consensus !== undefined` dibuja las barras—.

    Se usa `exclude_if` y no un `model_serializer` porque éste obliga a anotar el retorno como
    `dict[str, Any]`, y FastAPI publicaría entonces un objeto sin campos en el OpenAPI.
    """
    return value is None
