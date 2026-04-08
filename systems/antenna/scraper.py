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
    CD_CATEGORY_SLUGS,
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

    def _build_user_lookup(self, data: dict) -> dict:
        """Build a user_id → username lookup from the API response."""
        lookup = {}
        for user in data.get("users", []):
            lookup[user.get("id")] = user.get("username", "")
        return lookup

    def _extract_topics(self, data: dict) -> list[dict]:
        """Extract and standardize topics from an API response."""
        if not data or "topic_list" not in data:
            return []
        user_lookup = self._build_user_lookup(data)
        results = []
        for topic in data["topic_list"].get("topics", []):
            standardized = self._standardize_topic(topic, user_lookup)
            if standardized:
                results.append(standardized)
        return results

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

            topics = self._extract_topics(data)
            if not topics:
                logger.info(f"No more topics on page {page}, stopping.")
                break

            all_topics.extend(topics)

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

            topics = self._extract_topics(data)
            if not topics:
                break

            all_topics.extend(topics)

            if not data["topic_list"].get("more_topics_url"):
                break

        return all_topics

    def fetch_priority_categories(self, max_pages_per_cat: int = 3) -> list[dict]:
        """
        Fetch topics from priority categories (Technical, Competition).
        Deduplicates against /latest results by topic_id.
        """
        all_topics = []
        seen_ids = set()

        for cat_id, slug in CD_CATEGORY_SLUGS.items():
            logger.info(f"Fetching category: {slug} (id={cat_id})...")
            topics = self.fetch_category_topics(slug, max_pages=max_pages_per_cat)
            for t in topics:
                if t["topic_id"] not in seen_ids:
                    t["category_name"] = slug
                    all_topics.append(t)
                    seen_ids.add(t["topic_id"])

        logger.info(f"Fetched {len(all_topics)} unique topics from priority categories.")
        return all_topics

    def search_topics(self, query: str, max_results: int = 20) -> list[dict]:
        """
        Search Chief Delphi for a specific query.
        Returns standardized topic dicts.
        """
        data = self._get("/search.json", params={"q": query})
        if not data:
            return []

        results = []
        seen_ids = set()

        for topic in data.get("topics", []):
            if topic.get("id") in seen_ids:
                continue
            seen_ids.add(topic["id"])

            # Search results have a slightly different shape than /latest
            standardized = {
                "topic_id": topic.get("id"),
                "url": f"{CD_BASE_URL}/t/{topic.get('slug', '')}/{topic.get('id')}",
                "title": topic.get("title", ""),
                "author": "",
                "category_id": topic.get("category_id"),
                "category_name": "",
                "date_posted": topic.get("created_at", ""),
                "last_activity": topic.get("last_posted_at", ""),
                "like_count": topic.get("like_count", 0) or 0,
                "reply_count": max(0, (topic.get("posts_count", 1) or 1) - 1),
                "views": topic.get("views", 0) or 0,
                "tags": "",
                "raw_excerpt": "",
                "summary": "",
                "excerpt": topic.get("title", ""),
            }

            # Search results include blurb text from matching posts
            for post in data.get("posts", []):
                if post.get("topic_id") == topic["id"]:
                    blurb = post.get("blurb", "")
                    standardized["excerpt"] = f"{standardized['title']} {blurb}"
                    standardized["raw_excerpt"] = blurb[:200]
                    standardized["author"] = post.get("username", "")
                    break

            results.append(standardized)

            if len(results) >= max_results:
                break

        logger.info(f"Search '{query}': {len(results)} results")
        return results

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

    def _standardize_topic(self, raw: dict,
                           user_lookup: Optional[dict] = None) -> Optional[dict]:
        """Convert raw Discourse topic dict to our standard format."""
        topic_id = raw.get("id")
        if not topic_id:
            return None

        # Skip pinned/archived topics on subsequent pages
        if raw.get("archived") or raw.get("closed"):
            return None

        title = raw.get("title", "")
        slug = raw.get("slug", "")

        # Extract OP username from posters array + user lookup
        author = ""
        posters = raw.get("posters", [])
        if posters and user_lookup:
            for p in posters:
                if "Original Poster" in (p.get("description") or ""):
                    user_id = p.get("user_id")
                    if user_id and user_id in user_lookup:
                        author = user_lookup[user_id]
                    break
        if not author:
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
            "reply_count": (raw.get("posts_count") or 1) - 1,  # posts includes OP
            "views": raw.get("views", 0) or 0,
            "tags": tags_str,
            "raw_excerpt": excerpt,
            "summary": excerpt[:200] if excerpt else "",
            # These are filled in by the scorer
            "excerpt": f"{title} {excerpt} {last_post_excerpt}",
        }


def fetch_and_filter_recent(scraper: CDScraper,
                            since: Optional[datetime] = None,
                            max_pages: int = MAX_PAGES_PER_RUN,
                            include_categories: bool = True) -> list[dict]:
    """
    Fetch recent topics from /latest and priority categories.
    Deduplicates by topic_id. Optionally filter by date.
    """
    # Fetch from /latest
    topics = scraper.fetch_latest_topics(max_pages=max_pages)
    seen_ids = {t["topic_id"] for t in topics}

    # Also fetch from priority categories to catch category-specific posts
    if include_categories:
        cat_topics = scraper.fetch_priority_categories(max_pages_per_cat=2)
        for t in cat_topics:
            if t["topic_id"] not in seen_ids:
                topics.append(t)
                seen_ids.add(t["topic_id"])
        logger.info(f"Combined: {len(topics)} unique topics (latest + categories)")

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
