import re
from flashtext import KeywordProcessor

# Build keyword processor ONCE at module level
_kp = KeywordProcessor(case_sensitive=False)
_kp.add_keywords_from_list(["gold", "operation", "content", "temperature", "high", "official", "time", "system", "place", "people", "large", "major", "history", "north", "business", "old", "term", "company", "acquisition_years", "mayor", "west", "team", "town", "grid", "location", "region", "home", "acquisitionyear", "park", "acquisition year"])

# Compile regex patterns ONCE at module level
_PATTERNS = [
    re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', re.IGNORECASE),
    re.compile(r'[\$£€¥]\s*\d[\d,]*(?:\.\d+)?', re.IGNORECASE),
    re.compile(r'\b[A-Z]{2,5}:\s*[A-Z0-9]+\b', re.IGNORECASE),
    re.compile(r'\b\d+(?:\.\d+)?\s*%', re.IGNORECASE)
]

def is_relevant(text: str) -> bool:
    if not text or not text.strip():
        return False
    # Fast keyword check
    if _kp.extract_keywords(text):
        return True
    # Regex check
    for pat in _PATTERNS:
        if pat.search(text):
            return True
    return False