from __future__ import annotations

import asyncio
import math
import sys
import time
from typing import Any, Callable

from .logger import log

# ── optional backend detection ──────────────────────────────────────────
try:
    import requests as _requests_lib
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    import cloudscraper as _cloudscraper_lib
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _HAS_CLOUDSCRAPER = False

import httpx  # always available


# ── helpers ─────────────────────────────────────────────────────────────
def _fmt_size(n: float) -> str:
    if n == 0:
        return "0  B"
    units = ["B", "KB", "MB", "GB"]
    i = min(int(math.log(abs(n), 1024)), len(units) - 1)
    return f"{n / (1024 ** i):.1f} {units[i]}"


def _fmt_time(s: float) -> str:
    if s < 1:
        return f"{s * 1000:.0f} ms"
    if s < 60:
        return f"{s:.1f} s"
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s"


# ── progress bar ────────────────────────────────────────────────────────
class _Progress:
    """Terminal progress bar untuk tracking download."""

    _W = 30  # bar width

    def __init__(self, total: int, label: str = "") -> None:
        self.total = max(total, 1)
        self.label = label
        self._start = time.time()
        self._last_draw = 0.0
        self._history: list[tuple[float, int]] = []

    def update(self, downloaded: int, status: str = "") -> None:
        now = time.time()
        if now - self._last_draw < 0.08 and downloaded < self.total:
            return
        self._last_draw = now
        self._history.append((now, downloaded))

        # Speed (rata-rata 3 detik terakhir)
        cutoff = now - 3
        recent = [(t, b) for t, b in self._history if t >= cutoff]
        if len(recent) >= 2:
            speed = (recent[-1][1] - recent[0][1]) / max(recent[-1][0] - recent[0][0], 0.01)
        else:
            speed = 0

        pct = min(downloaded / self.total, 1.0)
        filled = int(self._W * pct)
        bar = "█" * filled + "░" * (self._W - filled)
        elapsed = now - self._start
        eta = (self.total - downloaded) / speed if speed > 0 else 0

        line = (
            f"\r  {bar}  {pct * 100:5.1f}%  │  "
            f"{_fmt_size(downloaded)} / {_fmt_size(self.total)}  │  "
            f"{_fmt_size(speed)}/s  │  "
            f"ETA {_fmt_time(eta)}  │  "
            f"⏱ {_fmt_time(elapsed)}"
        )
        if status:
            line += f"  │  {status}"
        sys.stderr.write(line + "\r")
        sys.stderr.flush()

    def done(self, status: str = "") -> None:
        elapsed = time.time() - self._start
        bar = "█" * self._W
        line = (
            f"\r  {bar}  100.0%  │  "
            f"{_fmt_size(self.total)} / {_fmt_size(self.total)}  │  "
            f"Done  │  ⏱ {_fmt_time(elapsed)}"
        )
        if status:
            line += f"  │  {status}"
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


# ── response ────────────────────────────────────────────────────────────
class Response:
    """Unified response object — mirip httpx/requests.Response."""

    def __init__(
        self,
        status_code: int,
        headers: dict,
        url: str,
        content: bytes,
        elapsed: float = 0.0,
        encoding: str = "utf-8",
    ):
        self.status_code = status_code
        self.headers = headers
        self.url = url
        self.content = content
        self.elapsed = elapsed
        self.encoding = encoding
        self._json = None

    def json(self) -> Any:
        if self._json is None:
            import json as _json

            self._json = _json.loads(self.content.decode(self.encoding))
        return self._json

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding, errors="replace")

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return (
            f"<Response [{self.status_code}] "
            f"{_fmt_size(len(self.content))} "
            f"in {_fmt_time(self.elapsed)}>"
        )


