#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgGuard Incident Player — PyQt6 + python-vlc with a tiny DVR proxy.

What’s new in this build:
- Dynamic live lag: on any segment 404/410, the proxy temporarily hides more
  tail segments in /live.m3u8 so VLC never requests unavailable parts.
  (Decay back to normal once stable.)
- No DVR freeze on resolve (removed items disappear; playback stops/advances).
- DVR seek/scrub still works *after* incident is marked resolved, using the
  segments already buffered in memory.
- No-cache headers on HLS endpoints.
- Smoother stream:
  * DVR poll interval tightened (REFRESH_MS default 300 ms).
  * VLC network caching default increased (800 ms).
"""

from __future__ import annotations
import sys, os, asyncio, threading, time, re, json
from dataclasses import dataclass
from typing import Optional, List, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import vlc  # python-vlc

from aiohttp import web, ClientSession
from aiohttp.client_exceptions import ClientConnectionError, ClientPayloadError

from vast.views.security.events_history_page import EventsHistoryPage
from src.vast.views.security.analytics.analytics_page import GeoAnalyticsView


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
class Config:
    MEDIA_BASE = os.getenv("MEDIA_BASE", "http://media-proxy:8080")
    INCIDENT = os.getenv("INCIDENT", "placeholder")
    TOKEN = os.getenv("MEDIA_TOKEN", "CHANGE_ME")
    BIND = os.getenv("BIND", "127.0.0.1")
    PORT = int(os.getenv("PORT", "19100"))

    # Poll upstream playlist ~2–4x per segment (1.0s segments -> 300ms is good)
    # ↓ Previously 20000 ms, which caused "segment → pause → segment" behaviour in DVR.
    REFRESH_MS = int(os.getenv("REFRESH_MS", "300"))

    # Show this many segments in the live window…
    LIVE_EDGE_SEGMENTS = int(os.getenv("LIVE_EDGE_SEGMENTS", "3"))
    # …but hide the freshest N (stay behind live edge to avoid stalls)
    LIVE_LAG_SEGMENTS = int(os.getenv("LIVE_LAG_SEGMENTS", "1"))

    # VLC network caching (ms) — slightly higher default for smoother playback
    NETWORK_CACHING = int(os.getenv("NETWORK_CACHING", "800"))

    ALERTS_WS = os.getenv("ALERTS_WS", "ws://host.docker.internal:8010/ws/alerts")
    ALERTS_SNAPSHOT_HTTP = os.getenv("ALERTS_SNAPSHOT_HTTP", "")
    ALLOWED_TYPES = {"climbing_fence", "masked_person", "intruding animal"}


# ──────────────────────────────────────────────────────────────────────────────
# Upstream fetcher + DVR state
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Segment:
    uri: str
    duration: float
    abs_url: str  # absolute URL to fetch


class DvrState:
    def __init__(self, upstream_index_url: str, auth_token: str = "", refresh_ms: int = 800):
        self.upstream_index_url = upstream_index_url
        self.auth_token = auth_token
        self.refresh_ms = refresh_ms
        self.init_url: Optional[str] = None
        self.target_duration: float = 1.0
        self.version: int = 6
        self.segments: List[Segment] = []
        self._last_playlist_text: Optional[str] = None
        self._stop = False
        self._ready_evt = threading.Event()
        self._lock = threading.Lock()

    @staticmethod
    def _absolutize(base: str, maybe_rel: str) -> str:
        return urljoin(base, maybe_rel)

    async def _fetch_text(self, session: ClientSession, url: str) -> Tuple[int, str]:
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        async with session.get(url, headers=headers, timeout=10) as resp:
            txt = await resp.text()
            status = resp.status
            if status == 200 and txt.lstrip().startswith("#EXTM3U"):
                print(f"[DVR] fetched playlist {status}, {len(txt)} bytes")
            else:
                print(f"[DVR] upstream status={status}, body[:120]={txt[:120]!r}")
            return status, txt

    def stop(self):
        self._stop = True
        self._ready_evt.set()

    async def run(self):
        async with ClientSession() as session:
            base = self.upstream_index_url
            base_dir = base.rsplit("/", 1)[0] + "/"
            while not self._stop:
                try:
                    status, text = await self._fetch_text(session, base)

                    # Hard-stop conditions: upstream removed/closed
                    if status in (404, 410):
                        print(f"[DVR] upstream gone (HTTP {status}); stop polling")
                        self.stop()
                        break

                    # Always parse; de-dupe by URL prevents dupes
                    if text.lstrip().startswith("#EXTM3U"):
                        self._parse_and_update(text, base_dir)
                        self._last_playlist_text = text
                        self._ready_evt.set()
                    else:
                        if text != self._last_playlist_text:
                            self._last_playlist_text = text
                            print("[DVR] NOTE: got non-HLS body; will retry.")
                except Exception as e:
                    print(f"[DVR] fetch error: {e!r}")
                await asyncio.sleep(self.refresh_ms / 1000.0)

    def _parse_and_update(self, playlist_text: str, base_dir: str):
        lines = [l.strip() for l in playlist_text.splitlines() if l.strip()]

        target_from_tag: Optional[float] = None
        max_seen_extinf = 0.0
        for l in lines:
            if l.startswith('#EXT-X-TARGETDURATION:'):
                try:
                    target_from_tag = float(l.split(':', 1)[1])
                except Exception:
                    pass
            elif l.startswith('#EXT-X-VERSION:'):
                try:
                    self.version = int(l.split(':', 1)[1])
                except Exception:
                    pass
            elif l.startswith('#EXT-X-MAP:'):
                m = re.search(r'URI="([^"]+)"', l)
                if m:
                    self.init_url = self._absolutize(base_dir, m.group(1))
            elif l.startswith('#EXTINF:'):
                try:
                    d = float(l.split(':', 1)[1].split(',')[0])
                    max_seen_extinf = max(max_seen_extinf, d)
                except Exception:
                    pass

        new_segments: List[Segment] = []
        i = 0
        while i < len(lines):
            l = lines[i]
            if l.startswith('#EXTINF:'):
                try:
                    dur = float(l.split(':', 1)[1].split(',')[0])
                except Exception:
                    dur = self.target_duration or 1.0
                j = i + 1
                while j < len(lines) and lines[j].startswith('#'):
                    j += 1
                if j < len(lines):
                    uri = lines[j]
                    absu = self._absolutize(base_dir, uri)
                    new_segments.append(Segment(uri=uri, duration=dur, abs_url=absu))
                    i = j + 1
                    continue
            i += 1

        if target_from_tag is None or target_from_tag <= 0:
            self.target_duration = max(1.0, max_seen_extinf or self.target_duration or 1.0)
        else:
            self.target_duration = target_from_tag

        added = 0
        with self._lock:
            seen_urls = {s.abs_url for s in self.segments}
            for s in new_segments:
                if s.abs_url not in seen_urls:
                    self.segments.append(s)
                    seen_urls.add(s.abs_url)
                    added += 1
        if added:
            print(f"[DVR] +{added} segments (total={len(self.segments)})")

    def render_dvr_vod_playlist(self, *, endlist: bool = False) -> Tuple[str, float]:
        with self._lock:
            segs = list(self.segments)
            init_url = self.init_url
            target = int(max(1.0, self.target_duration))
            version = self.version

        total = sum(s.duration for s in segs)

        out: List[str] = []
        out.append('#EXTM3U')
        out.append(f'#EXT-X-VERSION:{version}')
        out.append('#EXT-X-PLAYLIST-TYPE:EVENT')
        out.append('#EXT-X-INDEPENDENT-SEGMENTS')
        out.append(f'#EXT-X-TARGETDURATION:{target}')
        out.append(f'#EXT-X-MEDIA-SEQUENCE:0')

        if init_url:
            out.append(f'#EXT-X-MAP:URI="/seg?u={init_url}"')

        for s in segs:
            out.append(f'#EXTINF:{s.duration:.3f},')
            out.append(f'/seg?u={s.abs_url}')

        if endlist:
            out.append('#EXT-X-ENDLIST')

        return "\n".join(out) + "\n", float(total)


# ──────────────────────────────────────────────────────────────────────────────
# Aiohttp proxy app
# ──────────────────────────────────────────────────────────────────────────────
import socket


def is_port_in_use(port=19090, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0
class VlcWidget(QtWidgets.QFrame):
    positionChanged = QtCore.pyqtSignal(float)
    timeChanged = QtCore.pyqtSignal(int)
    ended = QtCore.pyqtSignal()      # <-- final, real signal

    def __init__(self, instance: vlc.Instance, parent=None):
        super().__init__(parent)
        self.instance = instance
        self.mediaplayer = self.instance.media_player_new()
        self.setMinimumSize(640, 360)

        # Timer that emits position/time
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

        # Attach VLC "end reached" event
        em = self.mediaplayer.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_media_end)

    def _on_media_end(self, _event):
        print("[VLC] Media end reached")
        # Emit Qt signal so IncidentPlayerVLC can react
        self.ended.emit()

    def _on_tick(self):
        if self.mediaplayer:
            try:
                pos = self.mediaplayer.get_position()
                t = self.mediaplayer.get_time()
                if pos >= 0:
                    self.positionChanged.emit(pos)
                if t >= 0:
                    self.timeChanged.emit(t)
            except Exception:
                pass

    def set_media(self, mrl: str, options: Optional[List[str]] = None):
        print(f"[VLC] set_media {mrl} opts={options or []}")
        media = self.instance.media_new(mrl)
        for opt in (options or []):
            media.add_option(opt)
        self.mediaplayer.set_media(media)

    def play(self):
        if sys.platform.startswith('linux'):
            self.mediaplayer.set_xwindow(int(self.winId()))
        elif sys.platform.startswith('win'):
            self.mediaplayer.set_hwnd(int(self.winId()))
        else:
            self.mediaplayer.set_nsobject(int(self.winId()))
        print("[VLC] play()")
        self.mediaplayer.play()

    def pause(self):
        print("[VLC] pause()")
        self.mediaplayer.pause()

    def set_position(self, pos01: float):
        p = max(0.0, min(1.0, float(pos01)))
        print(f"[VLC] set_position {p:.3f}")
        self.mediaplayer.set_position(p)

    def set_time_ms(self, t_ms: int):
        t = int(max(0, t_ms))
        print(f"[VLC] set_time {t}ms")
        self.mediaplayer.set_time(t)


class ProxyServer:
    def __init__(self, media_base: str, camera: Optional[str], incident: Optional[str],
                 token: str, refresh_ms: int, bind: str, port: int):
        self.media_base = media_base.rstrip('/')
        self.camera = camera
        self.incident = incident
        self.token = token
        self.refresh_ms = refresh_ms
        self.bind = bind
        self.port = port

        self.upstream_index: Optional[str] = None
        self.dvr: Optional[DvrState] = None
        self.resolved: bool = False

        # Dynamic lag control
        self._last_seg_404_ts: float = 0.0   # monotonic timestamp of last 404/410
        self._extra_lag_floor: int = 0       # can be bumped to 1–2 and decays over time

        self._app = web.Application()
        self._app.router.add_get('/dvr.m3u8', self.handle_dvr)
        self._app.router.add_get('/live.m3u8', self.handle_live)
        self._app.router.add_get('/seg', self.handle_seg)
        self._app.router.add_get('/', self.handle_root)
        self._app.router.add_get('/dvr_seek.m3u8', self.handle_dvr_seek)
        self._app.router.add_get("/vod", self.handle_vod)
        self._app.router.add_get("/img", self.handle_img)

        # DEBUG routes
        self._app.router.add_get('/debug/upstream', self.handle_debug_upstream)
        self._app.router.add_get('/debug/dvr', self.handle_debug_dvr)
        self._app.router.add_get('/debug/state', self.handle_debug_state)

        self._runner: Optional[web.AppRunner] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def handle_img(self, request):
        img_url = request.query.get("u")
        if not img_url:
            raise web.HTTPBadRequest(text="missing u")

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with ClientSession() as session:
                async with session.get(img_url, headers=headers, timeout=15) as resp:
                    body = await resp.read()
                    ctype = resp.headers.get("Content-Type", "image/jpeg")
                    return web.Response(
                        body=body,
                        content_type=ctype,
                        status=resp.status,
                        headers=self._nocache_headers(),
                    )
        except Exception as e:
            print(f"[HTTP] image fetch error: {e!r}")
            return web.Response(
                text=f"image fetch error: {type(e).__name__}: {e}",
                content_type="text/plain",
                status=502,
                headers=self._nocache_headers(),
            )

    # no-cache headers helper
    def _nocache_headers(self) -> dict:
        return {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }

    # quick helper so UI knows totals
    def get_durations_ms(self) -> Tuple[int, int]:
        if not self.dvr:
            return (0, 0)
        with self.dvr._lock:
            segs = list(self.dvr.segments)
            total_ms = int(sum(s.duration for s in segs) * 1000)
            edge = max(1, int(getattr(Config, "LIVE_EDGE_SEGMENTS", 3)))
            lag = max(0, int(getattr(Config, "LIVE_LAG_SEGMENTS", 0)))
            # Apply dynamic lag here too so UI stays coherent with playlist
            lag += self._current_extra_lag()
            keep = min(len(segs), max(1, edge + lag))
            last = segs[-keep:] if keep <= len(segs) else segs
            live_win_ms = int(sum(s.duration for s in last) * 1000)
        return (total_ms, live_win_ms)

    async def handle_vod(self, request):
        vod_url = request.query.get("u")
        if not vod_url:
            raise web.HTTPBadRequest(text="missing u")

        if not vod_url.startswith(("http://", "https://")):
            vod_url = f"http://{vod_url.lstrip('/')}"

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        range_hdr = request.headers.get("Range")
        if range_hdr:
            headers["Range"] = range_hdr

        try:
            async with ClientSession() as session:
                async with session.get(vod_url, headers=headers, timeout=None) as resp:
                    response_headers = {
                        "Content-Type": resp.headers.get("Content-Type", "video/mp4"),
                        "Accept-Ranges": resp.headers.get("Accept-Ranges", "bytes"),
                        **self._nocache_headers(),
                    }
                    if "Content-Length" in resp.headers:
                        response_headers["Content-Length"] = resp.headers["Content-Length"]
                    if "Content-Range" in resp.headers:
                        response_headers["Content-Range"] = resp.headers["Content-Range"]

                    print(
                        f"[HTTP] vod {resp.status} -> {vod_url} "
                        f"({resp.headers.get('Content-Length', '?')} bytes, range={range_hdr})"
                    )

                    proxy_resp = web.StreamResponse(status=resp.status, headers=response_headers)
                    await proxy_resp.prepare(request)

                    try:
                        async for chunk in resp.content.iter_chunked(8192):
                            await proxy_resp.write(chunk)
                    except (asyncio.CancelledError,
                            ConnectionResetError,
                            ClientConnectionError,
                            ClientPayloadError) as e:
                        # Harmless — VLC moved to another range
                        print(f"[HTTP] client disconnected early ({type(e).__name__}) — OK")
                    except Exception as e:
                        print(f"[HTTP] stream write error: {type(e).__name__}: {e}")
                    finally:
                        try:
                            await proxy_resp.write_eof()
                        except Exception:
                            pass

                    return proxy_resp

        except Exception as e:
            print(f"[HTTP] vod fetch error: {e!r} <- {vod_url}")
            return web.Response(
                text=f"vod fetch error: {type(e).__name__}: {e}",
                content_type="text/plain",
                status=502,
                headers=self._nocache_headers(),
            )

    # Dynamic lag amount based on recent 404s
    def _current_extra_lag(self) -> int:
        now = time.monotonic()
        extra = 0
        if self._last_seg_404_ts > 0:
            dt = now - self._last_seg_404_ts
            # immediately after a 404, be conservative with +2;
            # after 10s, ease to +1; after 30s, back to +0
            if dt < 10:
                extra = 2
            elif dt < 30:
                extra = 1
            else:
                extra = 0
        # floor in case we had repeated issues and want to hold higher lag briefly
        extra = max(extra, self._extra_lag_floor)
        # decay the floor gently
        if self._extra_lag_floor and (now - self._last_seg_404_ts) > 20:
            self._extra_lag_floor = max(0, self._extra_lag_floor - 1)
        return extra

    def _bump_extra_lag(self, floor_to: int):
        self._last_seg_404_ts = time.monotonic()
        self._extra_lag_floor = max(self._extra_lag_floor, floor_to)
        print(f"[LIVE] segment 404/410 observed → increasing effective lag (floor={self._extra_lag_floor})")

    # DEBUG HANDLERS
    async def handle_debug_upstream(self, _request: web.Request):
        if not self.upstream_index:
            return web.Response(text="(no upstream_index yet)\n", content_type="text/plain")
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        try:
            async with ClientSession() as session:
                async with session.get(self.upstream_index, headers=headers, timeout=10) as resp:
                    body = await resp.text()
                    out = [
                        f"URL: {self.upstream_index}",
                        f"HTTP {resp.status}",
                        "",
                        body
                    ]
                    print(f"[HTTP] debug_upstream {resp.status}")
                    return web.Response(
                        text="\n".join(out),
                        content_type='text/plain',
                        status=resp.status,
                        headers=self._nocache_headers(),
                    )
        except Exception as e:
            return web.Response(
                text=f"fetch error: {type(e).__name__}: {e}\n",
                content_type="text/plain",
                status=500,
                headers=self._nocache_headers(),
            )

    async def handle_debug_dvr(self, _request: web.Request):
        if not self.dvr:
            return web.Response(
                text="(no DVR yet)\n",
                content_type="text/plain",
                headers=self._nocache_headers(),
            )
        m3u8, total = self.dvr.render_dvr_vod_playlist(endlist=self.resolved)
        hdr = f"# segment_count={len(self.dvr.segments)} total_duration_seconds={total:.3f} resolved={self.resolved}\n"
        print(f"[HTTP] debug_dvr segments={len(self.dvr.segments)} total_s={total:.3f} endlist={self.resolved}")
        return web.Response(
            text=hdr + m3u8,
            content_type="text/plain",
            headers=self._nocache_headers(),
        )

    async def handle_debug_state(self, _request: web.Request):
        info = {
            "camera": self.camera,
            "incident": self.incident,
            "upstream_index": self.upstream_index,
            "have_dvr": bool(self.dvr),
            "segment_count": len(self.dvr.segments) if self.dvr else 0,
            "target_duration": getattr(self.dvr, "target_duration", None) if self.dvr else None,
            "have_init": bool(getattr(self.dvr, "init_url", None)) if self.dvr else False,
            "resolved": self.resolved,
            "extra_lag": self._current_extra_lag(),
        }
        print(f"[HTTP] state: {info}")
        return web.json_response(info, headers=self._nocache_headers())

    # URL helpers
    def _rewrite_to_media_base(self, any_hls_url: str) -> str:
        if not any_hls_url:
            return any_hls_url

        mb = urlparse(self.media_base)

        # Case 1: bare camera/incident/index.m3u8 → add /hls/ prefix
        if not any_hls_url.startswith(("http://", "https://", "/")):
            return f"{mb.scheme}://{mb.netloc}/hls/{any_hls_url.lstrip('/')}"

        # Case 2: starts with / but not // → relative path
        if any_hls_url.startswith('/') and not any_hls_url.startswith('//'):
            # Ensure it passes through /hls/ too
            path = any_hls_url.lstrip('/')
            if not path.startswith('hls/'):
                path = f"hls/{path}"
            return f"{mb.scheme}://{mb.netloc}/{path}"

        # Case 3: full URL → normalize its host to media_base
        u = urlparse(any_hls_url)
        if not u.scheme or not u.netloc:
            return f"{mb.scheme}://{mb.netloc}/{any_hls_url.lstrip('/')}"
        return urlunparse(u._replace(scheme=mb.scheme, netloc=mb.netloc))

    def _normalize_live_playlist(self, upstream_text: str, upstream_index_url: str) -> str:
        base_dir = upstream_index_url.rsplit("/", 1)[0] + "/"
        lines = [l.strip() for l in upstream_text.splitlines() if l.strip()]

        version = 6
        media_seq = 0

        segments = []
        init_map_abs = None
        max_extinf = 1.0

        i = 0
        while i < len(lines):
            l = lines[i]
            if l.startswith("#EXT-X-VERSION:"):
                try:
                    version = int(l.split(":", 1)[1])
                except Exception:
                    pass
            elif l.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                try:
                    media_seq = int(l.split(":", 1)[1])
                except Exception:
                    media_seq = 0
            elif l.startswith("#EXT-X-MAP:"):
                m = re.search(r'URI="([^"]+)"', l)
                if m:
                    init_map_abs = urljoin(base_dir, m.group(1))
            elif l.startswith("#EXTINF:"):
                try:
                    dur = float(l.split(':', 1)[1].split(',')[0])
                except Exception:
                    dur = 1.0
                max_extinf = max(max_extinf, dur)
                attached = []
                j = i + 1
                while j < len(lines) and lines[j].startswith("#"):
                    attached.append(lines[j])
                    j += 1
                if j < len(lines):
                    uri = lines[j]
                    segments.append((dur, attached, uri))
                    i = j
                else:
                    i = j
                i += 1
                continue
            i += 1

        base_edge = max(1, int(getattr(Config, "LIVE_EDGE_SEGMENTS", 3)))
        base_lag = max(0, int(getattr(Config, "LIVE_LAG_SEGMENTS", 0)))
        # Add dynamic lag derived from recent 404s
        effective_lag = base_lag + self._current_extra_lag()

        total = len(segments)
        keep = min(total, max(1, base_edge + effective_lag))
        start_index = max(0, total - keep)
        end_index = max(0, total - effective_lag)
        trimmed = segments[start_index:end_index]
        new_media_seq = media_seq + start_index

        out = [
            "#EXTM3U",
            f"#EXT-X-VERSION:{version}",
            "#EXT-X-PLAYLIST-TYPE:LIVE",
            f"#EXT-X-TARGETDURATION:{int(max(1, round(max_extinf + 0.0001)))}",
            "#EXT-X-INDEPENDENT-SEGMENTS",
            f"#EXT-X-MEDIA-SEQUENCE:{new_media_seq}",
        ]

        if init_map_abs:
            out.append(f'#EXT-X-MAP:URI="/seg?u={init_map_abs}"')

        for dur, attached_tags, uri in trimmed:
            out.append(f"#EXTINF:{dur:.3f},")
            for t in attached_tags:
                out.append(t)
            seg_abs = urljoin(base_dir, uri)
            out.append(f'/seg?u={seg_abs}')

        print(f"[LIVE] served {len(trimmed)} segs (edge={base_edge}, lag={effective_lag}, seq={new_media_seq})")
        return "\n".join(out) + "\n"

    # Source switching
    def switch_source(self, *, camera: Optional[str] = None,
                      incident: Optional[str] = None,
                      upstream_hls: Optional[str] = None):
        if camera:
            self.camera = camera
        if incident:
            self.incident = incident

        self.resolved = False
        self._last_seg_404_ts = 0.0
        self._extra_lag_floor = 0

        if upstream_hls:
            # Always normalize, even if relative like "CAM-482A/incident-123/index.m3u8"
            self.upstream_index = self._rewrite_to_media_base(upstream_hls)
        elif self.camera and self.incident:
            # Build from camera/incident if no explicit URL
            rel_path = f"{self.camera}/{self.incident}/index.m3u8"
            self.upstream_index = self._rewrite_to_media_base(rel_path)
        else:
            return

        print(f"[SRC] switch to upstream={self.upstream_index}")

        if self.dvr:
            try:
                self.dvr.stop()
            except Exception:
                pass
        self.dvr = DvrState(self.upstream_index, auth_token=self.token, refresh_ms=self.refresh_ms)

        if self._loop and self._loop.is_running():
            def _start():
                print("[SRC] starting DVR loop")
                self._loop.create_task(self.dvr.run())
            self._loop.call_soon_threadsafe(_start)

    def mark_resolved(self):
        """Mark incident as resolved: stop polling upstream,
        keep buffered segments for DVR scrubbing."""
        if self.resolved:
            return
        self.resolved = True
        if self.dvr:
            try:
                self.dvr.stop()   # stop adding more segments, keep existing
            except Exception:
                pass
        # Do NOT clear upstream_index or dvr here; DVR is still usable.
        print("[SRC] incident resolved; upstream disabled; DVR segments kept for scrubbing")

    # HTTP handlers
    async def handle_root(self, _request: web.Request):
        return web.Response(text='OK', content_type='text/plain', headers=self._nocache_headers())

    async def handle_dvr(self, _request: web.Request):
        # No global DVR playlist anymore
        return web.Response(
            text="#EXTM3U\n#EXT-X-ENDLIST\n",
            content_type='application/vnd.apple.mpegurl',
            status=410,
            headers=self._nocache_headers(),
        )

    async def handle_live(self, _request: web.Request):
        # 1. After resolve: serve a static DVR playlist from buffered segments
        if self.resolved:
            if not self.dvr or not self.dvr.segments:
                # No DVR buffer -> nothing to play
                return web.Response(
                    text="#EXTM3U\n#EXT-X-ENDLIST\n",
                    content_type="application/vnd.apple.mpegurl",
                    status=410,
                    headers=self._nocache_headers(),
                )

            m3u8_body, total = self.dvr.render_dvr_vod_playlist(endlist=True)
            print(
                f"[HTTP] live.m3u8 (resolved) serving DVR snapshot: "
                f"{len(self.dvr.segments)} segs, total={total:.3f}s"
            )
            return web.Response(
                text=m3u8_body,
                content_type="application/vnd.apple.mpegurl",
                status=200,
                headers=self._nocache_headers(),
            )

        # 2. No source yet -> nothing to serve
        if not self.upstream_index:
            return web.Response(
                text="#EXTM3U\n#EXT-X-ENDLIST\n",
                content_type="application/vnd.apple.mpegurl",
                status=410,
                headers=self._nocache_headers(),
            )

        # 3. Normal live mode (your existing logic...)
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            async with ClientSession() as session:
                async with session.get(self.upstream_index, headers=headers, timeout=10) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        print(f"[HTTP] live.m3u8 upstream {resp.status}")
                        if resp.status in (404, 410):
                            self.mark_resolved()
                            return web.Response(
                                text="#EXTM3U\n#EXT-X-ENDLIST\n",
                                content_type='application/vnd.apple.mpegurl',
                                status=410,
                                headers=self._nocache_headers(),
                            )
                        return web.Response(
                            text=f"# upstream {resp.status}\n{text}",
                            content_type='text/plain',
                            status=resp.status,
                            headers=self._nocache_headers(),
                        )
        except Exception as e:
            print(f"[HTTP] live.m3u8 fetch error: {e!r}")
            return web.Response(
                text=f"# fetch error: {type(e).__name__}: {e}\n",
                content_type='text/plain',
                status=502,
                headers=self._nocache_headers(),
            )

        text = self._normalize_live_playlist(text, self.upstream_index)
        return web.Response(
            text=text,
            content_type='application/vnd.apple.mpegurl',
            headers=self._nocache_headers(),
        )

    async def handle_seg(self, request: web.Request):
        url = request.query.get('u')
        if not url:
            raise web.HTTPBadRequest(text='missing u')
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        try:
            async with ClientSession() as session:
                async with session.get(url, headers=headers, timeout=20) as resp:
                    body = await resp.read()
                    ctype = resp.headers.get('Content-Type', 'application/octet-stream')
                    status = resp.status
                    print(f"[HTTP] seg {status} {ctype} {len(body)} bytes <- {url}")
                    # On 404/410, bump lag so subsequent /live.m3u8 hides fresher segs
                    if status in (404, 410):
                        self._bump_extra_lag(floor_to=2)
                    return web.Response(
                        body=body,
                        content_type=ctype,
                        status=status,
                        headers=self._nocache_headers(),
                    )
        except Exception as e:
            print(f"[HTTP] seg fetch error: {e!r} <- {url}")
            return web.Response(
                text=f"segment fetch error: {type(e).__name__}: {e}",
                content_type="text/plain",
                status=502,
                headers=self._nocache_headers(),
            )

    async def handle_dvr_seek(self, request: web.Request):
        # IMPORTANT: allow DVR seek even when resolved, as long as we still have a DVR buffer.
        if not self.dvr:
            return web.Response(
                text="#EXTM3U\n#EXT-X-ENDLIST\n",
                content_type='application/vnd.apple.mpegurl',
                status=410,
                headers=self._nocache_headers(),
            )

        t_ms_str = request.query.get('t', '0')
        try:
            t_ms = max(0, int(float(t_ms_str)))
        except Exception:
            t_ms = 0

        with self.dvr._lock:
            segs = list(self.dvr.segments)
            init_url = self.dvr.init_url
            version = self.dvr.version
            target = int(max(1.0, self.dvr.target_duration))

        # Compute which segment contains t_ms and how far into it we need to start.
        acc_ms = 0.0
        start_idx = 0
        intra_ms = 0.0
        for i, s in enumerate(segs):
            next_acc = acc_ms + s.duration * 1000.0
            if next_acc > t_ms:
                start_idx = i
                intra_ms = max(0.0, t_ms - acc_ms)
                break
            acc_ms = next_acc
        else:
            # Past the end → start at the last segment, no intra offset
            start_idx = max(0, len(segs) - 1)
            intra_ms = 0.0

        trimmed = segs[start_idx:]
        media_seq = start_idx

        out = []
        out.append('#EXTM3U')
        out.append(f'#EXT-X-VERSION:{version}')
        out.append('#EXT-X-PLAYLIST-TYPE:EVENT')
        out.append('#EXT-X-INDEPENDENT-SEGMENTS')
        out.append(f'#EXT-X-TARGETDURATION:{max(1, target)}')
        out.append(f'#EXT-X-MEDIA-SEQUENCE:{media_seq}')

        # PRECISE intra-segment start (many players honor this; helps VLC too)
        out.append(f'#EXT-X-START:TIME-OFFSET={intra_ms/1000.0:.3f},PRECISE=YES')

        if init_url:
            out.append(f'#EXT-X-MAP:URI="/seg?u={init_url}"')

        for s in trimmed:
            out.append(f'#EXTINF:{s.duration:.3f},')
            out.append(f'/seg?u={s.abs_url}')

        body = "\n".join(out) + "\n"
        print(
            f"[HTTP] dvr_seek.m3u8 t={t_ms}ms -> start_idx={start_idx} "
            f"intra={int(intra_ms)}ms segs={len(trimmed)} resolved={self.resolved}"
        )
        headers = self._nocache_headers() | {"X-Start-Offset-Ms": str(int(intra_ms))}
        return web.Response(
            text=body,
            content_type='application/vnd.apple.mpegurl',
            headers=headers,
        )

    # Lifecycle
    def start(self):
        def _run_loop():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            self._runner = web.AppRunner(self._app)
            loop.run_until_complete(self._runner.setup())
            site = web.TCPSite(self._runner, self.bind, self.port)
            loop.run_until_complete(site.start())
            print(f"[HTTP] proxy listening on http://{self.bind}:{self.port}")
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(self._runner.cleanup())
                loop.stop()

        # Use the configured port, not a hardcoded one
        if is_port_in_use(self.port, self.bind):
            print(f"[INFO] DVR proxy already running on port {self.port}, reusing it.")
        else:
            self._thread = threading.Thread(target=_run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        if self.dvr:
            self.dvr.stop()


# ──────────────────────────────────────────────────────────────────────────────
# LEFT PANE + UI — unchanged except: DVR seek allowed after resolve
# ──────────────────────────────────────────────────────────────────────────────
class AlertsModel(QtCore.QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._items: list[dict] = []

    def rowCount(self, parent=None):
        return len(self._items)

    def data(self, idx, role):
        if not idx.isValid():
            return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            a = self._items[idx.row()]
            status = (a.get("status") or "firing").lower()
            return f'[{status}] {a.get("camera")} {a.get("anomaly")} ({a.get("incident_id")})'
        return None

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def set_alerts(self, items: list[dict]):
        self.beginResetModel()
        self._items = list(items or [])
        self.endResetModel()

    def add_alerts(self, items):
        if not items:
            return
        start = len(self._items)
        self.beginInsertRows(QtCore.QModelIndex(), start, start + len(items) - 1)
        self._items.extend(items)
        self.endInsertRows()

    def get(self, row: int):
        return self._items[row]

    def _key(self, it: dict) -> tuple[str, str]:
        return (str(it.get("camera") or ""), str(it.get("incident_id") or ""))

    def as_dict(self) -> dict[tuple[str, str], dict]:
        return {self._key(it): it for it in self._items}

    def replace_with(self, merged: dict[tuple[str, str], dict]):
        self.set_alerts(list(merged.values()))

    def remove_by_key(self, camera: str, incident_id: str):
        k = (str(camera or ""), str(incident_id or ""))
        for i, it in enumerate(self._items):
            if (str(it.get("camera") or ""), str(it.get("incident_id") or "")) == k:
                self.beginRemoveRows(QtCore.QModelIndex(), i, i)
                self._items.pop(i)
                self.endRemoveRows()
                return True
        return False


class AlertItemDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        model: AlertsModel = index.model()  # type: ignore
        a = model.get(index.row())
        r = option.rect
        painter.save()

        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            painter.fillRect(r, QtGui.QColor("#eef8ff"))
        elif option.state & QtWidgets.QStyle.StateFlag.State_MouseOver:
            painter.fillRect(r, QtGui.QColor("#f6fafc"))

        status = (a.get("status") or "firing").lower()
        color = {"firing": "#16a34a", "resolved": "#94a3b8", "warning": "#f59e0b"}.get(status, "#16a34a")
        chip = QtCore.QRect(r.left() + 10, r.center().y() - 5, 10, 10)
        painter.setBrush(QtGui.QColor(color))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(chip)

        x = chip.right() + 10
        cam = str(a.get("camera") or "")
        anom = str(a.get("anomaly") or "")
        subject = str(a.get("subject") or "")
        if anom.lower() in ("intruding animal", "intruding_animal", "climbing_fence") and subject:
            anom = f"{anom.title()} ({subject.title()})"
        else:
            anom = anom.title()

        inc = str(a.get("incident_id") or "")[:8]

        title_font = QtGui.QFont(option.font)
        title_font.setPointSizeF(option.font.pointSizeF() + 1)
        title_font.setBold(True)
        sub_font = QtGui.QFont(option.font)
        sub_font.setPointSizeF(option.font.pointSizeF() - 1)

        painter.setPen(QtGui.QColor("#111827"))
        painter.setFont(title_font)
        painter.drawText(
            QtCore.QRect(x, r.top() + 4, r.width() - 20, 18),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            f"{cam} • {anom}",
        )

        painter.setPen(QtGui.QColor("#6b7280"))
        painter.setFont(sub_font)
        painter.drawText(
            QtCore.QRect(x, r.top() + 22, r.width() - 20, 16),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            f"Incident: {inc}…  •  Status: {status}",
        )

        painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, _index: QtCore.QModelIndex) -> QtCore.QSize:
        return QtCore.QSize(220, 42)


LEFT_LIST_QSS = """
QListView {
  padding: 6px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}
