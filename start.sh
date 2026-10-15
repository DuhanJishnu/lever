#!/usr/bin/env bash

echo "Starting all three services..."

# Persistent DB: Temp\opencode\ui.db is wiped on reboot/cleanup, so use repo-local file.
# Default in src/lever/cli.py:116 is ".lever_sessions.db".
DB='D:\Lever\.lever_sessions.db'

# Single wt invocation: \; is wt's tab separator escaped for bash.
# Use -d for working directory: a ';' inside -Command would be parsed by wt
# as its own separator, which caused 0x80070002 on ' npm run dev ...'.
wt.exe new-tab --title "Llama Server" powershell.exe -NoExit -Command '& "D:\tools\llama.cpp\base\llama-server.exe" -m "D:\models\gemma-3-4b-q4km.gguf" --port 8080 -c 8192 --n-gpu-layers 99 --no-jinja' \; new-tab --title "Lever Server" -d 'D:\Lever' powershell.exe -NoExit -Command "uv run lever serve --port 8000 --db '$DB'" \; new-tab --title "Vite Server" -d 'D:\Lever\web' powershell.exe -NoExit -Command 'npm run dev -- --port 5173 --host 127.0.0.1 --strictPort'

echo "Launch commands sent."