# ── backends ────────────────────────────────────────────────────────────
class _HttpxBackend:
    @staticmethod
    def request(
        method: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        json: Any = None,
        data: str | bytes | dict | None = None,
        files: dict | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify: bool | str = True,
        progress_callback: Callable | None = None,
        **_,
    ) -> Response:
        client_kw = dict(
            timeout=timeout,
            follow_redirects=follow_redirects,
            verify=verify,
        )
        if auth:
            client_kw["auth"] = auth

        proxy = _proxy_url()
        if proxy:
            client_kw["proxy"] = proxy

        with httpx.Client(**client_kw) as client:
            if progress_callback:
                start = time.time()
                with client.stream(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                    json=json,
                    data=data,
                    files=files,
                ) as stream:
                    chunks, total = [], 0
                    for chunk in stream.iter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        progress_callback(total)
                    content = b"".join(chunks)
                    elapsed = time.time() - start
                    return Response(
                        status_code=stream.status_code,
                        headers=dict(stream.headers),
                        url=str(stream.url),
                        content=content,
                        elapsed=elapsed,
                    )
            else:
                start = time.time()
                resp = client.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                    json=json,
                    data=data,
                    files=files,
                )
                elapsed = time.time() - start
                return Response(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    url=str(resp.url),
                    content=resp.content,
                    elapsed=elapsed,
                )


class _RequestsBackend:
    @staticmethod
    def request(
        method: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        json: Any = None,
        data: str | bytes | dict | None = None,
        files: dict | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify: bool | str = True,
        progress_callback: Callable | None = None,
        **_,
    ) -> Response:
        if not _HAS_REQUESTS:
            raise ImportError("requests not installed → pip install requests")

        proxy = _proxy_url()
        proxies = {"http": proxy, "https": proxy} if proxy else None

        start = time.time()
        resp = _requests_lib.request(
            method=method,
            url=url,
            params=params,
            headers=headers,
            cookies=cookies,
            json=json,
            data=data,
            files=files,
            auth=auth,
            timeout=timeout,
            allow_redirects=follow_redirects,
            verify=verify,
            proxies=proxies,
            stream=progress_callback is not None,
        )

        if progress_callback:
            chunks, total = [], 0
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    chunks.append(chunk)
                    total += len(chunk)
                    progress_callback(total)
            content = b"".join(chunks)
        else:
            content = resp.content

        elapsed = time.time() - start
        return Response(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            url=resp.url,
            content=content,
            elapsed=elapsed,
        )


class _CloudscraperBackend:
    @staticmethod
    def request(
        method: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        json: Any = None,
        data: str | bytes | dict | None = None,
        files: dict | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify: bool | str = True,
        progress_callback: Callable | None = None,
        **_,
    ) -> Response:
        if not _HAS_CLOUDSCRAPER:
            raise ImportError("cloudscraper not installed → pip install cloudscraper")

        scraper = _cloudscraper_lib.create_scraper()
        start = time.time()
        resp = scraper.request(
            method=method,
            url=url,
            params=params,
            headers=headers,
            cookies=cookies,
            json=json,
            data=data,
            files=files,
            auth=auth,
            timeout=timeout,
            allow_redirects=follow_redirects,
            verify=verify,
            stream=progress_callback is not None,
        )

        if progress_callback:
            chunks, total = [], 0
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    chunks.append(chunk)
                    total += len(chunk)
                    progress_callback(total)
            content = b"".join(chunks)
        else:
            content = resp.content

        elapsed = time.time() - start
        return Response(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            url=resp.url,
            content=content,
            elapsed=elapsed,
        )


# ── config helpers (lazy import to avoid circular deps) ─────────────────
def _scraper_delay() -> float:
    try:
        from shared.config import settings
        return settings.scraper_delay
    except Exception:
        return 1.0


def _proxy_url() -> str:
    try:
        from shared.config import settings
        return settings.proxy_url or ""
    except Exception:
        return ""


# ── registry ────────────────────────────────────────────────────────────
_BACKENDS: dict[str, Any] = {
    "httpx": _HttpxBackend,
    "requests": _RequestsBackend,
    "cloudscraper": _CloudscraperBackend,
}

_RETRYABLE = (429, 500, 502, 503, 504)


