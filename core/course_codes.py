import json
import os
import re
from typing import List, Optional, Dict

DATA_PATH = "catalog_courses_full.json"

ALIAS_OVERRIDES = {
    "ewrt1a": "ENGL C1000",
    "ewrt1": "ENGL C1000",
    "ewrtd001a": "ENGL C1000",
    "english1a": "ENGL C1000",
    "engl1a": "ENGL C1000",
    "english1000": "ENGL C1000",
    "math1a": "MATH 1A",
    "math1b": "MATH 1B",
    "cis22a": "CIS 22A",
    "cis22b": "CIS 22B",
    "cis22c": "CIS 22C",
}

class CourseIndex:
    def __init__(self, path: str = DATA_PATH):
        self.by_code: Dict[str, dict] = {}
        self.by_alias: Dict[str, str] = {}

        if os.path.exists(path):
            with open(path, "r", encoding = "utf-8") as f:
                courses = json.load(f)

            for c in courses:
                if not isinstance(c, dict) or "error" in c:
                    continue
                code = (c.get("code") or c.get("Course ID (CB01A and CB01B)") or "").strip()
                if not code:
                    continue

                self.by_code[code] = c
                for alias in self._generate_aliases(code):
                    self.by_alias[alias] = code

    @staticmethod
    def _generate_aliases(code: str):
        aliases = []
        compact = re.sub(r"\s+", "", code).lower()
        aliases.append(compact)

        m = re.match(r"^\s*([A-Za-z]+)\s*D0*(\d+[A-Za-z]?)\s*$", code)
        if m:
            prefix, num = m.group(1).lower(), m.group(2).lower()
            aliases.append(f"{prefix}{num}")
            aliases.append(f"{prefix} {num}")
            aliases.append(f"{prefix}-{num}")

        return aliases

    def normalize(self, text: str):
        clean = re.sub(r"[\s\-_]+", "", text).lower()
        if clean in ALIAS_OVERRIDES:
            return ALIAS_OVERRIDES[clean]
        return self.by_alias.get(clean)

    def find_in_text(self, text:str):
        """Extract course code mention from natural language user query."""
        #Check standard couse pattern (e.g. CIS 22A, Math-1A, Phys4A)
        tokens = re.findall(r"\b([A-Za-z]{2,5}[\s\-_]?D?0*\d{1,4}[A-Za-z]?)\b", text)
        for token in tokens:
            resolved = self.normalize(token)
            if resolved:
                return resolved
        return None

_INDEX = None

def get_index():
    global _INDEX
    if _INDEX is None:
        _INDEX = CourseIndex()
    return _INDEX

def resolve_code(query: str):
    return get_index().find_in_text(query)