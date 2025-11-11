thonimport logging
from typing import Any, Dict, List, Union, Optional

LOGGER = logging.getLogger(__name__)

EXPECTED_FIELDS = [
    "appId",
    "title",
    "developer",
    "category",
    "rating",
    "reviewsCount",
    "installs",
    "price",
    "inAppPurchases",
    "description",
    "releaseDate",
    "lastUpdated",
    "version",
    "screenshots",
    "iconUrl",
    "developerWebsite",
]

def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        LOGGER.debug("Unable to convert to float: %r", value)
        return None

def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, int):
            return value
        s = str(value).replace(",", "").replace("+", "").strip()
        # Some forms like 'UserDownloads:1000000'
        if ":" in s:
            s = s.split(":", 1)[1]
        return int(s)
    except (ValueError, TypeError):
        LOGGER.debug("Unable to convert to int: %r", value)
        return None

def _normalize_installs(installs: Any) -> Optional[str]:
    if installs is None:
        return None
    s = str(installs).strip()
    if not s:
        return None
    return s

def _normalize_in_app_purchases(value: Any, description: Optional[str]) -> Union[bool, List[str]]:
    """
    Currently returns a boolean. If you later extend this to parse explicit
    IAP items, you can switch to a list of strings.
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, list) and value:
        # Already a list of items
        return value

    desc = (description or "").lower()
    keywords = ["in-app purchases", "offers in-app purchases", "offers in app purchases"]
    if any(k in desc for k in keywords):
        return True

    return False

def normalize_app_data(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize raw parser output into a clean, consistent record.
    Ensures all expected fields are present and in the expected types.
    """
    cleaned: Dict[str, Any] = {}

    for field in EXPECTED_FIELDS:
        cleaned[field] = raw.get(field)

    cleaned["title"] = cleaned["title"].strip() if isinstance(cleaned["title"], str) else cleaned["title"]
    cleaned["developer"] = (
        cleaned["developer"].strip() if isinstance(cleaned["developer"], str) else cleaned["developer"]
    )
    cleaned["category"] = (
        cleaned["category"].strip() if isinstance(cleaned["category"], str) else cleaned["category"]
    )
    cleaned["description"] = (
        cleaned["description"].strip() if isinstance(cleaned["description"], str) else cleaned["description"]
    )

    cleaned["rating"] = _to_float(cleaned["rating"])
    cleaned["reviewsCount"] = _to_int(cleaned["reviewsCount"])

    cleaned["installs"] = _normalize_installs(cleaned["installs"])

    # Normalize price field to a friendly string
    price = cleaned["price"]
    if price is None:
        cleaned["price"] = "Unknown"
    else:
        s = str(price).strip()
        if s in {"0", "0.0", "Free", ""}:
            cleaned["price"] = "Free"
        else:
            cleaned["price"] = s

    cleaned["inAppPurchases"] = _normalize_in_app_purchases(
        cleaned["inAppPurchases"], cleaned["description"]
    )

    if not isinstance(cleaned["screenshots"], list):
        cleaned["screenshots"] = (
            [cleaned["screenshots"]] if cleaned["screenshots"] is not None else []
        )

    # Ensure URLs are trimmed
    for url_field in ("iconUrl", "developerWebsite"):
        val = cleaned.get(url_field)
        if isinstance(val, str):
            cleaned[url_field] = val.strip()

    LOGGER.debug("Normalized data: %s", cleaned)
    return cleaned