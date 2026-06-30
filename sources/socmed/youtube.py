from urllib.parse import urlparse, parse_qs

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from sources import BaseSource
from sources.registry import register_source
from shared.utils import Network, log
from shared.config import settings


@register_source("youtube")
class YoutubeSource(BaseSource):

    @property
    def _base(self) -> str:
        return settings.piped_base_url.rstrip("/")

    def _video_id(self, url: str) -> str:
        qs = parse_qs(urlparse(url).query)
        return (qs.get("v") or [""])[0]

    def _upload_date_filter(self, interval: str) -> str | None:
        """Map interval string ke Piped upload_date filter (best-effort, granularitas kasar)."""
        try:
            days = int(interval.rstrip("d"))
        except ValueError:
            return None
        if days <= 1:  return "today"
        if days <= 7:  return "week"
        if days <= 30: return "month"
        return "year"

    @override
    async def collect_urls(self, keyword: str, interval: str) -> list[dict]:
        videos: list[dict] = []
        nextpage: str | None = None
        upload_date = self._upload_date_filter(interval)

        for i in range(5):
            params: dict = {"q": keyword, "filter": "videos"}
            if upload_date:
                params["upload_date"] = upload_date
            if nextpage:
                params["nextpage"] = nextpage

            response = await Network.aget(url=f"{self._base}/search", params=params)
            if not response or not response.ok:
                break

            data = response.json()
            items = [i for i in (data.get("items") or []) if i.get("type") == "stream"]
            if not items:
                break

            for item in items:
                raw_url: str = item.get("url", "")
                video_id = self._video_id(raw_url)
                videos.append({
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": item.get("title", ""),
                    "media": item.get("uploaderName", ""),
                    "desc": item.get("shortDescription", ""),
                    "date": {
                        "epoch": item.get("uploaded"),
                        "text": item.get("uploadedDate", ""),
                    },
                })

            log.debug("[youtube] search → %d videos (total %d)", len(items), len(videos))
            nextpage = data.get("nextpage")
            if not nextpage:
                break

        return videos

    @override
    async def fetch_detail(self, content: dict) -> dict:
        video_id = self._video_id(content["url"])
        if not video_id:
            return content

        response = await Network.aget(url=f"{self._base}/streams/{video_id}")
        if not response or not response.ok:
            return {**content, "article_id": video_id, "raw": {}}

        return {**content, "article_id": video_id, "raw": response.json()}

    @override
    async def fetch_comments(self, content: dict) -> list[dict]:
        video_id = content.get("article_id", "")
        if not video_id:
            return []

        page: int = 1
        comments: list[dict] = []
        nextpage: str | None = None

        while True:
            params = {"nextpage": nextpage} if nextpage else None

            response = await Network.aget(
                url=f"{self._base}/comments/{video_id}",
                params=params,
            )
            if not response or not response.ok:
                break

            data = response.json()
            items: list[dict] = data.get("comments") or []
            if not items:
                break

            comments.extend(items)
            log.debug("[youtube] comments → %d (total %d)", len(items), len(comments))
            nextpage = data.get("nextpage")
            if not nextpage or page >= self.MAX_COMMENT_PAGES:
                break
            
            page+=1

        return comments
