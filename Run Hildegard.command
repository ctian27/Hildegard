#!/bin/bash
# Double-click this file to open the Hildegard GUI.
#
# It runs through Terminal, which has permission to read files in ~/Documents
# (a double-clicked .app bundle does not, which is why the .app can fail with
# "Operation not permitted"). The first time, macOS may ask Terminal for
# permission to access your Documents folder -- click Allow / OK.
#
# On first run (or on a machine it was shared to) this sets up its own Python
# environment automatically. No manual Terminal setup needed.

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

pause_and_exit() {
    echo
    read -n 1 -s -r -p "Press any key to close..."
    exit "${1:-1}"
}

if [ ! -f "$ROOT/pipeline/gui.py" ]; then
    echo "Could not find pipeline/gui.py in: $ROOT"
    echo "Keep this file inside the Hildegard project folder."
    pause_and_exit 1
fi

# On Apple Silicon, force native arm64. If Terminal happens to be running under
# Rosetta, a universal Python would otherwise launch as x86_64 and fail to load
# arm64 packages ("incompatible architecture"). No-op on Intel Macs.
if arch -arm64 /usr/bin/true 2>/dev/null; then
    ARCH="arch -arm64"
else
    ARCH=""
fi

# Need a system python3 to bootstrap.
if ! $ARCH command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required but was not found."
    echo "Install it from https://www.python.org/downloads/ and run this again."
    pause_and_exit 1
fi

VENV_PY="$ROOT/.venv/bin/python"

# (Re)create the environment if it's missing, broken, or built for the wrong
# architecture. The import check runs under the same arch we'll launch with, so
# an arch-mismatched venv (e.g. copied from another machine, or built while
# Terminal was under Rosetta) is caught and rebuilt with matching wheels.
if [ ! -x "$VENV_PY" ] || ! $ARCH "$VENV_PY" -c "import anthropic, pydantic_core, markdown, xhtml2pdf" >/dev/null 2>&1; then
    echo "First-time setup: creating the Python environment (this runs once)..."
    rm -rf "$ROOT/.venv"
    $ARCH python3 -m venv "$ROOT/.venv" || { echo "Failed to create virtual environment."; pause_and_exit 1; }
    $ARCH "$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1
    echo "Installing dependencies..."
    $ARCH "$VENV_PY" -m pip install -r "$ROOT/requirements.txt" || { echo "Failed to install dependencies."; pause_and_exit 1; }
    echo "Setup complete."
fi

# Warn (don't block) if no Anthropic API key is configured -- the GUI still
# opens and dry runs work, but live extraction needs a key in .env.
if [ ! -f "$ROOT/.env" ] || ! grep -qE '^ANTHROPIC_API_KEY=.+' "$ROOT/.env"; then
    echo
    echo "NOTE: no Anthropic API key found in .env."
    echo "      The GUI will open and 'dry run' works, but live extraction needs a key."
    echo "      Copy .env.example to .env and add ANTHROPIC_API_KEY (and NCBI_API_KEY)."
    echo
fi

echo "Launching Hildegard GUI..."
$ARCH "$VENV_PY" -m pipeline.gui
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo
    echo "GUI exited with code $STATUS."
    pause_and_exit "$STATUS"
fi
