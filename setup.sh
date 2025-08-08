#!/bin/bash

# --- Step 1: Create all necessary directories ---
echo "Creating project directories..."
mkdir -p video_to_split audio_in transcripts video_out processing temp_chunks
echo "Directories created successfully."
echo

# --- Step 2: Install Python packages from requirements.txt ---
echo "Installing Python requirements..."
pip install -r requirements.txt
echo

echo "Setup complete! ✅"
