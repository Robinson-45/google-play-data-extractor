thonimport json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

@dataclass
class GooglePlayParserConfig:
    base_url_template: str = (
        "https://play.google.com/store/apps/details?id={app_id}&hl={hl}&gl={gl}"
    )
    timeout: int = 15
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0 Safari/537.36"
    )

class GooglePlayParser:
    """
    Fetch and parse app details from the Google Play Store.

    Note: Google may change their HTML/JSON structure at any time. This parser
    uses a mix of JSON-LD data and meta tags for resilience.
    """

    def __init__(
        self,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
        config: Optional[GooglePlayParserConfig] = None,
    ) -> None:
        self.config = config or GooglePlayParserConfig(timeout=timeout)
        self.config.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent})

    def build_url(self, app_id: str, locale: str, country: str) -> str:
        return self.config.base_url_template.format(app_id=app_id, hl=locale, gl=country)

    def fetch_app_page(self, app_id: str, locale: str, country: str) -> str:
        url = self.build_url(app_id, locale, country)
        LOGGER.debug("Fetching URL: %s", url)
        try:
            response = self.session.get(url, timeout=self.config.timeout)
            response.raise_for_status()
            return response.text
        except requests.HTTPError as http_err:
            LOGGER.error("HTTP error for %s: %s", app_id, http_err)
            raise
        except requests.RequestException as req_err:
            LOGGER.error("Request error for %s: %s", app_id, req_err)
            raise

    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except json.JSONDecodeError:
                continue

            # Sometimes wrapped in a list
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "SoftwareApplication":
                        return item
            elif isinstance(data, dict) and data.get("@type") == "SoftwareApplication":
                return data
        return None

    def _safe_get(self, container: Dict[str, Any], *keys: str, default: Any = None) -> Any:
        current: Any = container
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key, default)
        return current

    def parse_app_data(self, html: str, app_id: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")

        json_ld = self._extract_json_ld(soup) or {}

        # Meta tags as fallback
        meta_title = soup.find("meta", property="og:title")
        meta_desc = soup.find("meta", property="og:description")
        meta_image = soup.find("meta", property="og:image")

        title = json_ld.get("name") or (meta_title["content"].strip() if meta_title and meta_title.has_attr("content") else None)
        description = json_ld.get("description") or (
            meta_desc["content"].strip() if meta_desc and meta_desc.has_attr("content") else None
        )
        icon_url = json_ld.get("image") or (
            meta_image["content"].strip() if meta_image and meta_image.has_attr("content") else None
        )

        # Developer / author info
        developer = None
        developer_website = None
        author = json_ld.get("author") or json_ld.get("publisher")

        if isinstance(author, dict):
            developer = author.get("name")
            developer_website = author.get("url") or author.get("sameAs")
        elif isinstance(author, str):
            developer = author

        # Category
        category = json_ld.get("applicationCategory") or json_ld.get("genre")

        # Ratings
        rating_value = self._safe_get(json_ld, "aggregateRating", default={}).get("ratingValue")
        reviews_count = (
            self._safe_get(json_ld, "aggregateRating", default={}).get("ratingCount")
            or self._safe_get(json_ld, "aggregateRating", default={}).get("reviewCount")
        )

        # Price & monetization
        offers = json_ld.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = offers.get("price")
        currency = offers.get("priceCurrency")
        if price is None or price == 0 or str(price) == "0":
            price_str = "Free"
        else:
            price_str = f"{price} {currency}" if currency else str(price)

        # In-app purchases
        # Google Play's JSON-LD may not explicitly state this; we attempt a heuristic using description.
        in_app_purchases = False
        desc_lower = (description or "").lower()
        triggers = [
            "in-app purchases",
            "offers in-app purchases",
            "offers in app purchases",
            "contains ads",
        ]
        if any(t in desc_lower for t in triggers):
            in_app_purchases = True

        # Installs and other fields are not reliably available in JSON-LD.
        # We keep them as None here; downstream cleaner can handle it.
        installs = None

        # Version, release dates
        version = json_ld.get("softwareVersion")
        release_date = json_ld.get("datePublished")
        last_updated = json_ld.get("dateModified")

        screenshots = []
        if "screenshot" in json_ld:
            if isinstance(json_ld["screenshot"], list):
                screenshots = json_ld["screenshot"]
            else:
                screenshots = [json_ld["screenshot"]]

        parsed = {
            "appId": app_id,
            "title": title,
            "developer": developer,
            "category": category,
            "rating": rating_value,
            "reviewsCount": reviews_count,
            "installs": installs,
            "price": price_str,
            "inAppPurchases": in_app_purchases,
            "description": description,
            "releaseDate": release_date,
            "lastUpdated": last_updated,
            "version": version,
            "screenshots": screenshots,
            "iconUrl": icon_url,
            "developerWebsite": developer_website,
        }

        LOGGER.debug("Parsed raw data for %s: %s", app_id, parsed)
        return parsed

    def get_app_data(self, app_id: str, locale: str = "en", country: str = "us") -> Dict[str, Any]:
        """
        Fetch the Google Play page for `app_id` and return parsed metadata.
        """
        if not app_id:
            raise ValueError("app_id must be a non-empty string")

        html = self.fetch_app_page(app_id, locale, country)
        return self.parse_app_data(html, app_id)