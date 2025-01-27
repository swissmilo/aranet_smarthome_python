#!/bin/bash

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install required system packages
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    bluetooth \
    bluez \
    libbluetooth-dev

# Install Python dependencies
pip install -r requirements.txt

# Set up Bluetooth permissions
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))

echo "Setup complete! You can now run the reader with: python aranet_reader.py" 