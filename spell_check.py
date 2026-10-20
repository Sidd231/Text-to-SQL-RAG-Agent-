import re
import string
from rapidfuzz import fuzz, process

CITIES: dict[str, list[str]] = {
    "Mumbai": ["Bombay", "Mumbai", "Bom"],
    "Kolkata": ["Calcutta", "Kolkata", "Cal"],
    "Chennai": ["Madras", "Chennai", "Maa"],
    "Bengaluru": ["Bangalore", "Bengaluru", "Blr"],
    "Thiruvananthapuram": ["Trivandrum", "Thiruvananthapuram", "Trv"],
    "Puducherry": ["Pondicherry", "Puducherry"],
    "Vadodara": ["Baroda", "Vadodara", "Bdg"],
    "Kochi": ["Cochin", "Kochi", "Cok"],
    "Prayagraj": ["Allahabad", "Prayagraj"],
    "Varanasi": ["Banaras", "Kashi", "Varanasi"],
    "Gurugram": ["Gurgaon", "Gurugram"],
    "Mysuru": ["Mysore", "Mysuru"],
    "Delhi": ["New Delhi", "Delhi", "Del"],
    "Goa": ["Goa", "Goi"],
    "Jaipur": ["Jaipur", "Jai"],
    "Hyderabad": ["Hyderabad", "Hyd"],
    "Pune": ["Pune", "Pnx"],
    "Ahmedabad": ["Ahmedabad", "Amd"],
    "Chandigarh": ["Chandigarh", "Ixc"],
    "Lucknow": ["Lucknow", "Lko"],
    "Agra": ["Agra", "Agr"],
    "Udaipur": ["Udaipur", "Udr"],
}

# Build mapping of alias -> canonical city name
CITY_MAP: dict[str, str] = {}
for canonical_name, aliases in CITIES.items():
    CITY_MAP[canonical_name.lower()] = canonical_name
    for alias in aliases:
        CITY_MAP[alias.lower()] = canonical_name

# Sort aliases by length descending so multi-word aliases (e.g. "new delhi") match first
ALL_ALIASES = sorted(CITY_MAP.keys(), key=lambda x: len(x), reverse=True)

# Common words to exclude from fuzzy city matching to prevent false positives
STOP_WORDS = {
    "what", "which", "where", "how", "who", "when", "why", "there", "their",
    "many", "much", "more", "most", "some", "any", "all", "each", "every",
    "hotel", "hotels", "flight", "flights", "booking", "bookings", "booked",
    "customer", "customers", "client", "clients", "city", "cities", "place",
    "database", "table", "data", "price", "cost", "total", "amount", "money",
    "night", "nights", "stay", "stays", "pool", "wifi", "free", "business",
    "class", "economy", "hour", "hours", "time", "date", "from", "for", "with",
    "under", "over", "between", "cancelled", "confirmed", "spend", "spent",
    "rate", "rating", "find", "show", "give", "list", "tell", "cheapest",
    "expensive", "highest", "lowest", "best", "worst", "count", "average"
}


def right_name(user_input: str, threshold: int = 80) -> str | None:
    """Finds canonical city name for a given word or short phrase."""
    if not user_input or not isinstance(user_input, str):
        return None

    clean = user_input.strip().lower()

    # Exact match check first (handles short codes like 'blr', 'goa', etc.)
    if clean in CITY_MAP:
        return CITY_MAP[clean]

    # Don't fuzzy-match common domain/query words or very short words
    if clean in STOP_WORDS or len(clean) < 4:
        return None

    res = process.extractOne(clean, ALL_ALIASES, scorer=fuzz.WRatio)
    if res:
        match, score, _ = res
        if score >= threshold:
            return CITY_MAP[match]

    return None


def check(text: str) -> str:
    """Normalizes city names in the user question to canonical database names,

    preserving punctuation and structure.
    """
    if not text:
        return ""

    result = text

    # Step 1: Replace multi-word city aliases (e.g. "New Delhi") first
    for alias in ALL_ALIASES:
        if " " in alias:
            pattern = re.compile(rf"\b{re.escape(alias)}\b", flags=re.IGNORECASE)
            result = pattern.sub(CITY_MAP[alias], result)

    # Step 2: Tokenize words while preserving attached punctuation
    tokens = re.findall(r"\w+|[^\w\s]|\s+", result)
    processed_tokens = []

    for token in tokens:
        # If it's a word token
        if token.isalnum():
            # Check if this token matches a city name/alias
            corrected = right_name(token)
            processed_tokens.append(corrected if corrected else token)
        else:
            processed_tokens.append(token)

    return "".join(processed_tokens)


# Aliases for backward compatibility
citys = CITIES
new_dis = CITY_MAP
old_name = ALL_ALIASES
right_name_func = right_name