QListView::item { padding: 4px 8px; }
QListView::item:selected { background: #eef8ff; border-radius: 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 8px 2px 8px 2px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #cbd5e1; min-height: 32px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
#LeftHeader { color: #6b7280; font-weight: 600; letter-spacing: 0.4px; margin: 0 6px 6px 6px; }
"""


class SeekSlider(QtWidgets.QSlider):
    hovered = QtCore.pyqtSignal(int)
    clickedTo = QtCore.pyqtSignal(int)
    draggedTo = QtCore.pyqtSignal(int)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._press_x: Optional[float] = None
        self._moved: bool = False
        self._CLICK_EPS = 4.0
        self._EDGE_SNAP_PX = 8  # snap zone near the ends

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press_x = float(ev.position().x())
            self._moved = False
            self.setSliderDown(True)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        x = float(ev.position().x())
        if self._press_x is not None and abs(x - self._press_x) > self._CLICK_EPS:
            self._moved = True
        val = self._value_for_x(x)
        self.hovered.emit(val)
        if self._moved:
            self.setValue(val)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton and self._press_x is not None:
            x = float(ev.position().x())
            val = self._value_for_x(x)
            self.setSliderDown(False)
            self.setValue(val)
            if self._moved:
                self.draggedTo.emit(val)
            else:
                self.clickedTo.emit(val)
            self._press_x = None
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def _value_for_x(self, x: float) -> int:
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_Slider,
            opt,
            QtWidgets.QStyle.SubControl.SC_SliderGroove,
            self,
        )
        if groove.width() <= 0:
            return self.value()

        # snap to exact min/max if you're near the ends
        if x <= groove.left() + self._EDGE_SNAP_PX:
            return self.minimum()
        if x >= groove.right() - self._EDGE_SNAP_PX:
            return self.maximum()

        ratio = max(0.0, min(1.0, (x - groove.left()) / groove.width()))
        return int(self.minimum() + ratio * (self.maximum() - self.minimum()))


class VideoSurface(QtWidgets.QStackedWidget):
    def __init__(self, vlc_widget: QtWidgets.QWidget, parent=None):
        super().__init__(parent)
        self.vlcw = vlc_widget
        self.loading = QtWidgets.QLabel("Loading…")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading.setStyleSheet("color:#b9c0c7; font-size:18px;")
        self.addWidget(self.vlcw)
        self.addWidget(self.loading)
        self.setCurrentIndex(1)

    def show_loading(self, on: bool):
        self.setCurrentIndex(1 if on else 0)



class IncidentPlayerVLC(QtWidgets.QWidget):
    def __init__(self, api, alert_service, parent=None):
        super().__init__(parent)
        self.api = api
        self.alert_service = alert_service
        self.allow_autoplay = False
        self._is_current_page = False
        self.cfg = Config()
        self.proxy = ProxyServer(
            media_base=self.cfg.MEDIA_BASE,
            camera=None,
            incident=self.cfg.INCIDENT,
            token=self.cfg.TOKEN,
            refresh_ms=self.cfg.REFRESH_MS,
            bind=self.cfg.BIND,
            port=self.cfg.PORT,
        )
        self.proxy.start()
        self.setWindowTitle("AgGuard — Live Incidents")

        self.setMinimumSize(1100, 620)
        self.resize(1180, 680)
        self.setContentsMargins(6, 6, 6, 6)

        THEME_QSS = """
        QWidget { background:#fafbfc; color:#1f2937; font-size:13px; }
        QGroupBox { background:#ffffff; border:1px solid #e5e7eb; border-radius:10px; margin-top:14px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; top:-6px; padding:0 4px; color:#0f172a; font-weight:600; }
        QPushButton { border-radius:10px; padding:7px 12px; background:#10b981; color:white; font-weight:600; border:0; }
        QPushButton:hover { background:#0ea371; }
        QLabel#timeLabel { color:#6b7280; font-weight:600; }
        QLabel#liveBadge { background:#10b981; color:white; padding:3px 8px; border-radius:12px; font-weight:700; }
        QLabel#liveBadge.off { background:#9ca3af; }
        QSlider::groove:horizontal { height:8px; background:#e7f6ef; border-radius:4px; }
        QSlider::handle:horizontal { background:#10b981; width:14px; height:14px; margin:-3px 0; border-radius:7px; }
        """ + LEFT_LIST_QSS
        self.setStyleSheet(THEME_QSS)

        os.environ.setdefault("VDPAU_DRIVER", "")
        os.environ.setdefault("LIBVA_DRIVER_NAME", "")
        vlc_opts = [
            f'--network-caching={max(200, int(self.cfg.NETWORK_CACHING))}',
            '--live-caching=300',
            '--file-caching=300',
            '--no-video-title-show',
            '--quiet',
            '--aout=dummy',
            '--avcodec-hw=none',
            '--drop-late-frames',
            '--skip-frames',
            '--clock-jitter=0',
        ]
        self.vlc_instance = vlc.Instance(*vlc_opts)
        self.vlcw = VlcWidget(self.vlc_instance)
        self.videoSurface = VideoSurface(self.vlcw)
        self.videoSurface.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        # Controls
        self.btnLive = QtWidgets.QPushButton('Go Live')
        self.btnLive.setObjectName("btnLive")

        self.timeLeft = QtWidgets.QLabel('00:00')
        self.timeLeft.setObjectName("timeLabel")
        self.slider = SeekSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.liveBadge = QtWidgets.QLabel('LIVE')
        self.liveBadge.setObjectName("liveBadge")

        # LEFT PANE
        leftContainer = QtWidgets.QGroupBox("Alerts")
        leftContainer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        leftContainer.setMinimumWidth(300)
        leftContainer.setMaximumWidth(340)

        leftLayout = QtWidgets.QVBoxLayout(leftContainer)
        leftLayout.setContentsMargins(10, 10, 10, 10)
        leftLayout.setSpacing(8)

        self.alertList = QtWidgets.QListView()
        self.alertList.setMouseTracking(True)
        self.alertList.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.alertList.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems)
        self.alertList.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.alertList.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.alertList.setUniformItemSizes(True)
        self.alertList.setSpacing(4)
        self.alertList.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.alertModel = AlertsModel()
        self.alertList.setModel(self.alertModel)
        self.alertList.setItemDelegate(AlertItemDelegate(self.alertList))
        leftLayout.addWidget(self.alertList)

        # Details inside player pane
        self.detailGroup = QtWidgets.QGroupBox("Details")
        self.detailGroup.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        grid = QtWidgets.QGridLayout(self.detailGroup)
        grid.setContentsMargins(12, 8, 12, 12)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        labels = ["Camera:", "Anomaly:", "Incident ID:", "Status:", "Start Time:"]
        self.lblVals = []
        for i, title in enumerate(labels):
            k = QtWidgets.QLabel(title)
            v = QtWidgets.QLabel("–")
            v.setStyleSheet("color:#6b7280;")
            grid.addWidget(k, i, 0, 1, 1)
            grid.addWidget(v, i, 1, 1, 1)
            self.lblVals.append(v)
        self.detailGroup.setMaximumHeight(160)

        # Right stack
        self.rightStack = QtWidgets.QStackedWidget()
        self.rightStack.setContentsMargins(0, 0, 0, 0)

        self.emptyPane = QtWidgets.QWidget()
        ep_layout = QtWidgets.QVBoxLayout(self.emptyPane)
        ep_layout.setContentsMargins(10, 10, 10, 10)
        ep_layout.setSpacing(0)

        noTitle = QtWidgets.QLabel("No alerts")
        noTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        noTitle.setStyleSheet("font-size:22px; font-weight:800; color:#111827;")

        noSub = QtWidgets.QLabel("Alerts will appear here.")
        noSub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        noSub.setWordWrap(True)
        noSub.setStyleSheet("color:#6b7280;")

        ep_layout.addStretch(1)
        ep_layout.addWidget(noTitle)
        ep_layout.addWidget(noSub)
        ep_layout.addStretch(3)

        self.playerPane = QtWidgets.QGroupBox("")
        rightLayout = QtWidgets.QVBoxLayout(self.playerPane)
        rightLayout.setContentsMargins(10, 10, 10, 10)
        rightLayout.setSpacing(10)

        titleRow = QtWidgets.QHBoxLayout()
        titleRow.setContentsMargins(0, 0, 0, 0)
        titleRow.setSpacing(10)
        title = QtWidgets.QLabel("AgGuard — Security Alerts")
        title.setStyleSheet("font-size:20px; font-weight:800; color:#111827;")
        dotLive = QtWidgets.QLabel("• LIVE")
        dotLive.setStyleSheet("color:#10b981; font-weight:700;")
        titleRow.addWidget(title)
        titleRow.addStretch(1)
        titleRow.addWidget(dotLive)

        ctrls = QtWidgets.QHBoxLayout()
        ctrls.setContentsMargins(0, 0, 0, 0)
        ctrls.setSpacing(10)
        ctrls.addWidget(self.btnLive)
        ctrls.addSpacing(10)
        ctrls.addWidget(self.timeLeft)
        ctrls.addSpacing(8)
        ctrls.addWidget(self.slider, 1)
        ctrls.addSpacing(8)
        ctrls.addWidget(self.liveBadge)

        rightLayout.addLayout(titleRow, 0)
        rightLayout.addWidget(self.videoSurface, 1)
        rightLayout.addLayout(ctrls, 0)
        rightLayout.addWidget(self.detailGroup, 0)

        self.rightStack.addWidget(self.emptyPane)
        self.rightStack.addWidget(self.playerPane)
        self.rightStack.setCurrentIndex(0)

        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.addWidget(leftContainer)
        splitter.addWidget(self.rightStack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 900])

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # Live page only; history/analytics in external navigation
        livePage = QtWidgets.QWidget()
        liveLayout = QtWidgets.QVBoxLayout(livePage)
        liveLayout.setContentsMargins(0, 0, 0, 0)
        liveLayout.setSpacing(0)
        liveLayout.addWidget(splitter)

        outer.addWidget(livePage)

        # State
        self.mode_live = False
        self.dvr_duration_ms = 0
        self._dragging = False
        self.current_camera: Optional[str] = None
        self.current_incident: Optional[str] = None
        self.current_status: str = "firing"
        self.current_alert: Optional[dict] = None


        self._last_abs_t_ms: int = 0
        self._playlist_offset_ms: int = 0

        self._ui_freeze_deadline: float = 0.0
        self._seek_guard_deadline: float = 0.0

        self._live_sync = QTimer(self)
        self._live_sync.setInterval(800)
        self._live_sync.timeout.connect(self._maybe_sync_live_timeline)

        # grows DVR slider while paused/seeked
        self._dvr_growth = QTimer(self)
        self._dvr_growth.setInterval(1200)
        self._dvr_growth.timeout.connect(self._maybe_grow_dvr_range_only)

        # --- Subscribe to alert service ---
        self.alert_service.alertsUpdated.connect(self._on_alerts_updated)
        self.alert_service.alertAdded.connect(self._on_alert_added)
        self.alert_service.alertRemoved.connect(self._on_alert_removed)

        # Trigger initial load
        if not self.alert_service.alerts:
            print("[IncidentPlayer] No cached alerts yet — calling load_initial()")
            self.alert_service.load_initial()
        else:
            print("[IncidentPlayer] Using cached alerts:", len(self.alert_service.alerts))
            self._on_alerts_updated(self.alert_service.alerts)

        # Connections
        self.btnLive.clicked.connect(self._go_live)
        self.slider.hovered.connect(self._on_slider_hover)
        self.slider.clickedTo.connect(self._on_slider_clicked)
        self.slider.draggedTo.connect(self._on_slider_drag_released)
        self.vlcw.positionChanged.connect(self._on_vlc_pos)
        self.vlcw.timeChanged.connect(self._on_vlc_time)
        self.vlcw.ended.connect(self._on_vlc_end) 
        self.alertList.clicked.connect(self._on_pick_alert_from_list)

        self._show_player(False)
        self._set_idle()
    def _on_vlc_end(self):
        print("[VLC] end reached (proxy.resolved=%s, alerts_empty=%s)"
            % (self.proxy.resolved, self.alertModel.is_empty()))

        # If incident is resolved and there are no *firing* alerts left,
        # we can fully tear down the player and hide the panels.
        if self.proxy.resolved:
            have_firing = any(
                (a.get("status") or "firing").lower() == "firing"
                for a in self.alertModel._items
            )

            if not have_firing:
                # Stop VLC
                try:
                    self.vlcw.mediaplayer.stop()
                except Exception:
                    pass

                # Optionally drop the current resolved incident from the list,
                # so the left list is also "clean".
                if self.current_camera and self.current_incident:
                    self.alertModel.remove_by_key(self.current_camera,
                                                self.current_incident)

                # Clear current state
                self.current_camera = None
                self.current_incident = None
                self.current_alert = None
                self.dvr_duration_ms = 0

                # Reset UI + hide player
                self._set_idle()
                self._show_player(False)   # switch to NO-ALERTS pane
                print("[MODE] DVR clip finished; no firing alerts → hiding player")
                return

        # Case 2: still have firing alerts or proxy not resolved — normal DVR mode
        self.mode_live = False
        self._set_live_badge(False)
        print("[MODE] clip finished; staying in DVR mode")



    def showEvent(self, event):
        super().showEvent(event)

        if not self.isVisible():
            return

        if not self._is_current_page:
            self._is_current_page = True
            self.allow_autoplay = True
            print("[IncidentPlayer] Activated (autoplay enabled)")

            # Restore video surface
            self.videoSurface.show()

            # If alerts exist, auto-play the first one
            if self.alertModel._items:
                self._show_player(True)
                self._play_alert(self.alertModel._items[0])

    def hideEvent(self, event):
        super().hideEvent(event)

        if self._is_current_page:
            self._is_current_page = False
            self.allow_autoplay = False
            print("[IncidentPlayer] Deactivated (autoplay disabled)")

            # Stop VLC safely
            try:
                self.vlcw.mediaplayer.stop()
            except Exception:
                pass

            # Hide video surface to stop painting
            self.videoSurface.hide()

            self._set_idle()

    def _on_alerts_updated(self, alerts: list):
        """Called when AlertService emits full list (on initial load)."""
        print(f"[AlertService] Full update: {len(alerts)} alerts")
        self._apply_firing_list(alerts)

    def _on_alert_added(self, alert: dict):
        """Called when a new alert arrives in real-time."""
        print(f"[AlertService] New alert added: {alert.get('alert_id')}")
        self._merge_firing_deltas([alert])

    def _on_alert_removed(self, alert_id: str):
        print(f"[AlertService] Alert removed: {alert_id}")

        is_current = (self.current_incident == alert_id)

        new_items: list[dict] = []
        for a in self.alertModel._items:
            if a.get("incident_id") != alert_id:
                new_items.append(a)
            else:
                # This is the removed alert
                if is_current and self.proxy.dvr and len(self.proxy.dvr.segments) > 0:
                    updated = dict(a)
                    updated["status"] = "resolved"
                    new_items.append(updated)
                # else: drop it completely

        self.alertModel.set_alerts(new_items)

        if is_current:
            self.current_status = "resolved"
            # Update cached alert metadata if we still have it
            self.current_alert = next(
                (a for a in new_items if a.get("incident_id") == alert_id),
                self.current_alert,
            )
            try:
                self.proxy.mark_resolved()
            except Exception as e:
                print(f"[IncidentPlayer] mark_resolved failed: {e!r}")

            # UI: DVR-only mode
            self.mode_live = False
            self._set_live_badge(False)

        self._update_right_pane_visibility()



    def _fetch_active_alerts_from_db(self):
        """Fetch current active alerts directly from the DB API."""
        try:
            print("[DB] Fetching active alerts from dashboard API...")
            url = f"{self.api.base}/api/tables/alerts"
            resp = self.api.http.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"[DB] Failed to fetch alerts: {resp.status_code}")
                return []

            data = resp.json()
            alerts = data.get("rows", data) if isinstance(data, dict) else data
            print(f"[DB] Loaded {len(alerts)} active alerts from DB.")
            return alerts
        except Exception as e:
            print(f"[DB] Error fetching alerts: {e}")
            return []

    # ───── NO-ALERTS helpers ─────
    def _show_player(self, on: bool):
        self.rightStack.setCurrentIndex(1 if on else 0)
        print(f"[UI] right pane -> {'PLAYER' if on else 'NO-ALERTS'}")

    def _update_right_pane_visibility(self):
        have_any_list = not self.alertModel.is_empty()

        # We also keep the player visible if we have a "current" incident
        # (even if it is resolved) and we still have a DVR buffer to scrub.
        have_current_dvr = (
            self.current_camera is not None
            and self.current_incident is not None
            and self.proxy.dvr is not None
            and len(self.proxy.dvr.segments) > 0
        )

        print(
            "_update_right_pane_visibility called: "
            f"have_any_list={have_any_list}, have_current_dvr={have_current_dvr}"
        )

        if not have_any_list and not have_current_dvr:
            # Nothing in the list and nothing to scrub → fully idle.
            try:
                self.vlcw.mediaplayer.stop()
            except Exception:
                pass
            self._set_idle()
            self._show_player(False)
        else:
            # Either we have firing alerts or a resolved incident with DVR buffer.
            self._show_player(True)


    # ───── alerts helpers ─────
    def _key(self, it: dict) -> tuple[str, str]:
        return (str(it.get('camera') or ''), str(it.get('incident_id') or ''))

    def _normalize_alert(self, it: dict) -> dict:
        meta = it.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        ended = (
            it.get("ended_at") or
            it.get("endsAt") or
            it.get("endedAt")
        )
        return {
            "camera": it.get("device_id") or it.get("camera"),
            "incident_id": it.get("alert_id") or it.get("incident_id"),
            "anomaly": it.get("alert_type") or it.get("anomaly"),
            "subject": it.get("subject") or meta.get("subject"),
            "hls": it.get("hls"),
            "vod": it.get("vod"),
            "image_url": it.get("image_url"),
            "summary": it.get("summary"),
            "severity": it.get("severity"),
            "started_at": it.get("started_at") or it.get("startsAt"),
            "ended_at": ended,
            "status": "resolved" if ended else "firing",
        }

    # Only expand DVR while paused/seeked (DVR mode). Never move the thumb.
    def _maybe_grow_dvr_range_only(self):
        if self.mode_live:
            self._dvr_growth.stop()
            return
        if self.proxy.dvr and not self.proxy.resolved:
            _, total = self.proxy.dvr.render_dvr_vod_playlist()
            new_max = int(total * 1000)
            if new_max > self.dvr_duration_ms:
                self.dvr_duration_ms = new_max
                self.slider.setRange(0, self.dvr_duration_ms)

    def _apply_firing_list(self, firing: list[dict]):
        firing = [self._normalize_alert(it) for it in (firing or []) if it]

        # only keep desired alert types that are still firing
        firing = [
            it for it in firing
            if (it.get("status") or "firing").lower() == "firing"
            and (it.get("anomaly") or "").lower() in self.cfg.ALLOWED_TYPES
        ]

        # Track currently selected item (optional; same as before)
        sel = self.alertList.selectionModel().currentIndex() if self.alertList.selectionModel() else QtCore.QModelIndex()
        selected_inc = selected_cam = None
        if sel.isValid():
            try:
                cur = self.alertModel.get(sel.row())
                selected_inc = cur.get('incident_id')
                selected_cam = cur.get('camera')
            except Exception:
                pass

        cur_cam = self.current_camera
        cur_inc = self.current_incident or self.cfg.INCIDENT
        has_current = bool(cur_cam and cur_inc)

        still_there = any(
            it.get('camera') == cur_cam and
            (it.get('incident_id') or it.get('alert_id')) == cur_inc
            for it in firing
        ) if has_current else False

        effective_list = list(firing)

        # Case: the current incident is no longer "firing" in the upstream list → resolved
        if has_current and not still_there:
            self.current_status = "resolved"
            try:
                self.proxy.mark_resolved()
            except Exception as e:
                print(f"[IncidentPlayer] mark_resolved failed in _apply_firing_list: {e!r}")

            # Keep it in the left list while we still have DVR segments
            if self.proxy.dvr is not None and len(self.proxy.dvr.segments) > 0:
                base = dict(self.current_alert or {})
                base.setdefault("camera", cur_cam)
                base.setdefault("incident_id", cur_inc)
                base["status"] = "resolved"
                if (base.get("anomaly") or "").lower() in self.cfg.ALLOWED_TYPES:
                    key = (base.get("camera"), base.get("incident_id"))
                    if not any(
                        it.get("camera") == key[0] and it.get("incident_id") == key[1]
                        for it in effective_list
                    ):
                        effective_list.append(base)

            self.alertModel.set_alerts(effective_list)
            self._update_right_pane_visibility()
            return

        # Normal case: just "firing" alerts + (possibly) already kept resolved ones
        self.alertModel.set_alerts(effective_list)
        self._update_right_pane_visibility()

        # Autoplay only when there was NO current incident at all (e.g., first load)
        if firing and not has_current:
            if self.allow_autoplay:
                self._show_player(True)
                self._play_alert(firing[0])
            else:
                print("[IncidentPlayer] Ignored new alert (page not visible)")


    def _merge_firing_deltas(self, deltas: list[dict]):
        current = self.alertModel.as_dict()
        changed = False

        for raw in (deltas or []):
            it = self._normalize_alert(raw)
            if (it.get("anomaly") or "").lower() not in self.cfg.ALLOWED_TYPES:
                continue  # skip other alert types

            k = self._key(it)
            status = (it.get("status") or "firing").lower()

            if status == 'firing':
                if current.get(k) != it:
                    current[k] = it
                    changed = True
            else:
                # resolved / non-firing
                keep_on_left = (
                    (self.current_camera, self.current_incident) == k
                    and self.proxy.dvr is not None
                    and len(self.proxy.dvr.segments) > 0
                )
                if keep_on_left:
                    stored = dict(current.get(k, it))
                    stored.update(it)
                    stored["status"] = "resolved"
                    current[k] = stored
                    changed = True
                else:
                    if k in current:
                        current.pop(k, None)
                        changed = True

            if (self.current_camera, self.current_incident) == k and status != 'firing':
                # Current incident resolved: stop polling upstream,
                # but keep DVR and keep it in the list so UI doesn't "blink out".
                self.current_status = "resolved"
                self.current_alert = it
                self.proxy.mark_resolved()
                print("[IncidentPlayer] Current incident resolved via delta; DVR-only mode")
                # Do NOT remove from model and do NOT stop the mediaplayer here.

        if not changed:
            return

        # Same selection-restore logic as before
        sel = self.alertList.selectionModel().currentIndex() if self.alertList.selectionModel() else QtCore.QModelIndex()
        selected_key = None
        if sel.isValid():
            try:
                cur = self.alertModel.get(sel.row())
                selected_key = self._key(cur)
            except Exception:
                selected_key = None

        self.alertModel.replace_with(current)

        cur_cam = self.current_camera
        cur_inc = self.current_incident or self.cfg.INCIDENT
        has_current = (cur_cam and cur_inc and (cur_cam, cur_inc) in current)

        # Restore selection for any remaining alert (same as before)
        if self.alertList.selectionModel() and self.alertList.selectionModel().currentIndex().isValid():
            selected_key = None
            try:
                cur = self.alertModel.get(self.alertList.selectionModel().currentIndex().row())
                selected_key = self._key(cur)
            except Exception:
                selected_key = None

            if selected_key:
                items = list(current.values())
                for row, it in enumerate(items):
                    if self._key(it) == selected_key:
                        idx = self.alertModel.index(row, 0)
                        self.alertList.selectionModel().select(
                            idx, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                        )
                        self.alertList.setCurrentIndex(idx)
                        break

        # Now decide visibility using the helper (which also checks DVR)
        self._update_right_pane_visibility()

        if not has_current:
            items = list(current.values())
            if items:
                if self.allow_autoplay:
                    self._show_player(True)
                    self._play_alert(items[0])
                else:
                    print("[IncidentPlayer] Ignored alert (page not visible)")
            else:
                try:
                    self.vlcw.mediaplayer.stop()
                except Exception:
                    pass
                self._set_idle()
                self._show_player(False)



    # ───── helpers ─────
    def _freeze_ui(self, seconds: float = 0.8):
        self._ui_freeze_deadline = time.monotonic() + max(0.1, seconds)

    def _maybe_sync_live_timeline(self):
        if not self.mode_live:
            self._live_sync.stop()
            return

        total_ms, live_win_ms = self.proxy.get_durations_ms()
        if total_ms <= 0 or live_win_ms <= 0:
            return

        target_offset = max(0, total_ms - live_win_ms)
        t_rel = self.vlcw.mediaplayer.get_time()
        if t_rel < 0:
            t_rel = 0
        abs_t = min(target_offset + t_rel, total_ms)

        changed = (self.dvr_duration_ms != total_ms) or (abs(self._playlist_offset_ms - target_offset) > 250)
        if changed:
            self.dvr_duration_ms = total_ms
            self._playlist_offset_ms = target_offset

            self.slider.setRange(0, total_ms)
            self.slider.blockSignals(True)
            self.slider.setValue(abs_t)
            self.slider.blockSignals(False)

            self._last_abs_t_ms = abs_t
            self._update_time_label(abs_t)

    # List click → play
    def _on_pick_alert_from_list(self, idx: QtCore.QModelIndex):
        if not idx.isValid():
            return
        it = self.alertModel.get(idx.row())
        print(f"[UI] picked alert: {it}")
        self._show_player(True)
        self._play_alert(it)

    def _play_alert(self, it: dict):
        # Remember the previous "current" before we switch
        old_cam = self.current_camera
        old_inc = self.current_incident
        old_status = getattr(self, "current_status", "firing")

        # Normalize to ensure keys like 'camera', 'anomaly', 'incident_id', 'started_at' exist
        it = self._normalize_alert(it)

        cam = it.get('camera')
        inc = it.get('incident_id') or self.cfg.INCIDENT
        hls_url = it.get('hls') or None

        # If we are leaving a resolved incident that we were keeping only
        # for DVR scrubbing, remove it from the list now (no video anymore).
        if old_cam and old_inc and old_status == "resolved":
            self.alertModel.remove_by_key(old_cam, old_inc)

        self.current_camera = cam
        self.current_incident = inc
        self.current_status = (it.get('status') or 'firing').lower()
        self.current_alert = it  # keep the latest metadata for this incident

        self.proxy.switch_source(camera=cam, incident=inc, upstream_hls=hls_url)
        self.setWindowTitle("AgGuard — Live Incidents")
        self._update_details(it)
        self.videoSurface.show_loading(True)

        QtCore.QTimer.singleShot(150, self._go_live)


    def _update_details(self, it: dict):
        subject = it.get("subject")
        anom = it.get("anomaly") or "–"
        if anom.lower() in ("intruding animal", "intruding_animal", "climbing_fence") and subject:
            anom = f"{anom.title()} ({subject.title()})"

        vals = [
            it.get('camera') or '–',
            anom,
            it.get('incident_id') or '–',
            (it.get('status') or self.current_status or '–'),
            it.get('started_at') or '–',
        ]
        for lbl, v in zip(self.lblVals, vals):
            lbl.setText(v)

    # ───── slider / playback helpers ─────
    def _fmt(self, ms: int) -> str:
        s = max(0, ms // 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if h:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:d}:{s:02d}"

    def _set_live_badge(self, live: bool):
        if live:
            self.liveBadge.setText("LIVE")
            self.liveBadge.setStyleSheet(
                "background:#10b981; color:white; padding:3px 8px; "
                "border-radius:12px; font-weight:700;"
            )
        else:
            self.liveBadge.setText("DVR")
            self.liveBadge.setStyleSheet(
                "background:#9ca3af; color:white; padding:3px 8px; "
                "border-radius:12px; font-weight:700;"
            )

    def _set_idle(self):
        self.mode_live = False
        self._set_live_badge(False)
        self.dvr_duration_ms = 0
        self._last_abs_t_ms = 0
        self._playlist_offset_ms = 0
        self.timeLeft.setText("00:00")
        self.videoSurface.show_loading(True)
        for v in self.lblVals:
            v.setText("–")
        print("[MODE] IDLE")

    def _go_live(self):
        # If the proxy is already resolved, there is no live stream any more.
        # We keep DVR scrubbing only – do not try to attach /live.m3u8.
        if self.proxy.resolved:
            print("[MODE] proxy resolved; live disabled, staying in DVR-only mode")
            self.mode_live = False
            self._set_live_badge(False)
            return

        # resume live sync; stop DVR growth
        if not self._live_sync.isActive():
            self._live_sync.start()
        self._dvr_growth.stop()

        # ❌ OLD: blocked when current_status == "resolved"
        # if self.current_status == "resolved":
        #     print("[MODE] resolved; not going live")
        #     self._set_idle()
        #     return

        if not self.proxy.upstream_index:
            return

        total_ms, live_win_ms = self.proxy.get_durations_ms()
        self.dvr_duration_ms = max(self.dvr_duration_ms, total_ms)
        self._playlist_offset_ms = max(0, total_ms - live_win_ms)

        self.mode_live = True
        self._set_live_badge(True)
        self.videoSurface.show_loading(True)

        self._freeze_ui(1.0)
        self._update_time_label(self.dvr_duration_ms)

        live_url = f"http://{self.cfg.BIND}:{self.cfg.PORT}/live.m3u8"

        try:
            self.vlcw.mediaplayer.stop()
        except Exception:
            pass

        live_edge_total = max(2, int(self.cfg.LIVE_EDGE_SEGMENTS) + int(self.cfg.LIVE_LAG_SEGMENTS))
        self.vlcw.set_media(
            live_url,
            options=[
                "--demux=hls",
                ":no-audio",
                ":http-reconnect=true",
                ":hls-keep-live-session",
                f":hls-live-edge={min(3, max(2, live_edge_total))}",
                ":hls-segment-threads=2",
                f":network-caching={max(200, int(self.cfg.NETWORK_CACHING))}",
            ],
        )
        self.vlcw.play()
        self._live_sync.start()

        self.slider.setEnabled(True)
        self.slider.setRange(0, self.dvr_duration_ms)
        self.slider.blockSignals(True)
        self.slider.setValue(self.dvr_duration_ms)
        self.slider.blockSignals(False)

        QtCore.QTimer.singleShot(300, lambda: self.videoSurface.show_loading(False))
        print(f"[MODE] LIVE offset={self._playlist_offset_ms}ms total={self.dvr_duration_ms}ms")

    def _load_dvr(self):
        print("[DVR] _load_dvr called but DVR freeze is disabled.")
        self._set_idle()

    def _on_slider_clicked(self, value: int):
        print(f"[SEEK] click -> {value}ms (mode_live={self.mode_live})")
        self._freeze_ui(0.8)
        if self.mode_live:
            self.mode_live = False
            self._set_live_badge(False)
        self._seek_via_playlist(value)

    def _on_slider_drag_released(self, value: int):
        print(f"[SEEK] drag-release -> {value}ms (mode_live={self.mode_live})")
        self._freeze_ui(0.8)
        if self.mode_live:
            self.mode_live = False
            self._set_live_badge(False)
        self._seek_via_playlist(value)

    def _seek_via_playlist(self, t_ms: int):
        # kill live sync right away so it cannot pull the thumb toward live
        self._live_sync.stop()
        if not self._dvr_growth.isActive():
            self._dvr_growth.start()

        # IMPORTANT: allow seeking even when current_status == "resolved".
        # Only block if there is no DVR.
        if not self.proxy.dvr:
            print("[SEEK] ignored (no DVR)")
            return

        t_ms = max(0, min(int(t_ms), max(0, self.dvr_duration_ms)))
        seek_url = f"http://{self.cfg.BIND}:{self.cfg.PORT}/dvr_seek.m3u8?t={t_ms}"
        print(f"[SEEK] switching media to seek playlist: {seek_url}")
        try:
            self.vlcw.mediaplayer.stop()
        except Exception:
            pass

        self._playlist_offset_ms = t_ms

        if self.slider.maximum() < max(self.dvr_duration_ms, t_ms):
            self.slider.setRange(0, max(self.dvr_duration_ms, t_ms))

        self.vlcw.set_media(seek_url, options=["--demux=hls", ":no-audio"])
        self.vlcw.play()
        self.mode_live = False
        self._set_live_badge(False)

        self._update_time_label(t_ms)
        self.slider.blockSignals(True)
        self.slider.setValue(t_ms)
        self.slider.blockSignals(False)

        self._last_abs_t_ms = t_ms
        self._seek_guard_deadline = time.monotonic() + 2.0

        QTimer.singleShot(700, lambda: setattr(self, "_ui_freeze_deadline", 0.0))

    def _on_slider_hover(self, value: int):
        if self.dvr_duration_ms > 0:
            self._update_time_label(int(value))

    def _on_vlc_pos(self, _pos01: float):
        pass

    def _on_vlc_time(self, t_ms: int):
        if t_ms < 0:
            return
        if time.monotonic() < self._ui_freeze_deadline:
            return

        absolute_ms = self._playlist_offset_ms + t_ms

        now = time.monotonic()
        if absolute_ms < self._last_abs_t_ms:
            if now < self._seek_guard_deadline:
                self._last_abs_t_ms = absolute_ms
            else:
                absolute_ms = self._last_abs_t_ms
        else:
            self._last_abs_t_ms = absolute_ms

        self._update_time_label(absolute_ms)

        if self.dvr_duration_ms > 0:
            self.slider.blockSignals(True)
            self.slider.setValue(min(absolute_ms, self.dvr_duration_ms))
            self.slider.blockSignals(False)

        if self.proxy.dvr and not self.proxy.resolved and (int(time.time()) % 2 == 0):
            _, total = self.proxy.dvr.render_dvr_vod_playlist()
            new_dur = int(total * 1000)
            if new_dur > self.dvr_duration_ms:
                self.dvr_duration_ms = new_dur
                self.slider.setRange(0, self.dvr_duration_ms)

    def _update_time_label(self, t_ms: int):
        s = max(0, t_ms // 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        txt = f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
        self.timeLeft.setText(txt)

    def closeEvent(self, event: QtGui.QCloseEvent):
        try:
            self.proxy.stop()
        except Exception:
            pass
        super().closeEvent(event)
