"""
The Antenna — Chief Delphi Scraper (AN.1)
Fetches topics from Chief Delphi's Discourse API.
Team 2950 — The Devastators
"""

import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional

from config import (
    CD_BASE_URL,
    CD_USER_AGENT,
    CD_RATE_LIMIT_SECONDS,
    CD_TOPICS_PER_PAGE,
    MAX_PAGES_PER_RUN,
)

logger = logging.getLogger("antenna.scraper")


class CDScraper:
    """Scrapes Chief Delphi topics via the Discourse public JSON API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": CD_USER_AGENT,
            "Accept": "application/json",
        })
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < CD_RATE_LIMIT_SECONDS:
            time.sleep(CD_RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a rate-limited GET request to Chief Delphi."""
        self._rate_limit()
        url = f"{CD_BASE_URL}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            if resp.status_code == 429:
                logger.warning("Rate limited! Waiting 30 seconds...")
                time.sleep(30)
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching {url}: {e}")
            return None
        except ValueError as e:
            logger.error(f"JSON decode error for {url}: {e}")
            return None

    def fetch_latest_topics(self, max_pages: int = MAX_PAGES_PER_RUN) -> list[dict]:
        """
        Fetch the latest topics from Chief Delphi.
        Returns a list of topic dicts with standardized keys.
        """
        all_topics = []

        for page in range(max_pages):
            logger.info(f"Fetching page {page} of latest topics...")
            data = self._get("/latest.json", params={"page": page})

            if not data or "topic_list" not in data:
                logger.warning(f"No data on page {page}, stopping.")
                break

            topics = data["topic_list"].get("topics", [])
            if not topics:
                logger.info(f"No more topics on page {page}, stopping.")
                break

            for topic in topics:
                standardized = self._standardize_topic(topic)
                if standardized:
                    all_topics.append(standardized)

            # Check if there are more pages
            if not data["topic_list"].get("more_topics_url"):
                logger.info("No more pages available.")
                break

        logger.info(f"Fetched {len(all_topics)} topics across {page + 1} pages.")
        return all_topics

    def fetch_category_topics(self, category_slug: str,
                              max_pages: int = 3) -> list[dict]:
        """Fetch latest topics from a specific category."""
        all_topics = []

        for page in range(max_pages):
            data = self._get(
                f"/c/{category_slug}/l/latest.json",
                params={"page": page}
            )
            if not data or "topic_list" not in data:
                break

            topics = data["topic_list"].get("topics", [])
            if not topics:
                break

            for topic in topics:
                standardized = self._standardize_topic(topic)
                if standardized:
                    all_topics.append(standardized)

            if not data["topic_list"].get("more_topics_url"):
                break

        return all_topics

    def fetch_topic_detail(self, topic_id: int) -> Optional[dict]:
        """
        Fetch full detail for a single topic, including first post content.
        Use sparingly — only for high-priority posts that need deeper analysis.
        """
        data = self._get(f"/t/{topic_id}.json")
        if not data:
            return None

        result = {
            "topic_id": data.get("id"),
            "title": data.get("title", ""),
            "category_id": data.get("category_id"),
            "like_count": data.get("like_count", 0),
            "views": data.get("views", 0),
            "posts_count": data.get("posts_count", 0),
            "tags": data.get("tags", []),
        }

        # Get first post content (the OP)
        post_stream = data.get("post_stream", {})
        posts = post_stream.get("posts", [])
        if posts:
            first_post = posts[0]
            result["op_username"] = first_post.get("username", "")
            result["op_cooked"] = first_post.get("cooked", "")  # HTML content
            result["op_like_count"] = first_post.get("like_count", 0)

        return result

    def _standardize_topic(self, raw: dict) -> Optional[dict]:
        """Convert raw Discourse topic dict to our standard format."""
        topic_id = raw.get("id")
        if not topic_id:
            return None

        # Skip pinned/archived topics on subsequent pages
        if raw.get("archived") or raw.get("closed"):
            return None

        title = raw.get("title", "")
        slug = raw.get("slug", "")

        # Extract poster info
        posters = raw.get("posters", [])
        author = ""
        if posters:
            # First poster with description containing "Original Poster"
            for p in posters:
                if "Original Poster" in (p.get("description") or ""):
                    # The user info is in the top-level users array,
                    # but we only have the poster extras here.
                    # Use last_poster_username as fallback.
                    break
        author = raw.get("last_poster_username", "")

        # Build excerpt from available data
        excerpt = raw.get("excerpt", "") or ""
        last_post_excerpt = raw.get("last_post_excerpt", "") or ""

        # Handle tags - can be list of dicts or list of strings
        tags = raw.get("tags", [])
        if isinstance(tags, list) and tags and isinstance(tags[0], dict):
            tags_str = ",".join(t.get("name", "") for t in tags)
        elif isinstance(tags, list):
            tags_str = ",".join(str(t) for t in tags)
        else:
            tags_str = ""

        return {
            "topic_id": topic_id,
            "url": f"{CD_BASE_URL}/t/{slug}/{topic_id}",
            "title": title,
            "author": author,
            "category_id": raw.get("category_id"),
            "category_name": "",  # Filled in later if needed
            "date_posted": raw.get("created_at", ""),
            "last_activity": raw.get("last_posted_at", ""),
            "like_count": raw.get("like_count", 0) or 0,
            "reply_count": raw.get("posts_count", 1) - 1,  # posts includes OP
            "views": raw.get("views", 0) or 0,
            "tags": tags_str,
            "raw_excerpt": excerpt,
            "summary": excerpt[:200] if excerpt else "",
            # These are filled in by the scorer
            "excerpt": f"{title} {excerpt} {last_post_excerpt}",
        }


def fetch_and_filter_recent(scraper: CDScraper,
                            since: Optional[datetime] = None,
                            max_pages: int = MAX_PAGES_PER_RUN) -> list[dict]:
    """
    Fetch recent topics and optionally filter to only those
    posted/updated since a given datetime.
    """
    topics = scraper.fetch_latest_topics(max_pages=max_pages)

    if since:
        filtered = []
        for t in topics:
            last_activity = t.get("last_activity", "")
            if last_activity:
                try:
                    activity_dt = datetime.fromisoformat(
                        last_activity.replace("Z", "+00:00")
                    )
                    since_aware = since.replace(
                        tzinfo=activity_dt.tzinfo
                    ) if activity_dt.tzinfo else since
                    if activity_dt >= since_aware:
                        filtered.append(t)
                except (ValueError, TypeError):
                    filtered.append(t)  # Include if we can't parse
            else:
                filtered.append(t)
        logger.info(
            f"Filtered to {len(filtered)} topics updated since {since.isoformat()}"
        )
        return filtered

    return topics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    scraper = CDScraper()

    print("=" * 60)
    print("ANTENNA SCRAPER — TEST RUN")
    print("=" * 60)

    # Fetch 2 pages (60 topics) as a test
    topics = scraper.fetch_latest_topics(max_pages=2)

    print(f"\nFetched {len(topics)} topics\n")
    for t in topics[:10]:
        print(f"  [{t['topic_id']}] {t['title'][:60]}")
        print(f"    Likes: {t['like_count']} | Replies: {t['reply_count']} | Views: {t['views']}")
        print(f"    Tags: {t['tags'] or 'none'}")
        print()
