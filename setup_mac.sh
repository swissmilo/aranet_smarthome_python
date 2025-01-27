#!/bin/bash

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Bluetooth dependencies via Homebrew
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Please install Homebrew first:"
    echo "Visit: https://brew.sh"
    exit 1
fi

# Install required system packages
brew install python3
brew install bluez

# Update pip
pip install --upgrade pip

# Install Python dependencies with a newer version of bleak
pip install -r requirements.txt

echo "Setup complete! You can now run the reader with: python aranet_reader.py" 