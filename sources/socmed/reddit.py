import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from sources import BaseSource
from sources.registry import register_source
from shared.utils import Network, log


@register_source("reddit")
class RedditSource(BaseSource):
    """
    Reddit source plugin.

    Search:   https://www.reddit.com/search.rss (Atom feed, no auth needed)
    Comments: https://api.pullpush.io/reddit/search/comment/ (PullPush archive)

    RSS returns real-time results without any authentication. PullPush may lag
    a few days behind for very recent comments, which is acceptable for sentiment.

    content_id = Reddit post ID (e.g. "1uk6agk", the t3_ suffix stripped).
    """

    _SEARCH_RSS  = "https://www.reddit.com/search.rss"
    _COMMENT_URL = "https://api.pullpush.io/reddit/search/comment/"
    _RSS_LIMIT   = 100
    _ATOM_NS     = "http://www.w3.org/2005/Atom"

    _HEADERS = {
        "User-Agent":      "voice-scraper/1.0 (data engineering portfolio; public data only)",
        "Accept":          "application/atom+xml, application/xml, text/xml, */*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def _cutoff_ts(self, interval: str) -> float:
        try:
            days = int(interval.rstrip("d"))
        except ValueError:
            days = 30
        return (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

    def _parse_rss(self, xml_bytes: bytes, cutoff_ts: float) -> tuple[list[dict], bool]:
        """
        Parse Atom RSS bytes into content dicts. Filters only t3_ (post) entries.
        Returns (contents, stop) where stop=True means cutoff was reached.
        """
        # Decode with replacement to handle any surrogate characters Reddit emits
        safe = xml_bytes.decode("utf-8", errors="replace").encode("utf-8")
        try:
            root = ET.fromstring(safe)
        except ET.ParseError as e:
            log.error(f"[reddit] RSS parse error: {e}")
            return [], False

        ns   = self._ATOM_NS
        contents: list[dict] = []
        stop = False

        for entry in root.findall(f"{{{ns}}}entry"):
            entry_id = entry.findtext(f"{{{ns}}}id") or ""

            # Skip subreddit entries (t5_) — only process posts (t3_)
            if not entry_id.startswith("t3_"):
                continue
            post_id = entry_id[3:]  # strip "t3_"

            # Timestamp
            pub_str = entry.findtext(f"{{{ns}}}published") or ""
            try:
                pub_dt   = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                created_ts = pub_dt.timestamp()
            except ValueError:
                created_ts = 0.0

            if created_ts and created_ts < cutoff_ts:
                stop = True
                break

            # URL
            link_el = entry.find(f"{{{ns}}}link")
            url = link_el.get("href", "") if link_el is not None else ""

            # Title
            title = entry.findtext(f"{{{ns}}}title") or ""

            # Author — Reddit emits "/u/username"
            author_el = entry.find(f"{{{ns}}}author")
            author = ""
            if author_el is not None:
                author = (author_el.findtext(f"{{{ns}}}name") or "").lstrip("/u")

            # Subreddit from <category term="subreddit_name"/>
            cat_el = entry.find(f"{{{ns}}}category")
            subreddit = cat_el.get("term", "") if cat_el is not None else ""

            contents.append({
                "url":        url,
                "content_id": post_id,
                "title":      title,
                "media":      f"r/{subreddit}" if subreddit else "",
                "desc":       "",
                "date":       {"text": pub_str},
                "_author":    author,
                "_created_ts": created_ts,
            })

        return contents, stop

    @override
    async def collect_urls(self, keyword: str, interval: str) -> list[dict]:
        cutoff_ts = self._cutoff_ts(interval)

        response = await Network.aget(
            url=self._SEARCH_RSS,
            params={"q": keyword, "sort": "new", "limit": self._RSS_LIMIT},
            headers=self._HEADERS,
            retry=3,
            backoff=2.0,
        )
        if not response or not response.ok:
            log.warning(f"[reddit] RSS request failed (status {response.status_code if response else 'none'})")
            return []

        contents, _ = self._parse_rss(response.content, cutoff_ts)

        if not contents:
            log.info(f"[reddit] no posts found for '{keyword}' within interval {interval}")
        else:
            log.debug(f"[reddit] RSS → {len(contents)} posts")

        return contents

    @override
    async def fetch_detail(self, content: dict) -> dict:
        # All metadata already in the RSS entry — no extra HTTP request needed.
        raw = {
            "id":          content["content_id"],
            "title":       content["title"],
            "author":      content.get("_author", ""),
            "subreddit":   content["media"].lstrip("r/"),
            "url":         content["url"],
            "created_utc": content.get("_created_ts", 0),
        }
        clean = {k: v for k, v in content.items() if not k.startswith("_")}
        return {
            **clean,
            "author": content.get("_author", ""),
            "raw":    json.dumps(raw, ensure_ascii=False),
        }

    @override
    async def fetch_comments(self, content: dict) -> list[dict]:
        post_id = content.get("content_id", "")
        if not post_id:
            return []

        all_comments: list[dict] = []
        before: int | None = None

        for page in range(1, self.MAX_COMMENT_PAGES + 1):
            params: dict = {
                "link_id": f"t3_{post_id}",
                "size":    100,
                "sort":    "asc",
            }
            if before:
                params["before"] = before

            response = await Network.aget(
                url=self._COMMENT_URL,
                params=params,
                headers=self._HEADERS,
            )
            if not response or not response.ok:
                break

            comments = response.json().get("data", [])
            if not comments:
                break

            all_comments.extend(comments)

            if len(comments) < 100:
                break
            oldest_ts = min(c.get("created_utc", 0) for c in comments if c.get("created_utc"))
            if not oldest_ts:
                break
            before = oldest_ts

        if not all_comments:
            log.info(f"[reddit] post {post_id} → 0 comments (PullPush may not have indexed this post yet — usually takes 1-2 weeks for recent posts)")
        else:
            log.debug(f"[reddit] post {post_id} → {len(all_comments)} comments")
        return all_comments
