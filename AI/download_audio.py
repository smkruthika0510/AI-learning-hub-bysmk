import sys
import os
import time
import yt_dlp
import av

# ---------------------------------------
# Check arguments
# ---------------------------------------
if len(sys.argv) < 3:
    print("Usage: python download_audio.py <youtube_url> <output_folder>")
    sys.exit(1)

url = sys.argv[1]
output_folder = sys.argv[2]

os.makedirs(output_folder, exist_ok=True)

MAX_DOWNLOAD_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5


def build_ydl_opts():
    return {
        # Prefer genuine audio-only formats explicitly, rather than a bare
        # "bestaudio/best" which can silently fall back to a combined
        # video+audio file (e.g. itag 18) if audio-only formats are
        # unavailable for whichever client yt-dlp happens to use.
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(output_folder, "%(id)s.%(ext)s"),
        "noplaylist": True,

        # Show detailed logs while debugging
        "quiet": False,
        "no_warnings": False,
        "verbose": True,

        # Try multiple clients in order. YouTube periodically runs
        # experiments (e.g. "SABR-only streaming") that break audio-only
        # format availability for a specific client — locking to just one
        # client means a single YouTube-side change can break every
        # download. Trying several lets yt-dlp fall through to one that
        # still has working audio-only URLs.
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "tv", "ios"]
            }
        },

        # Retry automatically
        "retries": 10,
        "fragment_retries": 10,

        # Ignore certificate issues if any
        "nocheckcertificate": True,

        # Convert audio to mp3
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }


def is_valid_audio_file(path):
    """
    Actually opens the file with the same decoder faster-whisper uses (PyAV)
    to confirm it's genuinely valid, playable audio -- not just that a file
    with the right name exists. A file that "exists" but is a partial or
    corrupted download (common on longer videos where more can go wrong
    mid-download) still fails this check.
    """
    try:
        with av.open(path) as container:
            if not container.streams.audio:
                return False
            # Actually decode a handful of frames rather than just reading
            # the header, since a truncated download can have a valid
            # header but broken/empty stream data.
            frame_count = 0
            for frame in container.decode(audio=0):
                frame_count += 1
                if frame_count >= 5:
                    break
            return frame_count > 0
    except Exception as e:
        print(f"Audio validation failed for {path}: {e}", file=sys.stderr)
        return False


# ---------------------------------------
# Download Audio (with real validation + retry on a genuinely bad download)
# ---------------------------------------
last_error = None
audio_path = None

for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
    try:
        print(f"Download attempt {attempt}/{MAX_DOWNLOAD_ATTEMPTS}...", file=sys.stderr)

        with yt_dlp.YoutubeDL(build_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=True)

            if info.get("vcodec") not in (None, "none"):
                print(
                    f"WARNING: yt-dlp selected a combined video+audio format "
                    f"(vcodec={info.get('vcodec')}, format_id={info.get('format_id')}) "
                    f"instead of audio-only. This usually means audio-only formats "
                    f"were unavailable for every tried player_client.",
                    file=sys.stderr
                )

            # Save title
            with open("title.txt", "w", encoding="utf-8") as f:
                f.write(info.get("title", "Untitled"))

            audio_path = os.path.join(
                output_folder,
                f"{info['id']}.mp3"
            )

            if not os.path.exists(audio_path):
                raise Exception("MP3 file was not created.")

            if not is_valid_audio_file(audio_path):
                # The file exists but PyAV couldn't actually decode it --
                # a genuinely broken/partial download, not a naming issue.
                # Delete it and retry the whole download rather than
                # handing a corrupt file downstream to transcribe.py.
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
                raise Exception("Downloaded MP3 failed audio validation (corrupt or incomplete download).")

            print(f"Downloaded and validated: {audio_path}", file=sys.stderr)
            last_error = None
            break

    except Exception as ex:
        last_error = ex
        print(f"Download attempt {attempt} failed: {ex}", file=sys.stderr)

        if attempt < MAX_DOWNLOAD_ATTEMPTS:
            print(f"Retrying full download in {RETRY_DELAY_SECONDS}s...", file=sys.stderr)
            time.sleep(RETRY_DELAY_SECONDS)

if last_error is not None:
    print("ERROR:", file=sys.stderr)
    print(f"Failed to download valid audio after {MAX_DOWNLOAD_ATTEMPTS} attempts: {last_error}", file=sys.stderr)
    sys.exit(1)

print(audio_path)