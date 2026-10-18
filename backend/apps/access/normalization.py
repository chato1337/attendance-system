import re

from django.core.exceptions import ValidationError

KNOWN_OPS = {
    "trim",
    "upper",
    "strip_leading_zeros",
    "regex_extract",
    "hex_to_dec",
    "dec_to_hex",
    "pad_left",
}


class NormalizationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_steps(steps) -> None:
    if not isinstance(steps, list):
        raise ValidationError("La normalización debe ser una lista ordenada de pasos.")
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or "op" not in step:
            raise ValidationError(f"El paso {index} debe incluir la operación.")
        op = step["op"]
        if op not in KNOWN_OPS:
            raise ValidationError(f"Operación desconocida en el paso {index}: {op}.")
        if op == "regex_extract":
            pattern = step.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                raise ValidationError(f"El paso {index} requiere pattern.")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValidationError(f"Expresión regular inválida en el paso {index}.") from exc
        if op == "pad_left":
            length = step.get("length")
            if not isinstance(length, int) or isinstance(length, bool) or length < 1:
                raise ValidationError(f"El paso {index} requiere length entero positivo.")
            char = step.get("char", "0")
            if not isinstance(char, str) or len(char) != 1:
                raise ValidationError(f"El paso {index} requiere un único carácter de relleno.")


def apply_normalization(
    value: str,
    steps: list[dict],
    *,
    min_length: int | None = None,
    max_length: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise NormalizationError("El valor debe ser texto.")
    current = value
    for index, step in enumerate(steps, start=1):
        op = step.get("op") if isinstance(step, dict) else None
        if op not in KNOWN_OPS:
            raise NormalizationError(f"Paso {index} inválido.")
        try:
            current = _apply_step(current, step)
        except NormalizationError:
            raise
        except Exception as exc:
            raise NormalizationError(f"Paso {index} ({op}) falló.") from exc
    length = len(current)
    if min_length is not None and length < min_length:
        raise NormalizationError(f"Longitud {length} menor que el mínimo {min_length}.")
    if max_length is not None and length > max_length:
        raise NormalizationError(f"Longitud {length} mayor que el máximo {max_length}.")
    return current


def _apply_step(value: str, step: dict) -> str:
    op = step["op"]
    if op == "trim":
        return value.strip()
    if op == "upper":
        return value.upper()
    if op == "strip_leading_zeros":
        stripped = value.lstrip("0")
        return stripped or "0"
    if op == "regex_extract":
        match = re.search(step["pattern"], value)
        if match is None:
            raise NormalizationError("La expresión regular no encontró coincidencias.")
        if match.lastindex:
            return match.group(1)
        return match.group(0)
    if op == "hex_to_dec":
        if not re.fullmatch(r"[0-9A-Fa-f]+", value):
            raise NormalizationError("El valor no es hexadecimal.")
        return str(int(value, 16))
    if op == "dec_to_hex":
        if not re.fullmatch(r"[0-9]+", value):
            raise NormalizationError("El valor no es decimal.")
        return format(int(value), "X")
    if op == "pad_left":
        char = step.get("char", "0")
        return value.rjust(int(step["length"]), char)
    raise NormalizationError(f"Operación desconocida: {op}.")
