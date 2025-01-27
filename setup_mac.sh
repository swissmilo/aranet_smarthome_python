#!/bin/bash

# Check if pip3 is installed
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not installed. Please install it first."
    exit 1
fi

# Install required packages using pip3
echo "Installing required packages..."
pip3 install -r requirements.txt

# Install system-level dependencies if needed
if ! command -v brew &> /dev/null; then
    echo "Homebrew is not installed. Please install it first."
    echo "Visit https://brew.sh for installation instructions."
    exit 1
fi

# Install bluetooth dependencies
echo "Installing bluetooth dependencies..."
brew install bluez

echo "Setup completed successfully!" 