#!/usr/bin/env python3
import os, time, subprocess, glob, logging, sys
from dotenv import load_dotenv
from openai import OpenAI
from httpcore._exceptions import LocalProtocolError

# ─── CONFIG ─────────────────────────────────────────────────
MAX_BYTES    = 25 * 1024 * 1024           # 25 MB API limit
SEGMENT_SEC  = 300                        # split into 5 min segments
RAW_DIR      = "audio_in"                 # where you drop files
WORK_DIR     = "processing"               # intermediate files live here
OUT_DIR      = "transcripts"
VALID_EXT    = {".mp3", ".wav", ".m4a", ".dat"}
LOG_FILE     = "transcribe.log"

# ─── 1) UNSET proxies ───────────────────────────────────────
for p in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    os.environ.pop(p, None)

# ─── 2) LOAD .env & INIT OpenAI ────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("⚠️ OPENAI_API_KEY not set in .env")
client = OpenAI(api_key=API_KEY)

# ─── 3) LOGGING ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

# ─── 4) HELPERS ─────────────────────────────────────────────
def wait_for_file_complete(path, timeout=20, interval=0.5):
    start, last = time.time(), -1
    while time.time() - start < timeout:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        if size == last and size > 0:
            return True
        last = size
        time.sleep(interval)
    return False

def preprocess_audio(raw_path):
    """Convert to mono-16k WAV with improved clarity, output in WORK_DIR."""
    base = os.path.splitext(os.path.basename(raw_path))[0]
    timestamp = int(time.time())
    clean = os.path.join(WORK_DIR, f"{base}_{timestamp}_clean.wav")
    logging.info(f"Preprocessing {raw_path} → {clean}")
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_path,
        "-ac", "1", "-ar", "16000",
        "-af", "highpass=f=100, lowpass=f=6000, dynaudnorm",
        clean
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return clean

def split_audio(clean_path):
    """Split cleaned WAV into SEGMENT_SEC chunks in WORK_DIR."""
    base = os.path.splitext(os.path.basename(clean_path))[0]
    tmp = os.path.join(WORK_DIR, f"{base}_chunks")
    os.makedirs(tmp, exist_ok=True)
    pattern = os.path.join(tmp, f"{base}_%03d.wav")
    logging.info(f"Splitting {clean_path} → {tmp}/*")
    subprocess.run([
        "ffmpeg", "-y", "-i", clean_path,
        "-f", "segment", "-segment_time", str(SEGMENT_SEC),
        "-c", "copy", pattern
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(glob.glob(os.path.join(tmp, f"{base}_*.wav")))

def process_file(fp):
    name = os.path.basename(fp)
    base = os.path.splitext(name)[0]
    timestamp = int(time.time())
    out_txt = os.path.join(OUT_DIR, f"{base}_{timestamp}.txt")
    logging.info(f"Processing file: {name}")
    if not wait_for_file_complete(fp):
        logging.error(f"Timeout waiting for {name} to finish uploading")
        return

    cleaned = preprocess_audio(fp)
    chunks = [cleaned]
    if os.path.getsize(cleaned) > MAX_BYTES:
        chunks = split_audio(cleaned)

    pieces = []
    for idx, seg in enumerate(chunks, 1):
        for attempt in (1, 2):
            try:
                logging.info(f"Transcribing chunk {idx}/{len(chunks)} (try {attempt})")
                with open(seg, "rb") as f:
                    txt = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        response_format="text",
                        language="en"
                    ).strip()
                pieces.append(txt)
                break
            except LocalProtocolError as e:
                logging.warning(f"Chunk upload error; retrying: {e}")
                time.sleep(1)
            except Exception as e:
                logging.error(f"Failed chunk {idx}: {e}")
                break

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n\n".join(pieces) + "\n")
    logging.info(f"Transcript saved → {out_txt}")

# ─── 5) MAIN ────────────────────────────────────────────────
if __name__ == "__main__":
    for d in (RAW_DIR, WORK_DIR, OUT_DIR):
        os.makedirs(d, exist_ok=True)

    files = [f for f in os.listdir(RAW_DIR)
             if os.path.isfile(os.path.join(RAW_DIR, f)) and os.path.splitext(f.lower())[1] in VALID_EXT]

    if not files:
        logging.info(f"No audio files found in '{RAW_DIR}' — nothing to do.")
        sys.exit(0)

    logging.info(f"Processing {len(files)} file(s) in '{RAW_DIR}'…")

    for f in files:
        process_file(os.path.join(RAW_DIR, f))

    logging.info("✅ All done. Exiting.")
