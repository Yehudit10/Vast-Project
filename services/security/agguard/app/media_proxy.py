# agguard/app/media_proxy.py
from __future__ import annotations
import os, re, mimetypes
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from botocore.exceptions import ClientError
from fastapi.responses import Response, StreamingResponse
import yaml

from agguard.adapters.s3_client import S3Client, S3Config

app = FastAPI(title="AgGuard Media Proxy", version="1.0")

# ---------- load config ----------
CFG_PATH = os.getenv("AGGUARD_CFG", "/app/configs/default.yaml")
with open(CFG_PATH, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f) or {}

_s3cfg = _cfg.get("s3", {}) or {}
_vcfg  = _cfg.get("video", {}) or {}
BUCKET = _vcfg.get("bucket")
PREFIX = (_vcfg.get("prefix") or "security/incidents").strip("/")

if not BUCKET:
    raise RuntimeError("video.bucket is not configured in your YAML (configs/default.yaml)")

s3 = S3Client(S3Config(
    region_name=_s3cfg.get("region_name", "us-east-1"),
    aws_access_key_id=_s3cfg.get("aws_access_key_id"),
    aws_secret_access_key=_s3cfg.get("aws_secret_access_key"),
    aws_session_token=_s3cfg.get("aws_session_token"),
    endpoint_url=_s3cfg.get("endpoint_url"),
    connect_timeout=float(_s3cfg.get("connect_timeout", 3.0)),
    read_timeout=float(_s3cfg.get("read_timeout", 10.0)),
    max_attempts=int(_s3cfg.get("max_attempts", 3)),
))

MEDIA_AUTH_TOKEN = os.getenv("MEDIA_AUTH_TOKEN") or _cfg.get("media_auth_token")  # optional

_M3U8_CT = "application/vnd.apple.mpegurl"
_TS_CT   = "video/MP2T"
_MP4_CT  = "video/mp4"

SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")  # prevent path traversal

def _require_auth(req: Request) -> None:
    """Simple Bearer check. If MEDIA_AUTH_TOKEN unset, auth is disabled (dev)."""
    print("in")
    if not MEDIA_AUTH_TOKEN:
        return
    auth = req.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    else:
        token = None
    if token != MEDIA_AUTH_TOKEN:
        print("unauthorazied")
        raise HTTPException(status_code=401, detail="Unauthorized")

def _ct_for_name(name: str) -> str:
    if name.endswith(".m3u8"): return _M3U8_CT
    if name.endswith(".ts"):   return _TS_CT
    if name.endswith(".mp4"):  return _MP4_CT
    if name.endswith(".m4s"):  return _MP4_CT
    return mimetypes.guess_type(name)[0] or "application/octet-stream"

def _object_key_for_hls(camera: str, incident: str, name: str) -> str:
    # e.g., security/incidents/<camera>/<incident>/segment_00001.ts
    return f"{PREFIX}/{camera}/{incident}/{name}"




import time
from botocore.exceptions import ClientError

def _exists(bucket: str, key: str) -> bool:
    try:
        s3.head_object(bucket, key)  # implement head_object in your S3Client
        return True
    except Exception:
        return False

def _wait_for_key(bucket: str, key: str, timeout=3.0, interval=0.2) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _exists(bucket, key):
            return True
        time.sleep(interval)
    return False

@app.get("/hls/{camera}/{incident}/index.m3u8")
def get_playlist(camera: str, incident: str, request: Request):
    _require_auth(request)
    names = ["index.m3u8", "master.m3u8", "playlist.m3u8"]
    for name in names:
        key = _object_key_for_hls(camera, incident, name)
        print("key: ",key)
        if True:#_wait_for_key(BUCKET, key, timeout=8.0, interval=0.2):
            # print(key)
            obj = s3.get_object_stream(BUCKET, key)
            body = obj["Body"].read()
            return Response(
                content=body,
                media_type=_M3U8_CT,
                headers={
                    "Cache-Control": "no-store, must-revalidate",
                    "Pragma": "no-cache",
                },
            )
    raise HTTPException(status_code=404, detail="playlist not found (not ready)")

