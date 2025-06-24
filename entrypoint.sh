#!/bin/bash

# Exit on any error
set -e

echo "Starting MinerU Server setup..."

# Download models
echo "Downloading models..."
/app/.venv/bin/python download_models_hf.py

# Start the server
echo "Starting server..."
exec /app/.venv/bin/python server.py