"""Part number detection and protection utilities."""
from __future__ import annotations

import re
from typing import Optional


# Industrial part number patterns — ordered by specificity (most specific first)
PART_NUMBER_PATTERNS = [
    # Dash-separated alphanumeric with multiple segments: ABC-1234-DEF, 12-3456-AB-7
    re.compile(r'\b[A-Z0-9]{1,6}(?:-[A-Z0-9]{1,6}){2,}\b'),
    # Letter prefix + dash + digits + optional suffix: AH-350, VLV-2001A, FLT-100-SS
    re.compile(r'\b[A-Z]{1,5}-\d{2,6}(?:-[A-Z0-9]{1,5})?\b'),
    # Digits + dash + digits pattern: 12345-001, 99-1234
    re.compile(r'\b\d{2,6}-\d{2,6}\b'),
    # Pure alphanumeric codes with mixed letters/digits, 5+ chars: ABC123, 12AB34
    re.compile(r'\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{5,12}\b'),
    # Codes with dots: 1.234.567, A1.B2.C3
    re.compile(r'\b[A-Z0-9]{1,4}(?:\.[A-Z0-9]{1,4}){2,}\b'),
    # Slash-separated part numbers: 123/456, ABC/123/DEF
    re.compile(r'\b[A-Z0-9]{1,6}(?:/[A-Z0-9]{1,6}){1,3}\b'),
]

# Common false positives to exclude
FALSE_POSITIVE_PATTERNS = [
    re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$'),      # Dates: 1/2/2025
    re.compile(r'^\d{1,2}-\d{1,2}-\d{2,4}$'),       # Dates: 1-2-2025
    re.compile(r'^https?://'),                         # URLs
    re.compile(r'^\d+\.\d+\.\d+$'),                   # Version numbers
    re.compile(r'^[A-Z]{1,3}$'),                       # Pure short abbreviations
    re.compile(r'^\d{1,4}$'),                          # Pure short numbers
    re.compile(r'^(?:PSI|GPM|CFM|RPM|BTU|kPa|°[CF])$', re.IGNORECASE),  # Units
    re.compile(r'^(?:MAX|MIN|AVG|REF|TYP|NOM)$', re.IGNORECASE),       # Spec abbreviations
    re.compile(r'^(?:ANSI|ASTM|ISO|ASME|AWS|NFPA|UL|CSA)\b'),         # Standards orgs
]


def is_false_positive(candidate: str) -> bool:
    """Check if a candidate part number is actually something else."""
    for pattern in FALSE_POSITIVE_PATTERNS:
        if pattern.match(candidate):
            return True
    return False


def extract_part_numbers(text: str) -> list[str]:
    """Extract unique part numbers from text, filtering false positives."""
    candidates: set[str] = set()
    for pattern in PART_NUMBER_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group()
            if not is_false_positive(candidate):
                candidates.add(candidate)
    return sorted(candidates)


def protect_part_numbers(text: str) -> tuple[str, dict[str, str]]:
    """Replace part numbers with placeholders to prevent splitting.
    
    Returns:
        Tuple of (masked_text, placeholder_map) where placeholder_map
        maps placeholder -> original part number
    """
    placeholder_map: dict[str, str] = {}
    masked = text
    part_numbers = extract_part_numbers(text)
    
    for i, pn in enumerate(part_numbers):
        placeholder = f"__PARTNUM_{i:04d}__"
        placeholder_map[placeholder] = pn
        # Replace only whole-word occurrences
        masked = re.sub(re.escape(pn), placeholder, masked)
    
    return masked, placeholder_map


def restore_part_numbers(text: str, placeholder_map: dict[str, str]) -> str:
    """Restore original part numbers from placeholders."""
    restored = text
    for placeholder, original in placeholder_map.items():
        restored = restored.replace(placeholder, original)
    return restored


def validate_part_number_density(
    source_part_numbers: list[str],
    output_part_numbers: list[str],
    threshold: float = 0.85,
) -> tuple[bool, str]:
    """Validate that output preserves most part numbers from source.
    
    Returns:
        Tuple of (passed, message)
    """
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
