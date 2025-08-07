import os
import subprocess
from pathlib import Path

# --- CONFIGURATION ---
# Set the desired length of each video chunk in minutes.
# You can change this value as needed.
CHUNK_DURATION_MINUTES = 50

# Specify the folder where your large video file is located.
SOURCE_FOLDER = Path("video_to_split")

# Specify the folder where the smaller video chunks will be saved.
OUTPUT_FOLDER = Path("audio_in")
# --- END CONFIGURATION ---


def split_video():
    """
    Finds the first video in the SOURCE_FOLDER and splits it into chunks
    of a specified duration, saving them to the OUTPUT_FOLDER.
    """
    # Create necessary directories
    SOURCE_FOLDER.mkdir(exist_ok=True)
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    
    # Convert chunk duration from minutes to seconds for ffmpeg
    chunk_duration_seconds = CHUNK_DURATION_MINUTES * 60

    # Find the first video file in the source folder
    source_video_path = None
    for file in SOURCE_FOLDER.iterdir():
        # Add other video extensions if needed
        if file.suffix.lower() in ['.mp4', '.mkv', '.mov', '.avi']:
            source_video_path = file
            break
            
    if not source_video_path:
        print(f"No video file found in the '{SOURCE_FOLDER}' directory.")
        print("Please add the large video you want to split into that folder and run again.")
        return

    print(f"Found video file: '{source_video_path.name}'")
    print(f"Splitting into chunks of {CHUNK_DURATION_MINUTES} minutes each...")

    # Define the output filename pattern
    # Example: if source is 'my_long_video.mp4', chunks will be 'my_long_video_part_001.mp4', etc.
    output_pattern = OUTPUT_FOLDER / f"{source_video_path.stem}_part_%03d{source_video_path.suffix}"

    # Construct and run the ffmpeg command
    # This command is highly efficient as it copies the video/audio streams without re-encoding
    command = [
        'ffmpeg',
        '-i', str(source_video_path),  # Input file
        '-c', 'copy',                 # Copy codecs to prevent re-encoding (fast)
        '-map', '0',                  # Map all streams
        '-segment_time', str(chunk_duration_seconds), # Duration of each chunk
        '-f', 'segment',              # Use the segment muxer
        '-reset_timestamps', '1',     # Reset timestamps for each chunk
        str(output_pattern)           # Output file pattern
    ]
    
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print("\nSuccessfully split the video!")
        print(f"The smaller chunks have been saved to the '{OUTPUT_FOLDER}' directory.")
        print("You can now run your transcription script daily on one of these chunks.")
    except subprocess.CalledProcessError as e:
        print("\nAn error occurred while running ffmpeg.")
        print("Please ensure ffmpeg is installed correctly.")
        print(f"Error details:\n{e.stderr}")
    except FileNotFoundError:
        print("\nError: 'ffmpeg' command not found.")
        print("Please make sure ffmpeg is installed on your system and accessible in your PATH.")


if __name__ == "__main__":
    split_video()
