import os
import re
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Status Saver API",
    version="2.0.0"
)


# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class VideoRequest(BaseModel):
    url: str


# --------------------------------------------------
# PLATFORM DETECTION
# --------------------------------------------------

def detect_platform(url: str):

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return "invalid"

        hostname = parsed.netloc.lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        if hostname == "instagram.com" or hostname.endswith(".instagram.com"):
            return "instagram"

        if hostname == "facebook.com" or hostname.endswith(".facebook.com"):
            return "facebook"

        if hostname == "fb.watch":
            return "facebook"

        if hostname == "pin.it":
            return "pinterest"

        if hostname == "pinterest.com" or hostname.endswith(".pinterest.com"):
            return "pinterest"

        return "unsupported"

    except Exception:
        return "invalid"


# --------------------------------------------------
# BASIC URL CLEANING
# --------------------------------------------------

def clean_url(url: str) -> str:

    url = url.strip()

    # Remove surrounding quotes if accidentally copied
    url = url.strip("\"'")

    return url


# --------------------------------------------------
# FIND BEST DIRECT MP4
# --------------------------------------------------

def find_best_format(info):

    formats = info.get("formats") or []

    candidates = []

    for fmt in formats:

        media_url = fmt.get("url")

        if not media_url:
            continue

        ext = (fmt.get("ext") or "").lower()
        protocol = (fmt.get("protocol") or "").lower()

        # We want an already playable video file.
        # Avoid separate video-only + audio-only streams
        # because that would require server-side merging.
        has_video = fmt.get("vcodec") not in (None, "none")
        has_audio = fmt.get("acodec") not in (None, "none")

        if not has_video or not has_audio:
            continue

        # Prefer MP4
        mp4_score = 1 if ext == "mp4" else 0

        # Prefer normal HTTP/HTTPS media URLs
        direct_score = 1 if protocol in ("http", "https") else 0

        width = fmt.get("width") or 0
        height = fmt.get("height") or 0
        filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0

        candidates.append({
            "url": media_url,
            "ext": ext,
            "width": width,
            "height": height,
            "filesize": filesize,
            "format_id": fmt.get("format_id"),
            "vcodec": fmt.get("vcodec"),
            "acodec": fmt.get("acodec"),
            "mp4_score": mp4_score,
            "direct_score": direct_score
        })

    if not candidates:
        return None

    # Prefer:
    # 1. MP4
    # 2. Direct HTTP/HTTPS
    # 3. Highest resolution
    # 4. Highest filesize when resolution is equal

    candidates.sort(
        key=lambda x: (
            x["mp4_score"],
            x["direct_score"],
            x["height"],
            x["width"],
            x["filesize"]
        ),
        reverse=True
    )

    return candidates[0]


# --------------------------------------------------
# API
# --------------------------------------------------

@app.get("/")
def home():

    return {
        "success": True,
        "message": "Status Saver API is working",
        "version": "2.0.0",
        "platforms": [
            "instagram",
            "facebook",
            "pinterest"
        ]
    }


# --------------------------------------------------
# EXTRACT
# --------------------------------------------------

@app.post("/extract")
def extract(request: VideoRequest):

    url = clean_url(request.url)

    platform = detect_platform(url)

    if platform == "invalid":

        return {
            "success": False,
            "message": "Invalid URL"
        }

    if platform == "unsupported":

        return {
            "success": False,
            "platform": "unknown",
            "message": (
                "Only Instagram, Facebook and Pinterest "
                "links are supported."
            )
        }

    print("=" * 60)
    print("EXTRACT REQUEST")
    print("Platform:", platform)
    print("URL:", url)
    print("=" * 60)

    options = {

        # IMPORTANT:
        # We only extract information.
        # We DO NOT download the video on Render.
        "quiet": True,
        "no_warnings": True,

        "noplaylist": True,

        # Don't create cache files on Render
        "cachedir": False,

        # Don't write files
        "skip_download": True,

        # Prefer a ready-to-play MP4.
        #
        # We intentionally avoid:
        # bestvideo+bestaudio
        #
        # because that would require merging.
        "format": (
            "best[ext=mp4][vcodec!=none][acodec!=none]"
            "/best[vcodec!=none][acodec!=none]"
        ),

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/124.0 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9"
        }
    }

    # Optional cookies.
    #
    # Only use cookies if you are legitimately authorized
    # to access the content they provide access to.
    cookie_file = "cookies.txt"

    if os.path.exists(cookie_file):
        options["cookiefile"] = cookie_file

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:

            return {
                "success": False,
                "platform": platform,
                "message": "Could not extract media information."
            }

        # If extractor returns a direct URL
        # use it as a possible candidate.
        best = find_best_format(info)

        if not best and info.get("url"):

            best = {
                "url": info.get("url"),
                "ext": info.get("ext"),
                "width": info.get("width") or 0,
                "height": info.get("height") or 0,
                "filesize": (
                    info.get("filesize")
                    or info.get("filesize_approx")
                    or 0
                ),
                "format_id": info.get("format_id"),
                "vcodec": info.get("vcodec"),
                "acodec": info.get("acodec")
            }

        if not best:

            return {
                "success": False,
                "platform": platform,
                "message": (
                    "No directly downloadable video format "
                    "was available."
                )
            }

        title = info.get("title") or "Status Saver Video"

        thumbnail = info.get("thumbnail")

        duration = info.get("duration")

        return {

            "success": True,

            "platform": platform,

            "title": title,

            "thumbnail": thumbnail,

            "duration": duration,

            "width": best.get("width"),

            "height": best.get("height"),

            "extension": best.get("ext") or "mp4",

            "filesize": best.get("filesize"),

            "format_id": best.get("format_id"),

            # IMPORTANT:
            # Android downloads this URL directly.
            "media_url": best["url"],

            "message": "Media is ready for direct download."
        }

    except yt_dlp.utils.DownloadError as e:

        print("yt-dlp error:", str(e))

        return {
            "success": False,
            "platform": platform,
            "message": (
                "This media could not be downloaded or "
                "is not available for direct download."
            )
        }

    except Exception as e:

        print("Unexpected error:", str(e))

        return {
            "success": False,
            "platform": platform,
            "message": "Unable to process this link."
        }