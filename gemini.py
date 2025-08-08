import google.generativeai as genai
import os
import sys
import time
import gc
import subprocess
import logging
from dotenv import load_dotenv
from pathlib import Path
from google.api_core import exceptions

# --- SETUP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("transcription.log"),
        logging.StreamHandler()
    ]
)

# --- LOAD CONFIGURATION ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    logging.error("FATAL: API key not found. Please set GEMINI_API_KEY in your .env file.")
    exit()

genai.configure(api_key=API_KEY)

# --- FOLDER AND MODEL DEFINITIONS ---
transcription_model = genai.GenerativeModel(model_name="models/gemini-2.5-pro")
INPUT_FOLDER = Path("audio_in")
OUTPUT_FOLDER = Path("transcripts")

def get_media_duration_seconds(file_path):
    """Gets the duration of a media file in seconds using ffprobe."""
    command = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout)
    except Exception as e:
        logging.warning(f"Could not get duration using ffprobe for {file_path.name}: {e}")
        return None

def transcribe_file(media_path):
    """
    Manages the full process for a single file, with all fixes implemented.
    """
    output_path = OUTPUT_FOLDER / f"{media_path.stem}.txt"
    if output_path.exists():
        logging.info(f"Skipping '{media_path.name}', transcript already exists.")
        return

    media_file_for_api = None
    try:
        logging.info(f"--- Processing '{media_path.name}' ---")

        # --- DYNAMIC "SMART WAIT" LOGIC ---
        duration = get_media_duration_seconds(media_path)
        initial_wait_seconds = 0
        if duration:
            # Calculate a smart initial wait time (e.g., 10% of video length)
            initial_wait_seconds = max(30, int(duration * 0.10))
            logging.info(f"  Media duration: {int(duration//60)}m {int(duration%60)}s. Calculated initial wait: {initial_wait_seconds}s.")
        else:
            # If duration can't be found, fall back to a 6-minute wait
            initial_wait_seconds = 360
            logging.warning("  Could not determine media duration. Defaulting to a 6-minute initial wait.")
        
        media_file_for_api = genai.upload_file(path=media_path)
        logging.info(f"  Upload initiated. Entering 'smart wait' of {initial_wait_seconds} seconds...")
        time.sleep(initial_wait_seconds)
        
        polling_interval = 60
        while media_file_for_api.state.name == "PROCESSING":
            logging.info(f"  File is still processing. Waiting {polling_interval}s...")
            time.sleep(polling_interval)
            media_file_for_api = genai.get_file(media_file_for_api.name)
        # --- END OF DYNAMIC LOGIC ---

        if media_file_for_api.state.name == "FAILED":
            raise ValueError("File processing failed on the API side.")

        logging.info("  File is ACTIVE. Generating transcription...")
        safety_settings = {
            'HARM_CATEGORY_HARASSMENT': 'BLOCK_ONLY_HIGH',
            'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_ONLY_HIGH',
            'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_ONLY_HIGH',
            'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_ONLY_HIGH',
        }
        prompt = [
            "You are an expert transcriptionist. Your task is to transcribe the following video with high accuracy and timestamps for every distinct segment of speech.",
            media_file_for_api
        ]
        response = transcription_model.generate_content(
            prompt,
            safety_settings=safety_settings,
            request_options={"timeout": 1000}
        )
        
        if not response.parts:
             raise ValueError("The API response was empty, likely due to a safety block that could not be overridden. The model's finish reason was: " + str(response.candidates[0].finish_reason))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)
        logging.info(f"  SUCCESS! Transcription saved to '{output_path}'")
        del response

    except exceptions.ResourceExhausted as e:
        logging.error("FATAL: Daily quota exceeded. The script will now terminate.")
        raise SystemExit("Exiting due to quota limit.")
    except Exception as e:
        logging.error(f"An unhandled error occurred with '{media_path.name}': {e}")
    finally:
        if media_file_for_api:
            logging.info(f"  Cleaning up uploaded file from API: {media_file_for_api.name}")
            genai.delete_file(media_file_for_api.name)
            del media_file_for_api
        logging.info("  Running memory cleanup...")
        gc.collect()

def main_workflow():
    """Main function to run the continuous transcription workflow."""
    for folder in [INPUT_FOLDER, OUTPUT_FOLDER]:
        folder.mkdir(exist_ok=True)
    
    logging.info("--- Starting Transcription Workflow ---")
    
    media_extensions = ['.mp4', '.m4a', '.mp3', '.wav', '.mov', '.avi']
    all_files = [p for p in INPUT_FOLDER.iterdir() if p.is_file() and p.suffix.lower() in media_extensions]
    all_files.sort(key=os.path.getmtime)
    
    if not all_files:
        logging.info(f"No media files found in the '{INPUT_FOLDER}' directory.")
        return

    logging.info(f"Found {len(all_files)} media file(s) to process.")
    for media_path in all_files:
        transcribe_file(media_path)
        logging.info("-" * 50)

    logging.info("--- All files processed. Workflow Complete ---")

if __name__ == "__main__":
    main_workflow()
