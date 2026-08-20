import os
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(
    title="Status Saver API",
    version="2.0.1"
)


# ============================================================
# REQUEST MODEL
# ============================================================

class VideoRequest(BaseModel):
    url: str


# ============================================================
# PLATFORM DETECTION
# ============================================================

def detect_platform(url: str):

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return "invalid"

        hostname = parsed.netloc.lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        # Instagram
        if (
            hostname == "instagram.com"
            or hostname.endswith(".instagram.com")
        ):
            return "instagram"

        # Facebook
        if (
            hostname == "facebook.com"
            or hostname.endswith(".facebook.com")
            or hostname == "fb.watch"
        ):
            return "facebook"

        # Pinterest
        if (
            hostname == "pin.it"
            or hostname == "pinterest.com"
            or hostname.endswith(".pinterest.com")
        ):
            return "pinterest"

        return "unsupported"

    except Exception:
        return "invalid"


# ============================================================
# URL CLEANING
# ============================================================

def clean_url(url: str) -> str:

    url = url.strip()

    # Remove accidental quotes
    url = url.strip("\"'")

    return url


# ============================================================
# FIND BEST DIRECT VIDEO FORMAT
# ============================================================

def find_best_format(info):

    formats = info.get("formats") or []

    candidates = []

    for fmt in formats:

        media_url = fmt.get("url")

        if not media_url:
            continue

        ext = (fmt.get("ext") or "").lower()
        protocol = (fmt.get("protocol") or "").lower()

        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")

        has_video = vcodec not in (None, "none")
        has_audio = acodec not in (None, "none")

        # We want a ready-to-play file.
        # This avoids server-side merging.
        if not has_video or not has_audio:
            continue

        width = fmt.get("width") or 0
        height = fmt.get("height") or 0

        filesize = (
            fmt.get("filesize")
            or fmt.get("filesize_approx")
            or 0
        )

        mp4_score = 1 if ext == "mp4" else 0

        direct_score = (
            1 if protocol in ("http", "https") else 0
        )

        candidates.append({
            "url": media_url,
            "ext": ext,
            "width": width,
            "height": height,
            "filesize": filesize,
            "format_id": fmt.get("format_id"),
            "vcodec": vcodec,
            "acodec": acodec,
            "mp4_score": mp4_score,
            "direct_score": direct_score
        })

    if not candidates:
        return None

    # Priority:
    #
    # 1. MP4
    # 2. HTTP/HTTPS
    # 3. Highest resolution
    # 4. Largest file when resolution is equal

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


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():

    return {
        "success": True,
        "message": "Status Saver API is working",
        "version": "2.0.1",
        "platforms": [
            "instagram",
            "facebook",
            "pinterest"
        ]
    }


# ============================================================
# EXTRACT MEDIA
# ============================================================

@app.post("/extract")
def extract(request: VideoRequest):

    url = clean_url(request.url)

    platform = detect_platform(url)

    # --------------------------------------------------------
    # URL VALIDATION
    # --------------------------------------------------------

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

    print("=" * 70)
    print("EXTRACT REQUEST")
    print("Platform:", platform)
    print("URL:", url)
    print("=" * 70)

    # --------------------------------------------------------
    # YT-DLP OPTIONS
    # --------------------------------------------------------

    options = {

        # Extraction only.
        # Render does NOT download the video.
        "skip_download": True,

        "quiet": True,

        "no_warnings": True,

        "noplaylist": True,

        # Don't create a yt-dlp cache on Render.
        "cachedir": False,

        # Prefer a ready-to-play MP4.
        #
        # We deliberately avoid:
        #
        # bestvideo+bestaudio
        #
        # because that requires downloading and merging
        # separate streams.
        "format": (
            "best[ext=mp4][vcodec!=none][acodec!=none]"
            "/best[vcodec!=none][acodec!=none]"
        ),

        # Browser-like headers.
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

    # --------------------------------------------------------
    # OPTIONAL COOKIE FILE
    # --------------------------------------------------------
    #
    # Only use cookies when you are authorized to access
    # the content associated with them.
    # --------------------------------------------------------

    cookie_file = "cookies.txt"

    if os.path.exists(cookie_file):

        options["cookiefile"] = cookie_file

        print("Cookie file detected.")

    else:

        print("No cookie file detected.")

    # --------------------------------------------------------
    # EXTRACTION
    # --------------------------------------------------------

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:

            print("No extraction information returned.")

            return {
                "success": False,
                "platform": platform,
                "message": "Could not extract media information."
            }

        # ----------------------------------------------------
        # FIND DIRECT VIDEO FORMAT
        # ----------------------------------------------------

        best = find_best_format(info)

        # ----------------------------------------------------
        # FALLBACK TO TOP-LEVEL URL
        # ----------------------------------------------------

        if not best and info.get("url"):

            media_url = info.get("url")

            best = {
                "url": media_url,
                "ext": info.get("ext") or "mp4",
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

        # ----------------------------------------------------
        # NO DIRECT FORMAT
        # ----------------------------------------------------

        if not best:

            print("=" * 70)
            print("NO DIRECT VIDEO FORMAT")
            print("Platform:", platform)
            print("Extractor:", info.get("extractor"))
            print("Extractor key:", info.get("extractor_key"))
            print("Title:", info.get("title"))
            print(
                "Available formats:",
                len(info.get("formats") or [])
            )
            print("=" * 70)

            return {
                "success": False,
                "platform": platform,
                "message": (
                    "No directly downloadable video format "
                    "was available."
                )
            }

        # ----------------------------------------------------
        # METADATA
        # ----------------------------------------------------

        title = (
            info.get("title")
            or "Status Saver Video"
        )

        thumbnail = info.get("thumbnail")

        duration = info.get("duration")

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        print("=" * 70)
        print("EXTRACTION SUCCESS")
        print("Platform:", platform)
        print("Title:", title)
        print("Format:", best.get("ext"))
        print("Resolution:",
              best.get("width"),
              "x",
              best.get("height"))
        print("Format ID:", best.get("format_id"))
        print("=" * 70)

        return {

            "success": True,

            "platform": platform,

            "title": title,

            "thumbnail": thumbnail,

            "duration": duration,

            "width": best.get("width"),

            "height": best.get("height"),

            "extension": (
                best.get("ext")
                or "mp4"
            ),

            "filesize": best.get("filesize"),

            "format_id": best.get("format_id"),

            # Android will download this directly.
            "media_url": best["url"],

            "message": (
                "Media is ready for direct download."
            )
        }

    # --------------------------------------------------------
    # YT-DLP ERROR
    # --------------------------------------------------------

    except yt_dlp.utils.DownloadError as e:

        error_message = str(e)

        # IMPORTANT:
        # This appears in Render logs so we can diagnose
        # the real problem.
        print("=" * 70)
        print("YT-DLP EXTRACTION ERROR")
        print("Platform:", platform)
        print("URL:", url)
        print("ERROR:", error_message)
        print("=" * 70)

        # Don't expose the full internal error to users.
        return {
            "success": False,
            "platform": platform,
            "message": (
                "This media could not be accessed or "
                "is not available for direct download."
            )
        }

    # --------------------------------------------------------
    # UNEXPECTED ERROR
    # --------------------------------------------------------

    except Exception as e:

        error_message = str(e)

        print("=" * 70)
        print("UNEXPECTED EXTRACTION ERROR")
        print("Platform:", platform)
        print("URL:", url)
        print("ERROR:", error_message)
        print("=" * 70)

        return {
            "success": False,
            "platform": platform,
            "message": "Unable to process this link."
        }