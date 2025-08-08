import os
import subprocess
from pathlib import Path

# --- CONFIGURATION ---
# Set the desired mode: 'audio', 'video', or 'both'.
# 'audio': Extracts and splits only the audio into MP3 chunks.
# 'video': Splits the video into smaller video chunks (no re-encoding).
# 'both':  Performs both of the above actions.
# NOTE: If an audio file is found as the source, this will automatically be treated as 'audio'.
SPLIT_MODE = 'both'  # Options: 'audio', 'video', 'both'

# Set the desired length of each chunk in minutes.
CHUNK_DURATION_MINUTES = 50

# Specify the folder where your large media file (video or audio) is located.
SOURCE_FOLDER = Path("video_to_split")

# Specify the folder where the smaller video chunks will be saved.
OUTPUT_FOLDER_VIDEO = Path("video_out")

# Specify the folder where the smaller audio chunks will be saved.
OUTPUT_FOLDER_AUDIO = Path("audio_in")
# --- END CONFIGURATION ---


def split_media():
    """
    Finds the first video or audio file in the SOURCE_FOLDER and processes it.
    - If a video file is found, it can split the video, audio, or both based on SPLIT_MODE.
    - If an audio file is found, it will only split the audio into chunks.
    """
    # --- Initial Setup ---
    SOURCE_FOLDER.mkdir(exist_ok=True)
    if SPLIT_MODE in ['video', 'both']:
        OUTPUT_FOLDER_VIDEO.mkdir(exist_ok=True)
    if SPLIT_MODE in ['audio', 'both']:
        OUTPUT_FOLDER_AUDIO.mkdir(exist_ok=True)

    if SPLIT_MODE not in ['audio', 'video', 'both']:
        print(f"Error: Invalid SPLIT_MODE '{SPLIT_MODE}'. Please choose 'audio', 'video', or 'both'.")
        return

    chunk_duration_seconds = CHUNK_DURATION_MINUTES * 60

    # --- File Discovery ---
    source_media_path = None
    source_type = None  # Will be 'video' or 'audio'
    
    video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm']
    audio_extensions = ['.mp3', '.wav', '.flac', '.m4a', '.aac']

    print(f"Searching for media files in '{SOURCE_FOLDER}'...")
    for file in SOURCE_FOLDER.iterdir():
        file_ext = file.suffix.lower()
        if file_ext in video_extensions:
            source_media_path = file
            source_type = 'video'
            break
        elif file_ext in audio_extensions:
            source_media_path = file
            source_type = 'audio'
            break
            
    if not source_media_path:
        print(f"No supported video or audio file found in the '{SOURCE_FOLDER}' directory.")
        print(f"Please add a media file ({', '.join(video_extensions)} or {', '.join(audio_extensions)}) to process.")
        return

    print(f"Found {source_type} file: '{source_media_path.name}'")

    # --- Mode Validation based on Source Type ---
    effective_mode = SPLIT_MODE
    if source_type == 'audio':
        if SPLIT_MODE == 'video':
            print("\nError: Cannot perform 'video' split on an audio file.")
            print("Please change SPLIT_MODE to 'audio'.")
            return
        # If input is audio, we can only perform audio splitting.
        effective_mode = 'audio' 
        print(f"Input is an audio file. Mode will be treated as 'audio'.")

    print(f"Effective mode: '{effective_mode}'")
    print(f"Processing into chunks of {CHUNK_DURATION_MINUTES} minutes each...")

    # --- Task Execution ---
    # Task 1: Split video (only if source is video and mode is video/both)
    if source_type == 'video' and effective_mode in ['video', 'both']:
        print("\nStarting video splitting task...")
        output_pattern_video = OUTPUT_FOLDER_VIDEO / f"{source_media_path.stem}_part_%03d{source_media_path.suffix}"
        command_video = [
            'ffmpeg', '-i', str(source_media_path), '-c', 'copy', '-map', '0',
            '-segment_time', str(chunk_duration_seconds), '-f', 'segment',
            '-reset_timestamps', '1', str(output_pattern_video)
        ]
        try:
            subprocess.run(command_video, check=True, capture_output=True, text=True)
            print("-> Successfully split the video!")
            print(f"   Video chunks saved to '{OUTPUT_FOLDER_VIDEO}'")
        except subprocess.CalledProcessError as e:
            print("-> An error occurred while splitting the video.")
            print(f"   FFmpeg Error Output:\n{e.stderr}")
        except FileNotFoundError:
            print("-> Error: 'ffmpeg' command not found. Please ensure it's installed and in your PATH.")

    # Task 2: Split audio (if mode is audio/both)
    if effective_mode in ['audio', 'both']:
        print("\nStarting audio splitting task...")
        output_pattern_audio = OUTPUT_FOLDER_AUDIO / f"{source_media_path.stem}_part_%03d.mp3"
        command_audio = [
            'ffmpeg', '-i', str(source_media_path), '-vn', '-c:a', 'libmp3lame',
            '-b:a', '192k', '-map', '0:a', '-segment_time', str(chunk_duration_seconds),
            '-f', 'segment', '-reset_timestamps', '1', str(output_pattern_audio)
        ]
        try:
            subprocess.run(command_audio, check=True, capture_output=True, text=True)
            print("-> Successfully split the audio!")
            print(f"   Audio chunks saved to '{OUTPUT_FOLDER_AUDIO}'")
        except subprocess.CalledProcessError as e:
            print("-> An error occurred while splitting the audio.")
            print(f"   FFmpeg Error Output:\n{e.stderr}")
        except FileNotFoundError:
            print("-> Error: 'ffmpeg' command not found. Please ensure it's installed and in your PATH.")
    
    print("\nProcessing complete.")


if __name__ == "__main__":
    split_media()
