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
    echo "Warning: VTS SDK (pyvitaisdk4bc) is not natively supported on macOS."
    echo "You can still run the GUI in --mock mode (e.g., python main.py --mock revo3-vision)."
    exit 1
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

# Detect pip command
PIP_CMD="pip3"
if ! command -v pip3 >/dev/null 2>&1; then
  if command -v pip >/dev/null 2>&1; then
    PIP_CMD="pip"
  else
    echo "Error: pip or pip3 not found. Please install pip."
    exit 1
  fi
fi

# Add --break-system-packages if pip supports it (for PEP 668)
PIP_FLAGS=""
if $PIP_CMD install --help | grep -q "break-system-packages"; then
  PIP_FLAGS="--break-system-packages"
fi

$PIP_CMD install $PIP_FLAGS "$WHL_URL"
echo "Done. VTS SDK (pyvitaisdk4bc) v${VERSION} installed successfully."
