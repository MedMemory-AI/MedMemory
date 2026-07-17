import bleach
import unicodedata


def clean_and_validate_query(query: str) -> str:
    """
    Sanitizes raw input to protect downstream vector queries and LLM prompts 
    from script injections, excessive whitespace, and malformed encodings.
    """
    if not query:
        raise ValueError("Query string cannot be empty or null.")

    # 1. Prevent ReDoS & Bypasses by stripping HTML/Script structures safely using Bleach
    # This leaves benign mathematical comparisons like '<' intact unless they mimic tags
    cleaned = bleach.clean(query, tags=[], attributes={}, strip=True)

    # 2. Unicode Normalization (converts variations like full-width characters to standard forms)
    cleaned = unicodedata.normalize("NFKC", cleaned)

    # 3. Collapse multiple spaces, newlines, or tabs into single spaces to preserve prompt efficiency
    cleaned = " ".join(cleaned.split())

    # 4. Check length constraints AFTER cleanup to prevent padding bypasses
    if not cleaned:
        raise ValueError("Query string contained no valid or safe text elements.")

    if len(cleaned) > 1000:
        raise ValueError("Query exceeds maximum allowed safety length of 1000 characters.")

    return cleaned
