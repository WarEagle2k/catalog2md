"""Part number detection and protection utilities."""
from __future__ import annotations

import re
from typing import Optional


PART_NUMBER_PATTERNS = [
    re.compile(r'\b[A-Z0-9]{1,6}(?:-[A-Z0-9]{1,6}){2,}\b'),
    re.compile(r'\b[A-Z]{1,5}-\d{2,6}(?:-[A-Z0-9]{1,5})?\b'),
    re.compile(r'\b\d{2,6}-\d{2,6}\b'),
    re.compile(r'\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{5,12}\b'),
    re.compile(r'\b[A-Z0-9]{1,4}(?:\.[A-Z0-9]{1,4}){2,}\b'),
    re.compile(r'\b[A-Z0-9]{1,6}(?:/[A-Z0-9]{1,6}){1,3}\b'),
]

FALSE_POSITIVE_PATTERNS = [
    re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$'),
    re.compile(r'^\d{1,2}-\d{1,2}-\d{2,4}$'),
    re.compile(r'^https?://'),
    re.compile(r'^\d+\.\d+\.\d+$'),
    re.compile(r'^[A-Z]{1,3}$'),
    re.compile(r'^\d{1,4}$'),
    re.compile(r'^(?:PSI|GPM|CFM|RPM|BTU|kPa|\u00b0[CF])$', re.IGNORECASE),
    re.compile(r'^(?:MAX|MIN|AVG|REF|TYP|NOM)$', re.IGNORECASE),
    re.compile(r'^(?:ANSI|ASTM|ISO|ASME|AWS|NFPA|UL|CSA)\b'),
]


def is_false_positive(candidate: str) -> bool:
    for pattern in FALSE_POSITIVE_PATTERNS:
        if pattern.match(candidate):
            return True
    return False


def extract_part_numbers(text: str) -> list[str]:
    candidates: set[str] = set()
    for pattern in PART_NUMBER_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group()
            if not is_false_positive(candidate):
                candidates.add(candidate)
    return sorted(candidates)


def protect_part_numbers(text: str) -> tuple[str, dict[str, str]]:
    placeholder_map: dict[str, str] = {}
    masked = text
    part_numbers = extract_part_numbers(text)
    for i, pn in enumerate(part_numbers):
        placeholder = f"__PARTNUM_{i:04d}__"
        placeholder_map[placeholder] = pn
        masked = re.sub(re.escape(pn), placeholder, masked)
    return masked, placeholder_map


def restore_part_numbers(text: str, placeholder_map: dict[str, str]) -> str:
    restored = text
    for placeholder, original in placeholder_map.items():
        restored = restored.replace(placeholder, original)
    return restored


def validate_part_number_density(
    source_part_numbers: list[str],
    output_part_numbers: list[str],
    threshold: float = 0.85,
) -> tuple[bool, str]:
    if not source_part_numbers:
        return True, "No part numbers in source"
    source_set = set(source_part_numbers)
    output_set = set(output_part_numbers)
    preserved = source_set & output_set
    missing = source_set - output_set
    ratio = len(preserved) / len(source_set) if source_set else 1.0
    if ratio >= threshold:
        return True, f"Part number density OK: {len(preserved)}/{len(source_set)} preserved ({ratio:.1%})"
    else:
        missing_sample = list(missing)[:10]
        return False, (
            f"Part number density LOW: {len(preserved)}/{len(source_set)} preserved ({ratio:.1%}). "
            f"Missing examples: {missing_sample}"
        )
