#!/bin/bash
set -e

# BrainCo Revo3 SDK - Install .whl from OSS
# Usage: bash install_whl.sh [version]
# Example: bash install_whl.sh 2.0.0-rc.6

OSS_BASE="https://app.brainco.cn/universal/bc-revo3-sdk/libs"

# Get version from argument, or default
if [ -n "$1" ]; then
  VERSION="$1"
else
  VERSION="2.0.0-rc.6"
fi

# Cargo prerelease versions use SemVer spelling while wheel filenames use
# their normalized PEP 440 spelling.
WHEEL_VERSION=$(printf '%s' "$VERSION" | sed -E \
  -e 's/-rc\.([0-9]+)$/rc\1/' \
  -e 's/-beta\.([0-9]+)$/b\1/' \
  -e 's/-alpha\.([0-9]+)$/a\1/')

echo "Installing bc-revo3-sdk v${VERSION}..."

# Detect platform
OS=$(uname -s)
ARCH=$(uname -m)

case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64) PLATFORM="macosx_11_0_arm64" ;;
      x86_64) PLATFORM="macosx_10_12_x86_64" ;;
      *) echo "Unsupported macOS arch: $ARCH"; exit 1 ;;
    esac
    ;;
  Linux)
    case "$ARCH" in
      x86_64) PLATFORM="manylinux_2_31_x86_64" ;;
      aarch64) PLATFORM="manylinux_2_31_aarch64" ;;
      *) echo "Unsupported Linux arch: $ARCH"; exit 1 ;;
    esac
    ;;
  MINGW*|MSYS*|CYGWIN*)
    PLATFORM="win_amd64"
    ;;
  *)
    echo "Unsupported OS: $OS"
    exit 1
    ;;
esac

# abi3-cp310 is compatible with Python 3.10+.
WHL_NAME="bc_revo3_sdk-${WHEEL_VERSION}-cp310-abi3-${PLATFORM}.whl"
WHL_URL="${OSS_BASE}/v${VERSION}/${WHL_NAME}"

# Check if file exists before downloading
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --head "$WHL_URL" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
  echo "Error: v${VERSION} not found on OSS (HTTP $HTTP_CODE)"
  echo "URL: $WHL_URL"
  echo ""
  echo "Try: pip3 install bc-revo3-sdk==${VERSION}  (from PyPI)"
  exit 1
fi

echo "Downloading: $WHL_URL"
# Add --break-system-packages if pip supports it (for PEP 668)
PIP_FLAGS=""
if pip3 install --help | grep -q "break-system-packages"; then
  PIP_FLAGS="--break-system-packages"
fi

pip3 install $PIP_FLAGS "$WHL_URL"
echo "Done. bc-revo3-sdk v${VERSION} installed."
