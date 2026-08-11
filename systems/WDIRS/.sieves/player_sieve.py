import re
from flashtext import KeywordProcessor

# Build keyword processor ONCE at module level
_kp = KeywordProcessor(case_sensitive=False)
_kp.add_keywords_from_list(["site", "resident", "people", "average", "team_name", "fiba_titles", "gold_medal", "player_college", "positions", "nba_championships_won", "mvpawards", "years", "gold_medals", "owner_ids", "team_names", "fiba_titles", "urban", "content", "nba_championship", "district", "city", "governor", "town", "gold", "railroad", "hasfibaworldcuptitle", "draft_picks", "nationalitys", "plains", "team name"])

# Compile regex patterns ONCE at module level
_PATTERNS = [
    re.compile(r'\b\d+(?:\.\d+)?\s*%', re.IGNORECASE),
    re.compile(r'\b[A-Z]{2,5}:\s*[A-Z0-9]+\b', re.IGNORECASE),
    re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', re.IGNORECASE),
    re.compile(r'[\$£€¥]\s*\d[\d,]*(?:\.\d+)?', re.IGNORECASE)
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