# ── Network class ───────────────────────────────────────────────────────
class Network:
    """
    HTTP client all-in-one.

    Semua method static. Panggil langsung tanpa instantiate.

    Parameters
    ----------
    url : str
    params : dict      — query string parameters
    headers : dict     — request headers
    cookies : dict     — cookies
    json : any         — JSON body (auto set Content-Type)
    data : str|bytes|dict — raw/form body
    files : dict       — multipart upload
    auth : (user, pass) — basic auth
    timeout : float    — default 30 detik
    follow_redirects : bool — default True
    verify : bool|str  — SSL verify (False = skip)
    backend : str      — "httpx" | "requests" | "cloudscraper"
    retry : int        — jumlah retry (default 0)
    retry_on : tuple   — status code yang di-retry (default: 429,5xx)
    backoff : float    — multiplier backoff (default 1.5)
    show_progress : bool — tampilkan progress bar (default True)
    """

    # Expose Response as Network.Response (mirip requests.Response)
    Response = Response

    # ── internal ────────────────────────────────────────────────────
    @staticmethod
    def _payload(
        method: str,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        json: Any = None,
        data: str | bytes | dict | None = None,
        files: dict | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify: bool | str = True,
        **extra,
    ) -> dict:
        return dict(
            method=method.upper(),
            url=url,
            params=params,
            headers=headers,
            cookies=cookies,
            json=json,
            data=data,
            files=files,
            auth=auth,
            timeout=timeout,
            follow_redirects=follow_redirects,
            verify=verify,
            **extra,
        )

    # ── core request ────────────────────────────────────────────────
    @staticmethod
    def request(
        method: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        json: Any = None,
        data: str | bytes | dict | None = None,
        files: dict | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        verify: bool | str = True,
        backend: str = "httpx",
        retry: int = 0,
        retry_on: tuple[int, ...] = _RETRYABLE,
        backoff: float = 1.5,
        show_progress: bool = True,
        **kwargs,
    ) -> Response | None:
        """Core HTTP request dengan retry, progress, dan logging."""

        # Validasi backend
        bk = backend.lower()
        if bk not in _BACKENDS:
            log.error(f"Unknown backend [{bk}]. Available: {', '.join(_BACKENDS)}")
            return None
        engine = _BACKENDS[bk]

        payload = Network._payload(
            method=method,
            url=url,
            params=params,
            headers=headers,
            cookies=cookies,
            json=json,
            data=data,
            files=files,
            auth=auth,
            timeout=timeout,
            follow_redirects=follow_redirects,
            verify=verify,
            **kwargs,
        )

        # Log request
        log.info(f"⟶  {method.upper()} {url}")
        if params:
            log.debug(f"   params : {params}")
        if headers:
            log.debug(f"   headers: {headers}")
        if cookies:
            log.debug(f"   cookies: {cookies}")
        if json is not None:
            log.debug(f"   json   : {json}")
        if data is not None:
            log.debug(f"   data   : {data}")
        log.debug(f"   backend: {bk}  |  retry: {retry}  |  timeout: {timeout}s")

        # Progress bar state
        progress: _Progress | None = None
        content_length = 0

        def _on_progress(downloaded: int) -> None:
            if progress is not None:
                progress.update(downloaded)

        last_error: Exception | None = None

        for attempt in range(retry + 1):
            try:
                if attempt > 0:
                    log.info(f"   ↻ retry {attempt}/{retry} …")

                # Jalankan request
                resp = engine.request(**payload, progress_callback=_on_progress if show_progress else None)

                # Log hasil
                size = _fmt_size(len(resp.content))
                dur = _fmt_time(resp.elapsed)
                icon = "✓" if resp.ok else "✗"
                level = "SUCCESS" if resp.ok else "WARNING"
                log.log(
                    "INFO" if resp.ok else "WARNING",
                    f"   {icon} {resp.status_code}  │  {size}  │  {dur}  │  {resp.url}",
                )

                # Retry kalau status retryable
                if resp.status_code in retry_on and attempt < retry:
                    wait = backoff ** (attempt + 1)
                    log.warning(f"   ⚠ status {resp.status_code} → retry in {wait:.1f}s")
                    time.sleep(wait)
                    continue

                return resp

            except (httpx.TimeoutException, httpx.ConnectError,
                    httpx.RemoteProtocolError, httpx.NetworkError) as e:
                last_error = e
                log.warning(f"   ✗ network error (attempt {attempt + 1}): {e}")

            except Exception as e:
                last_error = e
                # Tangkap juga error dari requests/cloudscraper
                name = type(e).__name__
                if any(x in name.lower() for x in ("timeout", "connection", "network", "proxy", "sslerror")):
                    log.warning(f"   ✗ {name} (attempt {attempt + 1}): {e}")
                else:
                    log.error(f"   ✗ unexpected {name}: {e}")
                    # Unexpected error → jangan retry
                    return None

            if attempt < retry:
                wait = backoff ** (attempt + 1)
                log.info(f"   ⏳ waiting {wait:.1f}s …")
                time.sleep(wait)

        # Semua gagal
        log.error(
            f"   ✗ ALL {retry + 1} ATTEMPTS FAILED for {method.upper()} {url}"
        )
        if last_error:
            log.error(f"   last error: {type(last_error).__name__}: {last_error}")
        return None

    # ── HTTP method shortcuts ───────────────────────────────────────
    @staticmethod
    def get(url: str, **kwargs) -> Response | None:
        return Network.request("GET", url, **kwargs)

    @staticmethod
    def post(url: str, **kwargs) -> Response | None:
        return Network.request("POST", url, **kwargs)

    @staticmethod
    def put(url: str, **kwargs) -> Response | None:
        return Network.request("PUT", url, **kwargs)

    @staticmethod
    def patch(url: str, **kwargs) -> Response | None:
        return Network.request("PATCH", url, **kwargs)

    @staticmethod
    def delete(url: str, **kwargs) -> Response | None:
        return Network.request("DELETE", url, **kwargs)

    @staticmethod
    def head(url: str, **kwargs) -> Response | None:
        kwargs.setdefault("show_progress", False)
        return Network.request("HEAD", url, **kwargs)

    @staticmethod
    def options(url: str, **kwargs) -> Response | None:
        kwargs.setdefault("show_progress", False)
        return Network.request("OPTIONS", url, **kwargs)

    # ── async shortcuts (wraps sync methods via asyncio.to_thread) ─────────
    @staticmethod
    async def arequest(method: str, url: str, **kwargs) -> Response | None:
        return await asyncio.to_thread(Network.request, method, url, **kwargs)

    @staticmethod
    async def aget(url: str, **kwargs) -> Response | None:
        delay = _scraper_delay()
        if delay > 0:
            await asyncio.sleep(delay)
        return await asyncio.to_thread(Network.get, url, **kwargs)

    @staticmethod
    async def apost(url: str, **kwargs) -> Response | None:
        delay = _scraper_delay()
        if delay > 0:
            await asyncio.sleep(delay)
        return await asyncio.to_thread(Network.post, url, **kwargs)

    @staticmethod
    async def aput(url: str, **kwargs) -> Response | None:
        return await asyncio.to_thread(Network.put, url, **kwargs)

    @staticmethod
    async def apatch(url: str, **kwargs) -> Response | None:
        return await asyncio.to_thread(Network.patch, url, **kwargs)

    @staticmethod
    async def adelete(url: str, **kwargs) -> Response | None:
        return await asyncio.to_thread(Network.delete, url, **kwargs)

    @staticmethod
    async def ahead(url: str, **kwargs) -> Response | None:
        return await asyncio.to_thread(Network.head, url, **kwargs)

    @staticmethod
    async def aoptions(url: str, **kwargs) -> Response | None:
        return await asyncio.to_thread(Network.options, url, **kwargs)

    # ── download ────────────────────────────────────────────────────
    @staticmethod
    def download(url: str, path: str, **kwargs) -> bool:
        """Download file ke local path dengan progress bar otomatis."""
        from shared.utils.fileIO import File
        from shared.utils.directory import Dir

        resp = Network.get(url, show_progress=True, **kwargs)
        if resp is None or not resp.ok:
            log.error(f"Download failed: {url}")
            return False

        Dir.create_dir(Dir.basedir(path))
        with open(path, "wb") as f:
            f.write(resp.content)

        log.info(f"   ✓ saved → {path}  ({_fmt_size(len(resp.content))})")
        return True

    # ── info ────────────────────────────────────────────────────────
    @staticmethod
    def backends() -> list[str]:
        """List backend yang tersedia."""
        r = ["httpx"]
        if _HAS_REQUESTS:
            r.append("requests")
        if _HAS_CLOUDSCRAPER:
            r.append("cloudscraper")
        return r

    @staticmethod
    def info() -> None:
        """Tampilkan info backend."""
        log.info(f"Available backends: {', '.join(Network.backends())}")
        log.info(f"  httpx         — {'✓' if True else '✗'} always installed")
        log.info(f"  requests      — {'✓' if _HAS_REQUESTS else '✗ pip install requests'}")
        log.info(f"  cloudscraper  — {'✓' if _HAS_CLOUDSCRAPER else '✗ pip install cloudscraper'}")
