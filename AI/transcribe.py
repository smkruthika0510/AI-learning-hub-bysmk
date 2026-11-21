from faster_whisper import WhisperModel
import sys
import os
import time

# -----------------------------
# Check Input
# -----------------------------
if len(sys.argv) < 2:
    print("No audio file provided!", file=sys.stderr)
    sys.exit(1)

audio_path = sys.argv[1]

if not os.path.exists(audio_path):
    print(f"Audio file not found: {audio_path}", file=sys.stderr)
    sys.exit(1)

# -----------------------------
# Wait for the file to be stable on disk before touching it.
#
# If this project folder lives inside OneDrive (or any other syncing
# service), a file can still be mid-write, locked, or swapped to a
# cloud-only placeholder for a moment right after it's created. Reading
# it while that's happening produces a corrupted/partial file that
# FFmpeg/PyAV reports as "Invalid data found when processing input" --
# not a real transcription failure. Polling the file size twice with a
# short pause catches that case before Whisper ever sees the file.
# -----------------------------
previous_size = -1
stable_checks = 0

for _ in range(10):
    try:
        current_size = os.path.getsize(audio_path)
    except OSError:
        current_size = -1

    if current_size > 0 and current_size == previous_size:
        stable_checks += 1
        if stable_checks >= 2:
            break
    else:
        stable_checks = 0

    previous_size = current_size
    time.sleep(0.5)

if previous_size <= 0:
    print(
        f"Audio file exists but is empty or unreadable: {audio_path}\n"
        f"If this project folder is inside OneDrive/Dropbox/etc., the file may still be "
        f"syncing or was swapped to a cloud-only placeholder. Try excluding the project's "
        f"wwwroot/uploads and AI folders from cloud sync.",
        file=sys.stderr
    )
    sys.exit(1)

print("Processing file:", audio_path, file=sys.stderr)

# -----------------------------
# Load Whisper Model
# -----------------------------
print("Loading Whisper model...", file=sys.stderr)
start = time.time()

model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

print(f"Model loaded in {time.time()-start:.2f} seconds", file=sys.stderr)

# -----------------------------
# Transcribe
# -----------------------------
print("Starting transcription...", file=sys.stderr)
transcribe_start = time.time()

DECODE_MAX_ATTEMPTS = 5
DECODE_RETRY_DELAY_SECONDS = 4

segments = None
info = None
last_decode_error = None

for decode_attempt in range(1, DECODE_MAX_ATTEMPTS + 1):
    try:
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=False
        )
        last_decode_error = None
        break
    except Exception as e:
        last_decode_error = e
        is_invalid_data = "Invalid data found" in str(e) or "InvalidDataError" in str(e)

        print(f"Whisper Error (attempt {decode_attempt}/{DECODE_MAX_ATTEMPTS}): {e}", file=sys.stderr)

        if is_invalid_data and decode_attempt < DECODE_MAX_ATTEMPTS:
            # "Invalid data" here usually isn't a genuinely corrupt file — it's
            # FFmpeg trying to read the file before it's actually fully
            # available (a sync/lock delay from OneDrive/Dropbox/etc., or a
            # file handle not yet released by whatever just wrote it). File
            # size can look stable while content still isn't readable, so the
            # only reliable check is retrying the real decode after a pause.
            print(f"Retrying decode in {DECODE_RETRY_DELAY_SECONDS}s (file may still be syncing/locked)...", file=sys.stderr)
            time.sleep(DECODE_RETRY_DELAY_SECONDS)
        elif not is_invalid_data:
            # Not the transient class of error — no point retrying.
            break

if last_decode_error is not None:
    print("Whisper Error:", str(last_decode_error), file=sys.stderr)

    if "Invalid data found" in str(last_decode_error) or "InvalidDataError" in str(last_decode_error):
        print(
            "This means FFmpeg still could not decode the file as valid media "
            f"after {DECODE_MAX_ATTEMPTS} attempts -- either the upload is "
            "genuinely corrupted/incomplete, the format isn't supported, or "
            "(if this project is inside OneDrive/Dropbox/etc.) the sync/lock "
            "delay lasted longer than the retries covered. Try excluding the "
            "project's wwwroot/uploads and AI folders from cloud sync.",
            file=sys.stderr
        )

    sys.exit(1)

print(f"Transcription took {time.time() - transcribe_start:.2f} seconds", file=sys.stderr)

print(f"Detected Language : {info.language}", file=sys.stderr)
print(f"Language Probability : {info.language_probability:.2f}", file=sys.stderr)

# -----------------------------
# Build Transcript
# -----------------------------
transcript = ""
segment_count = 0

for segment in segments:
    segment_count += 1

    print(
        f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text}",
        file=sys.stderr
    )

    transcript += segment.text.strip() + " "

transcript = transcript.strip()

print(f"Segments Found : {segment_count}", file=sys.stderr)
print(f"Transcript Length : {len(transcript)}", file=sys.stderr)

# -----------------------------
# Check Transcript
# -----------------------------
if len(transcript) == 0:
    print("No speech detected in the audio.", file=sys.stderr)
    sys.exit(1)

# -----------------------------
# Save Transcript
# -----------------------------
with open("transcript.txt", "w", encoding="utf-8") as f:
    f.write(transcript)

print("Transcript saved successfully.", file=sys.stderr)

# stdout is read by ASP.NET
print(transcript)