# ---------- SEGMENTS (and CMAF init.mp4) ----------
@app.get("/hls/{camera}/{incident}/{name}")
def get_segment(camera: str, incident: str, name: str, request: Request, range: Optional[str] = Header(default=None)):
    _require_auth(request)
    if "/" in name or ".." in name or not SAFE_NAME.match(name):
        raise HTTPException(status_code=400, detail="bad segment name")
    key = _object_key_for_hls(camera, incident, name)
    try:
        obj = s3.get_object_stream(BUCKET, key, range_header=range)
    except Exception:
        raise HTTPException(status_code=404, detail="segment not found")

    headers = {"Accept-Ranges": "bytes", "Content-Type": _ct_for_name(name)}
    status = 200
    cr = obj.get("ContentRange") or obj.get("Content-Range")
    if cr:
        headers["Content-Range"] = cr
        status = 206
    return StreamingResponse(obj["Body"].iter_chunks(), headers=headers, status_code=status, media_type=headers["Content-Type"])
# ---------- FINAL MP4 (VOD) ----------
@app.get("/vod/{camera}/{incident}/final.mp4")
def get_final_mp4(
    camera: str,
    incident: str,
    request: Request,
    range: Optional[str] = Header(default=None)
):
    _require_auth(request)
    key = _object_key_for_hls(camera, incident, "final.mp4")

   

    try:
        obj = s3.get_object_stream(BUCKET, key, range_header=range)

    except ClientError as e:
        code = e.response["Error"]["Code"]

        # File NOT found → real 404
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="VOD not found")

        # VLC requests ranges beyond file end → MUST return 416, NOT 404
        if code == "InvalidRange":
            raise HTTPException(status_code=416, detail="Invalid Range")

        # Any other S3 problem is a server issue
        raise HTTPException(status_code=502, detail=f"S3 error: {code}")

    # Non-S3 exceptions (timeout, disconnect, etc.)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Internal proxy error: {type(e).__name__}")


    body = obj["Body"]
    content_length = obj.get("ContentLength")
    content_range = obj.get("ContentRange") or obj.get("Content-Range")

    headers = {
    "Accept-Ranges": "bytes",
    "Content-Type": _MP4_CT,
    }

    # Important for VLC
    if "ContentLength" in obj:
        headers["Content-Length"] = str(obj["ContentLength"])


    status = 200
    if content_range:
        headers["Content-Range"] = content_range
        status = 206
    if content_length and status == 200:
        headers["Content-Length"] = str(content_length)

    # --- SAFE STREAMING GENERATOR ---
    def stream_body():
        try:
            while True:
                chunk = body.read(256 * 1024)

                # S3 can return b'' BEFORE true EOF → retry once
                if chunk == b"":
                    more = body.read(256 * 1024)
                    if more == b"":
                        break
                    yield more
                    continue

                if not chunk:
                    break

                yield chunk

        except Exception as e:
            print("[MEDIA_PROXY][STREAM ERROR]", e)

    return StreamingResponse(
        stream_body(),
        headers=headers,
        status_code=status,
        media_type=_MP4_CT,
    )

@app.get("/img/{camera}/{incident}/{filename}")
def get_image(camera: str, incident: str, filename: str, request: Request):
    _require_auth(request)
    if "/" in filename or ".." in filename or not SAFE_NAME.match(filename):
        raise HTTPException(status_code=400, detail="bad filename")

    key = f"{PREFIX}/{camera}/{incident}/{filename}"
    try:
        obj = s3.get_object_stream(BUCKET, key)
    except Exception:
        raise HTTPException(status_code=404, detail="image not found")

    mime = _ct_for_name(filename)
    headers = {"Cache-Control": "no-store, must-revalidate"}
    return StreamingResponse(obj["Body"].iter_chunks(), headers=headers, media_type=mime)

