"""Utility to robustly extract JSON from LLM responses.

Models sometimes wrap the JSON in ```json ... ``` or add extra text. This
function tries to recover the first valid JSON object from the text.
"""

from __future__ import annotations

import json
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a text, tolerating surrounding noise.

    Raises:
        ValueError: if no parseable JSON object is found.
    """
    text = text.strip()
    # Direct case.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Look for the first balanced {...} block.
    start = text.find("{")
    if start == -1:
        raise ValueError("La respuesta del LLM no contiene un objeto JSON")

    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    break
    raise ValueError("No se pudo parsear un objeto JSON de la respuesta del LLM")
