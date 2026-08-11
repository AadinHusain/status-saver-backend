import os
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

# Ensure the downloads directory exists when server starts
DOWNLOADS_DIR = "downloads"
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
        video_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOADS_DIR, f"{video_id}.%(ext)s")

        options = {
            "quiet": True,
            "no_warnings": True,
            # Single pre-merged MP4 stream preferred to avoid FFmpeg dependency issues on Render
            "format": "best[ext=mp4]/bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": output_template
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                request.url,
                download=True
            )

        # Locate the downloaded file (accounting for possible extension variations)
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
        return {
            "success": False,
            "platform": platform,
            "message": str(e)
        }


@app.get("/file/{filename}")
def get_file(filename: str):

    file_path = os.path.join(DOWNLOADS_DIR, filename)

    if not os.path.exists(file_path):
        return {
            "success": False,
            "message": "File not found"
        }

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename
    )