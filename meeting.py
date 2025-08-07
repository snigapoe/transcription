import os
import google.generativeai as genai
from pathlib import Path
from dotenv import load_dotenv

def create_directory_if_not_exists(folder_path):
    """
    Checks if a directory exists, and if not, creates it.

    Args:
        folder_path (str): The path to the directory.
    """
    if not os.path.isdir(folder_path):
        print(f"Directory not found. Creating directory: {folder_path}")
        os.makedirs(folder_path)

def transcribe_and_summarize_audio(api_key, audio_path):
    """
    Transcribes an audio file and summarizes the resulting text using the Gemini API.

    Args:
        api_key (str): Your Google AI API key.
        audio_path (str): The path to the audio file.

    Returns:
        tuple: A tuple containing the transcription and the summary,
               or (None, None) if an error occurs.
    """
    try:
        genai.configure(api_key=api_key)

        print(f"Uploading file: {audio_path}...")
        audio_file = genai.upload_file(path=audio_path)
        print(f"Completed upload: {audio_file.name}")

        model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")

        # Prompt for transcription
        print("Transcribing audio...")
        transcription_response = model.generate_content(
            ["Please transcribe this audio.", audio_file]
        )
        transcription = transcription_response.text
        print("Transcription complete.")

        # Prompt for summarization
        print("Summarizing text...")
        summary_response = model.generate_content(
            [f"Please provide a concise summary of the following text:\n{transcription}"]
        )
        summary = summary_response.text
        print("Summarization complete.")

        return transcription, summary

    except Exception as e:
        print(f"An error occurred with {audio_path}: {e}")
        return None, None

def process_audio_folder(api_key, input_folder, output_folder):
    """
    Processes all audio files in a given folder and saves transcriptions and summaries
    to a single output folder with distinct names.

    Args:
        api_key (str): Your Google AI API key.
        input_folder (str): The path to the folder containing audio files.
        output_folder (str): The path to the folder to save all output files.
    """
    # Create all necessary directories
    create_directory_if_not_exists(input_folder)
    create_directory_if_not_exists(output_folder)

    supported_extensions = ('.wav', '.mp3', '.flac', '.aac', '.ogg')
    audio_files = [f for f in os.listdir(input_folder) if f.lower().endswith(supported_extensions)]

    if not audio_files:
        print(f"No audio files found in '{input_folder}'. Please add audio files to this folder and run the script again.")
        return

    for filename in audio_files:
        audio_file_path = os.path.join(input_folder, filename)
        transcription, summary = transcribe_and_summarize_audio(api_key, audio_file_path)

        if transcription and summary:
            # Generate distinct filenames for transcription and summary
            base_name = Path(filename).stem
            transcription_filename = f"{base_name}.txt"
            summary_filename = f"summarize_{base_name}.txt"

            # Save the transcription file
            transcription_output_path = os.path.join(output_folder, transcription_filename)
            with open(transcription_output_path, 'w', encoding='utf-8') as f:
                f.write(transcription)
            print(f"Transcription for {filename} saved to: {transcription_output_path}")

            # Save the summary file
            summary_output_path = os.path.join(output_folder, summary_filename)
            with open(summary_output_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            print(f"Summary for {filename} saved to: {summary_output_path}\n")

if __name__ == "__main__":
    # Load environment variables from a .env file
    load_dotenv()

    # Retrieve the Gemini API key from the environment variables
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # --- Configuration ---
    # Specify the folder where your audio files are located
    audio_input_folder = "audio_files"

    # Specify the single folder for all output files
    main_output_folder = "output"
    # --- End Configuration ---

    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not found. Please create a .env file and add your API key.")
    else:
        process_audio_folder(
            GEMINI_API_KEY,
            audio_input_folder,
            main_output_folder
        )
