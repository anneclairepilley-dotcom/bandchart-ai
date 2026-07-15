"""YouTube audio import: yt-dlp extracts the audio, ffmpeg converts to WAV.

The extracted file lands in the project's normal audio folder, so everything
downstream (transcription, exports, deletion) treats it exactly like an
uploaded file.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

MAX_DURATION_S = 600  # 10 minutes — keeps extraction + transcription snappy

AUDIO_BASENAME = "youtube-audio"

_YOUTUBE_PATTERNS = [
    # watch URLs must actually reference a video (v=…): a bare watch?list=…
    # is a playlist link, which yt-dlp would expand to every entry.
    r"^https?://(www\.|m\.|music\.)?youtube\.com/(watch\?(\S*&)?v=[\w-]{6,}|shorts/[\w-]+)",
    r"^https?://youtu\.be/[\w-]{5,}",
]

FFMPEG_HELP = (
    "ffmpeg is required to convert YouTube audio but wasn't found on the server. "
    "In Codespaces run: sudo apt-get update && sudo apt-get install -y ffmpeg — "
    "then restart the backend and try again."
)
YTDLP_HELP = (
    "The yt-dlp library is missing on the server. With the backend virtual "
    "environment active, run: pip install -r requirements.txt — then restart "
    "the backend and try again."
)


class YoutubeImportError(Exception):
    """Import failure with a message safe to show to the user."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def is_valid_youtube_url(url: str) -> bool:
    url = url.strip()
    # Test-only escape hatch: lets automated tests exercise the full pipeline
    # with a local media URL in environments where youtube.com is blocked.
    if os.environ.get("BANDCHART_ALLOW_ANY_URL") == "1" and url.startswith("http"):
        return True
    return any(re.match(pattern, url) for pattern in _YOUTUBE_PATTERNS)


def _friendly_download_error(exc: Exception) -> YoutubeImportError:
    text = str(exc)
    lowered = text.lower()
    # Network problems first: their messages can contain arbitrary other words
    # (e.g. "Unable to download API page ... Confirm you are on the latest
    # version"), so more specific checks must not run before this one.
    # YouTube's bot/rate blocks come first: they often arrive wrapped in
    # network-sounding text ("Unable to download API page: HTTP Error 403"),
    # so this check must run before the generic network branch.
    if (
        ("sign in to confirm" in lowered and "bot" in lowered)
        or "http error 403" in lowered
        or "http error 429" in lowered
        or "too many requests" in lowered
    ):
        return YoutubeImportError(
            "YouTube blocked this cloud server from downloading the audio. This "
            "can happen in Codespaces. Try another video, upload an audio file "
            "instead, or run the app locally.",
            status_code=502,
        )
    if re.search(
        r"unable to connect|proxy|getaddrinfo|timed? ?out|temporary failure"
        r"|connection (refused|reset|aborted)|unable to download (api page|webpage)"
        r"|network is unreachable|no route to host|ssl",
        lowered,
    ):
        return YoutubeImportError(
            "Couldn't reach YouTube from the server — YouTube may be blocked on "
            "this network, or the connection dropped. Check the internet "
            "connection and try again.",
            status_code=502,
        )
    if "private video" in lowered or ("sign in" in lowered and "private" in lowered):
        return YoutubeImportError(
            "This video is private or restricted, so its audio can't be extracted. "
            "Try a video that plays for you in a normal browser without signing in."
        )
    if re.search(r"age.restrict|confirm your age|age.gated", lowered):
        return YoutubeImportError(
            "This video is age-restricted, so its audio can't be extracted without "
            "a signed-in session. Try a different video."
        )
    if "unavailable" in lowered or "removed" in lowered or "does not exist" in lowered:
        return YoutubeImportError(
            "That video is unavailable (it may have been removed, made private, or "
            "the link has a typo). Double-check the URL and try again."
        )
    return YoutubeImportError(f"YouTube import failed: {text[:300]}")


def _check_importable(info: dict[str, Any]) -> None:
    """Reject videos that can't be imported safely.

    Live/endless content must be refused BEFORE downloading: yt-dlp records
    an ongoing stream until it ends, which would pin the request forever and
    fill the disk. A missing duration is treated the same way — the length
    cap can't be enforced without it.
    """
    if info.get("is_live") or info.get("live_status") in (
        "is_live",
        "is_upcoming",
        "post_live",
    ):
        raise YoutubeImportError(
            "Live streams can't be imported — try a normal uploaded video."
        )
    duration = info.get("duration")
    if not duration:
        # Direct media URLs (test-hatch only) legitimately report no duration.
        if os.environ.get("BANDCHART_ALLOW_ANY_URL") == "1":
            return
        raise YoutubeImportError(
            "Couldn't determine this video's length, so it can't be imported "
            "safely. Try a different video."
        )
    if duration > MAX_DURATION_S:
        minutes = int(duration // 60)
        raise YoutubeImportError(
            f"This video is about {minutes} minutes long — YouTube import is "
            f"limited to {MAX_DURATION_S // 60} minutes for now so extraction and "
            "transcription stay quick. Try a shorter clip."
        )


def download_audio_as_wav(url: str, dest_dir: Path) -> tuple[str, dict[str, Any]]:
    """Extract a video's audio as WAV into dest_dir.

    Returns (saved filename, {"title": …, "duration": …}).
    Raises YoutubeImportError with a user-friendly message on any failure.
    """
    if shutil.which("ffmpeg") is None:
        raise YoutubeImportError(FFMPEG_HELP, status_code=500)
    try:
        import yt_dlp
    except ImportError as exc:
        raise YoutubeImportError(YTDLP_HELP, status_code=500) from exc

    base_opts = {"quiet": True, "no_warnings": True, "noplaylist": True}

    # Probe first: catches unavailable/private videos and over-length videos
    # before any download work happens.
    try:
        with yt_dlp.YoutubeDL(dict(base_opts)) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise _friendly_download_error(exc) from exc

    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise YoutubeImportError(
                "That link points to a playlist with no playable video. "
                "Paste a link to a single video instead."
            )
        info = entries[0]

    _check_importable(info)

    # Download the resolved single video, never the original URL: if the link
    # expanded to a playlist, the original URL would download every entry.
    target_url = info.get("webpage_url") or url

    dest_dir.mkdir(parents=True, exist_ok=True)
    download_opts = {
        **base_opts,
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / f"{AUDIO_BASENAME}.%(ext)s"),
        "playlist_items": "1",  # belt-and-braces against playlist expansion
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "wav"}
        ],
    }
    try:
        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([target_url])
    except yt_dlp.utils.DownloadError as exc:
        raise _friendly_download_error(exc) from exc

    wav_path = dest_dir / f"{AUDIO_BASENAME}.wav"
    if not wav_path.exists():
        raise YoutubeImportError(
            "The audio downloaded but converting it to WAV failed. Check that "
            "ffmpeg is installed and working, then try again.",
            status_code=500,
        )
    return wav_path.name, {"title": info.get("title"), "duration": info.get("duration")}
