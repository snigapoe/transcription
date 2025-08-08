import os
import sys
import time
import gc
import subprocess
import logging
import math
import shutil
from dotenv import load_dotenv
from pathlib import Path
from pydub import AudioSegment
import google.generativeai as genai
from google.api_core import exceptions

# --- 1. CONFIGURATION ---
def setup_logging():
    """Configures logging to file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("meeting_transcription.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

# --- Load API Key ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    logging.error("FATAL: API key not found. Please set GEMINI_API_KEY in your .env file.")
    sys.exit()
genai.configure(api_key=API_KEY)

# --- Script Parameters ---
MODEL_NAME = "models/gemini-2.5-pro"
INPUT_FOLDER = Path("audio_in")
OUTPUT_FOLDER = Path("transcripts")
CHUNK_FOLDER = Path("temp_chunks")
CHUNK_DURATION_MINUTES = 30  # Split files longer than this
SUPPORTED_EXTENSIONS = ['.mp4', '.m4a', '.mp3', '.wav', '.mov', '.avi', '.flac']


# --- 2. HELPER FUNCTIONS ---
def get_media_duration_seconds(file_path):
    """Gets media duration using ffprobe. Returns float or None."""
    command = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout)
    except Exception as e:
        logging.warning(f"Could not get duration for {file_path.name} using ffprobe: {e}")
        return None

def split_audio(file_path, chunk_duration_sec, output_dir):
    """Splits an audio file into chunks and returns a list of their paths."""
    output_dir.mkdir(exist_ok=True)
    logging.info(f"Splitting '{file_path.name}' into {chunk_duration_sec / 60}-minute chunks...")
    try:
        audio = AudioSegment.from_file(file_path)
        num_chunks = math.ceil(len(audio) / (chunk_duration_sec * 1000))
        chunk_paths = []
        for i in range(num_chunks):
            start_ms = i * chunk_duration_sec * 1000
            end_ms = (i + 1) * chunk_duration_sec * 1000
            chunk = audio[start_ms:end_ms]
            chunk_path = output_dir / f"{file_path.stem}_chunk{i+1}.mp3"
            chunk.export(chunk_path, format="mp3")
            chunk_paths.append(chunk_path)
        logging.info(f"Successfully split into {len(chunk_paths)} chunks.")
        return chunk_paths
    except Exception as e:
        logging.error(f"Failed to split audio file {file_path.name}: {e}")
        return []

def transcribe_chunk(chunk_path, model):
    """Uploads, transcribes, and deletes a single media chunk."""
    logging.info(f"Processing chunk: {chunk_path.name}")
    media_file_for_api = None
    try:
        media_file_for_api = genai.upload_file(path=chunk_path)
        
        # Poll for processing completion
        while media_file_for_api.state.name == "PROCESSING":
            logging.info(f"  Waiting for '{chunk_path.name}' to be processed...")
            time.sleep(10)
            media_file_for_api = genai.get_file(media_file_for_api.name)

        if media_file_for_api.state.name == "FAILED":
            raise ValueError("File processing failed on the API side.")

        logging.info(f"  '{chunk_path.name}' is ACTIVE. Generating transcription...")
        prompt = """
        You are a highly accurate transcriptionist. Your task is to transcribe the following meeting audio.
        - Identify and label each speaker (e.g., Speaker 1, Speaker 2).
        - Transcribe verbatim.
        - Ensure high accuracy for all words.
        """
        response = model.generate_content([prompt, media_file_for_api], request_options={"timeout": 1000})
        return response.text
    
    except Exception as e:
        logging.error(f"  An error occurred with chunk '{chunk_path.name}': {e}")
        return None
    finally:
        if media_file_for_api:
            genai.delete_file(media_file_for_api.name)
        gc.collect()

def summarize_transcript(transcript, model):
    """Generates a summary, decisions, and action items from a transcript."""
    logging.info("Generating final summary...")
    prompt = f"""
    You are a professional meeting assistant. Based on the following meeting transcript, provide a concise summary.
    Your output must be in three distinct sections:
    1.  **Summary:** A brief overview of the meeting's purpose and key discussions.
    2.  **Key Decisions:** A bulleted list of all decisions made during the meeting.
    3.  **Action Items:** A bulleted list of all action items, including who is assigned to each if mentioned.

    Transcript:
    ---
    {transcript}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Could not generate summary: {e}")
        return "Summary could not be generated."

# --- 3. MAIN WORKFLOW ---
def main():
    """Main function to run the continuous transcription workflow."""
    setup_logging()
    
    # Create necessary directories
    for folder in [INPUT_FOLDER, OUTPUT_FOLDER, CHUNK_FOLDER]:
        folder.mkdir(exist_ok=True)
    
    model = genai.GenerativeModel(model_name=MODEL_NAME)
    
    all_files = [p for p in INPUT_FOLDER.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    
    if not all_files:
        logging.info(f"No media files found in '{INPUT_FOLDER}'.")
        return

    logging.info(f"Found {len(all_files)} files to process.")
    for media_path in all_files:
        logging.info(f"--- Starting file: {media_path.name} ---")
        transcript_path = OUTPUT_FOLDER / f"{media_path.stem}_transcript.txt"
        summary_path = OUTPUT_FOLDER / f"{media_path.stem}_summary.txt"

        if transcript_path.exists():
            logging.info(f"Skipping '{media_path.name}', transcript already exists.")
            continue
        
        duration_sec = get_media_duration_seconds(media_path)
        if duration_sec is None:
            logging.warning(f"Skipping {media_path.name} due to inability to get duration.")
            continue
            
        chunk_paths = []
        if duration_sec > CHUNK_DURATION_MINUTES * 60:
            chunk_paths = split_audio(media_path, CHUNK_DURATION_MINUTES * 60, CHUNK_FOLDER)
        else:
            chunk_paths = [media_path] # Process the whole file as a single "chunk"
            
        full_transcript_parts = []
        # UPDATED LOOP with enumerate and time.sleep
        for i, path in enumerate(chunk_paths):
            transcript_part = transcribe_chunk(path, model)
            if transcript_part:
                full_transcript_parts.append(transcript_part)
            
            # If it's not the last chunk, wait 60 seconds to respect API rate limits
            if i < len(chunk_paths) - 1:
                logging.info(f"Waiting 60 seconds to respect API rate limits... ({i+1}/{len(chunk_paths)} chunks processed)")
                time.sleep(60)

        if not full_transcript_parts:
            logging.error(f"Failed to transcribe any part of {media_path.name}. Skipping.")
            continue

        full_transcript = "\n\n".join(full_transcript_parts)
        
        # Save the full transcript
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(full_transcript)
        logging.info(f"Full transcript saved to '{transcript_path}'")

        # Generate and save the summary
        summary = summarize_transcript(full_transcript, model)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary)
        logging.info(f"Meeting summary saved to '{summary_path}'")
        
        # Clean up temporary chunk folder if it was used
        if CHUNK_FOLDER.exists() and any(CHUNK_FOLDER.iterdir()):
             shutil.rmtree(CHUNK_FOLDER)
             CHUNK_FOLDER.mkdir(exist_ok=True) # Recreate for next run
        logging.info(f"--- Finished file: {media_path.name} ---")

    logging.info("--- All files processed. Workflow Complete. ---")

if __name__ == "__main__":
    try:
        main()
    except exceptions.ResourceExhausted as e:
        logging.error("FATAL: Gemini API quota exceeded. Please check your billing and limits.")
    except Exception as e:
        logging.error(f"An unexpected fatal error occurred: {e}")
