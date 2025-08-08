import google.generativeai as genai
import os
import time
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("API key not found. Please set GEMINI_API_KEY in your .env file.")

genai.configure(api_key=API_KEY)

# --- Folder Definitions ---
INPUT_FOLDER = Path("audio_in")
OUTPUT_FOLDER = Path("transcripts")

# --- Model Definition ---
# Using 2.5 Pro as it's the best for transcription
transcription_model = genai.GenerativeModel(model_name="models/gemini-2.5-pro")


def run_comparison():
    """
    Main function to run the comparison workflow.
    """
    # Create necessary directories
    for folder in [INPUT_FOLDER, OUTPUT_FOLDER]:
        folder.mkdir(exist_ok=True)

    print("--- Starting Transcription Comparison ---")

    # Find the first media file in the input folder
    media_files = list(INPUT_FOLDER.iterdir())
    if not media_files:
        print(f"Error: No files found in '{INPUT_FOLDER}'. Please add a video/audio file to compare.")
        return

    # Use the first file found for the comparison
    media_path = media_files[0]
    print(f"Found file. Will use '{media_path.name}' for comparison.")

    # --- Step 1: Upload the file ONCE ---
    # We only need to upload the file once and can reuse it for both prompts.
    print("\n[UPLOADING FILE]")
    media_file_for_api = upload_file_to_gemini(media_path)
    if not media_file_for_api:
        return # Stop if upload fails

    # --- Step 2: Generate transcription with the SIMPLE prompt ---
    print("\n[TEST 1: SIMPLE PROMPT]")
    simple_prompt = "Please provide a clean transcription of this audio/video."
    simple_output_path = OUTPUT_FOLDER / f"{media_path.stem}.simple.txt"
    generate_transcription(media_file_for_api, simple_prompt, simple_output_path)

    # --- Step 3: Generate transcription with the DETAILED timestamp prompt ---
    print("\n[TEST 2: DETAILED TIMESTAMP PROMPT]")
    detailed_prompt = [
        "You are an expert transcriptionist. Your task is to transcribe the following video with high accuracy. "
        "The output format MUST include timestamps for every distinct segment of speech. "
        "Each entry should have a start and end time followed by the transcribed text. "
        "Follow this format exactly:\n\n"
        "[ HhMmSs - HhMmSs ] Text of the speech segment.\n\n"
        "Example:\n"
        "[ 0h0m5s - 0h0m12s ] This is the first segment of spoken words.\n"
        "[ 0h0m14s - 0h0m19s ] This is the second segment, after a brief pause.",
        media_file_for_api # Reusing the uploaded file
    ]
    timestamp_output_path = OUTPUT_FOLDER / f"{media_path.stem}.with_timestamps.txt"
    generate_transcription(media_file_for_api, detailed_prompt, timestamp_output_path)

    print(f"\n--- Comparison Complete ---")
    print(f"Check the '{OUTPUT_FOLDER}' directory for the two output files.")


def upload_file_to_gemini(file_path):
    """Uploads a single file to Gemini and returns the file object."""
    print(f"Uploading '{file_path.name}'...", end="", flush=True)
    try:
        media_file = genai.upload_file(path=file_path)
        # Wait for the file to be processed
        while media_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(10)
            media_file = genai.get_file(media_file.name)

        if media_file.state.name == "FAILED":
            print(f"\nError: File processing failed for '{file_path.name}'")
            return None

        print(" Done.")
        return media_file
    except Exception as e:
        print(f"\nAn error occurred during file upload: {e}")
        return None


def generate_transcription(media_file, prompt, output_path):
    """Generates and saves a transcription based on a given prompt."""
    if output_path.exists():
        print(f"Output file '{output_path.name}' already exists. Skipping.")
        return

    print(f"  Generating transcription and saving to '{output_path.name}'...", end="", flush=True)
    try:
        response = transcription_model.generate_content(
            prompt,
            request_options={"timeout": 1000}
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(" Done.")
    except Exception as e:
        print(f"\n  An error occurred during transcription: {e}")


if __name__ == "__main__":
    run_comparison()

