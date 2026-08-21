#!/bin/bash
set -e

# BrainCo VTS SDK - Install pyvitaisdk4bc from OSS
# Detects OS and installs the appropriate wheel (Linux x86_64 or Windows amd64)

VERSION="1.0.10"
OSS_BASE="https://focus-resource.oss-cn-beijing.aliyuncs.com/universal/bc-stark-sdk/libs/vts"

echo "Detecting platform for VTS SDK..."

# Detect platform
OS=$(uname -s)
ARCH=$(uname -m)

case "$OS" in
  Linux)
    if [ "$ARCH" = "x86_64" ]; then
      PLATFORM="linux_x86_64"
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
      PLATFORM="linux_aarch64"
    else
      echo "Unsupported Linux architecture for VTS: $ARCH. Only x86_64 and aarch64/arm64 are supported."
      exit 1
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*)
    PLATFORM="win_amd64"
    ;;
  Darwin)
    if [ "$ARCH" = "arm64" ]; then
      PLATFORM="macosx_11_0_arm64"
    else
      echo "Warning: VTS SDK (pyvitaisdk4bc) is not natively supported on macOS x86_64."
      echo "You can still run the standalone VisionTouch window with its built-in mock fallback."
      exit 1
    fi
    ;;
  *)
    # Windows native cmd/git bash fallback check
    if [[ "$OS" == *"Windows"* ]]; then
      PLATFORM="win_amd64"
    else
      echo "Unsupported OS: $OS"
      exit 1
    fi
    ;;
esac

WHL_NAME="pyvitaisdk4bc-${VERSION}-py3-none-${PLATFORM}.whl"
WHL_URL="${OSS_BASE}/${WHL_NAME}"

echo "Selected wheel: $WHL_NAME"
echo "Downloading and installing from: $WHL_URL"

# Detect Python and pip command from the active environment.
PYTHON_CMD=""
if command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
else
  echo "Error: python or python3 not found. Please activate a Python 3.10+ environment."
  exit 1
fi

if ! "$PYTHON_CMD" - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit(1)
PY
then
  echo "Error: VTS SDK (pyvitaisdk4bc) requires Python 3.10 or newer."
  echo "Current Python:"
  "$PYTHON_CMD" --version || true
  echo "Please activate a Python 3.10+ environment, for example: conda activate py310"
  exit 1
fi

PIP_CMD="$PYTHON_CMD -m pip"

# Optional extra pip flags.
#
# Do not probe `pip install --help` here: on some Windows terminals, pip's rich
# help renderer can fail before installation starts. PEP 668 environments can
# pass this explicitly, for example:
#   PIP_FLAGS="--break-system-packages" bash python/install_vts_whl.sh
PIP_FLAGS="${PIP_FLAGS:-}"

install_from_local_wheel() {
  TMP_DIR="$(mktemp -d)"
  WHL_PATH="${TMP_DIR}/${WHL_NAME}"

  echo "Direct pip install failed. Trying to download the wheel first..."
  if command -v curl >/dev/null 2>&1; then
    curl -L --retry 3 --fail -o "$WHL_PATH" "$WHL_URL"
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \
      "Invoke-WebRequest -Uri '$WHL_URL' -OutFile '$WHL_PATH'"
  elif command -v python >/dev/null 2>&1; then
    python - "$WHL_URL" "$WHL_PATH" <<'PY'
import sys
import urllib.request

urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
PY
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "$WHL_URL" "$WHL_PATH" <<'PY'
import sys
import urllib.request

urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
PY
  else
    echo "Error: curl, powershell.exe, python, or python3 is required for fallback download."
    return 1
  fi

  $PIP_CMD install $PIP_FLAGS "$WHL_PATH"
}

print_network_help() {
  cat <<'EOF'

Install failed. If you are on Windows and see:
  ValueError: check_hostname requires server_hostname

This is usually caused by an invalid HTTP_PROXY/HTTPS_PROXY setting or an old
pip/requests proxy stack. Try one of the following in PowerShell:

  conda activate <your-env>
  python -m pip install --upgrade pip
  Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
  Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue

Then run this script again.

If your network requires a proxy, make sure the proxy URL includes scheme,
host, and port, for example:

  $env:HTTPS_PROXY="http://127.0.0.1:7890"
  $env:HTTP_PROXY="http://127.0.0.1:7890"

EOF
}

if ! $PIP_CMD install $PIP_FLAGS "$WHL_URL"; then
  if ! install_from_local_wheel; then
    print_network_help
    exit 1
  fi
fi

echo "Done. VTS SDK (pyvitaisdk4bc) v${VERSION} installed successfully."
