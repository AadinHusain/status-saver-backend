import os
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

DOWNLOADS_DIR = "downloads"
COOKIE_FILE = "cookies.txt"

os.makedirs(DOWNLOADS_DIR, exist_ok=True)


class VideoRequest(BaseModel):
    url: str


def detect_platform(url: str):
    try:
        hostname = urlparse(url).netloc.lower()
        hostname = hostname.replace("www.", "")

        if hostname == "instagram.com" or hostname.endswith(".instagram.com"):
            return "instagram"

        if hostname == "youtube.com" or hostname.endswith(".youtube.com"):
            return "youtube"

        if hostname == "youtu.be":
            return "youtube"

        return "unsupported"

    except Exception:
        return "invalid"


@app.get("/")
def home():
    return {
        "success": True,
        "message": "Status Saver API is working"
    }


@app.post("/download")
def download(request: VideoRequest):

    platform = detect_platform(request.url)

    if platform == "unsupported":
        return {
            "success": False,
            "message": "Unsupported platform"
        }

    if platform == "invalid":
        return {
            "success": False,
            "message": "Invalid URL"
        }

    try:

        # Create a unique filename
        video_id = str(uuid.uuid4())

        output_template = os.path.join(
            DOWNLOADS_DIR,
            f"{video_id}.%(ext)s"
        )

        options = {
            # Detailed logging for Render debugging
            "quiet": False,
            "no_warnings": False,
            "verbose": True,

            # Download best available combination
            # "format": "b/best/bestvideo+bestaudio",
            "format": "bestvideo*+bestaudio/best",
            "merge_output_format": "mp4",

            # Output filename
            "outtmpl": output_template,

            # YouTube client configuration
            "extractor_args": {
                "youtube": {
                    "player_client": [
                        "android",
                        "ios",
                        "mweb"
                    ]
                }
            },

            # Browser-like headers
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9"
            }
        }

        # Use cookies.txt if it exists
        if os.path.exists(COOKIE_FILE):
            options["cookiefile"] = COOKIE_FILE
            print("Using cookies.txt")

        else:
            print("No cookies.txt found")

        print("=" * 60)
        print("DOWNLOAD REQUEST")
        print("Platform:", platform)
        print("URL:", request.url)
        print("=" * 60)

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                request.url,
                download=True
            )

        # Find downloaded file
        downloaded_file = None

        for file in os.listdir(DOWNLOADS_DIR):

            if file.startswith(video_id):

                downloaded_file = file
                break

        if not downloaded_file:

            return {
                "success": False,
                "platform": platform,
                "message": "Failed to save downloaded file"
            }

        return {
            "success": True,
            "platform": platform,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "filename": downloaded_file,
            "download_url": f"/file/{downloaded_file}",
            "original_url": request.url,
            "message": "Video downloaded successfully"
        }

    except Exception as e:

        print("=" * 60)
        print("DOWNLOAD ERROR")
        print(str(e))
        print("=" * 60)

        return {
            "success": False,
            "platform": platform,
            "message": str(e)
        }


@app.get("/file/{filename}")
def get_file(filename: str):

    file_path = os.path.join(
        DOWNLOADS_DIR,
        filename
    )

    if not os.path.exists(file_path):

        return {
            "success": False,
            "message": "File not found"
        }

    if filename.endswith(".webm"):
        media_type = "video/webm"

    elif filename.endswith(".mp4"):
        media_type = "video/mp4"

    else:
        media_type = "application/octet-stream"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename
    )
