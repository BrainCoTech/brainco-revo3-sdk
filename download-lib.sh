#!/bin/bash
set -e # Exit on error

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
VERSION_FILE="${SCRIPT_DIR}/VERSION"

# Configuration
LIB_VERSION="v2.0.0-rc.9"
BASE_URL="https://app.brainco.cn/universal/bc-revo3-sdk/libs/${LIB_VERSION}"

# Colorful output functions
echo_y() { printf "\033[1;33m%s\033[0m\n" "$*"; } # Yellow
echo_r() { printf "\033[0;31m%s\033[0m\n" "$*"; } # Red

# Determine platform and library name
OS_TYPE=$(uname -s)
ARCH=$(uname -m)
IS_ARM64=$([[ "$ARCH" == "aarch64" ]] && echo 1 || echo 0)
echo_y "OS type: $OS_TYPE, ARCH: $ARCH"
case "$OS_TYPE" in
"Linux")
  # 加载系统发行版信息
  if [ -f /etc/os-release ]; then
    . /etc/os-release
  fi

  # 根据系统和架构设置ZIP文件名
  if [[ "$ID" == "ubuntu" && "$VERSION_ID" == "22.04" ]]; then
    LIB_PREFIX="linux"
    # LIB_PREFIX="ubuntu-22"
  else
    LIB_PREFIX="linux"
  fi

  ARM64_SUFFIX=""
  [[ $IS_ARM64 -eq 1 ]] && ARM64_SUFFIX="-arm64"
  LIB_NAME="${LIB_PREFIX}${ARM64_SUFFIX}"
  SDK_LIBRARY_RELATIVE="shared/linux/libbc_revo3_sdk.so"
  ;;
"Darwin")
  LIB_NAME="mac"
  SDK_LIBRARY_RELATIVE="shared/mac/libbc_revo3_sdk.dylib"
  ;;
"msys" | "MINGW"*)
  LIB_NAME="win"
  SDK_LIBRARY_RELATIVE="shared/win/bc_revo3_sdk.dll"
  ;;
*)
  echo_r "Error: This script does not support your platform ($OS_TYPE)"
  exit 1
  ;;
esac

# Reuse an installation only when its version and required public artifacts match.
if [ -f "$VERSION_FILE" ] && grep -Fqx "[bc-revo3-sdk] Version: $LIB_VERSION" "$VERSION_FILE" && \
  [ -f "$DIST_DIR/include/revo3-sdk.h" ] && \
  [ -f "$DIST_DIR/include/revo3/revo3.hpp" ] && \
  [ -f "$DIST_DIR/$SDK_LIBRARY_RELATIVE" ]; then
  echo_y "[bc-revo3-sdk] (${LIB_VERSION}) is already installed"
  cat "$VERSION_FILE"
  exit 0
fi

ZIP_NAME="${LIB_NAME}.zip"
DOWNLOAD_URL="${BASE_URL}/${ZIP_NAME}?$(date +%s)" # Timestamp for uniqueness
DOWNLOAD_DIR=$(mktemp -d "$SCRIPT_DIR/.bc-revo3-sdk.XXXXXX")
ZIP_PATH="$DOWNLOAD_DIR/$ZIP_NAME"
EXTRACT_DIR="$DOWNLOAD_DIR/extract"
trap 'rm -rf "$DOWNLOAD_DIR"' EXIT
mkdir -p "$EXTRACT_DIR"

# Download library
echo_y "[bc-revo3-sdk] Downloading (${LIB_VERSION}) for ${LIB_NAME}..."

DOWNLOAD_SUCCESS=0

# 1. Try downloading with curl if available
if command -v curl >/dev/null 2>&1; then
  echo_y "Trying to download using curl..."
  if curl --fail --location --progress-bar "$DOWNLOAD_URL" -o "$ZIP_PATH"; then
    DOWNLOAD_SUCCESS=1
  else
    echo_r "Warning: curl download failed. Trying fallback options..."
  fi
fi

# 2. Try downloading with wget if curl failed or is unavailable
if [ $DOWNLOAD_SUCCESS -ne 1 ] && command -v wget >/dev/null 2>&1; then
  echo_y "Trying to download using wget..."
  if wget -q --show-progress "$DOWNLOAD_URL" -O "$ZIP_PATH"; then
    DOWNLOAD_SUCCESS=1
  else
    echo_r "Error: wget download failed."
  fi
fi

# 3. Check final download status
if [ $DOWNLOAD_SUCCESS -ne 1 ]; then
  if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    echo_r "Error: Neither curl nor wget is installed. Please install one of them and try again."
  else
    echo_r "Error: Failed to download ${ZIP_NAME} using all available tools (curl/wget)."
  fi
  exit 1
fi

# Validate and extract without modifying the current installation.
if ! unzip -tq "$ZIP_PATH" >/dev/null; then
  echo_r "Error: Downloaded file is not a valid SDK ZIP archive: ${ZIP_NAME}"
  exit 1
fi

echo_y "[bc-revo3-sdk] Extracting ${ZIP_NAME}..."
unzip -o -q "$ZIP_PATH" -d "$EXTRACT_DIR" || {
  echo_r "Error: Failed to unzip ${ZIP_NAME}"
  exit 1
}
STAGED_DIST="$EXTRACT_DIR/dist"
rm -rf "$EXTRACT_DIR/__MACOSX" "$STAGED_DIST/__MACOSX"
if [ ! -d "$STAGED_DIST/include" ]; then
  echo_r "Error: Downloaded SDK package has an invalid directory layout."
  exit 1
fi
find "$STAGED_DIST/include" \
  -type f \
  ! -name 'revo3-sdk.h' \
  ! -path "$STAGED_DIST/include/revo3/revo3.hpp" \
  ! -path "$STAGED_DIST/include/zlgcan/*" \
  -exec rm -f {} \;

if [ ! -f "$STAGED_DIST/include/revo3-sdk.h" ] || \
  [ ! -f "$STAGED_DIST/include/revo3/revo3.hpp" ] || \
  [ ! -f "$STAGED_DIST/$SDK_LIBRARY_RELATIVE" ]; then
  echo_r "Error: Downloaded SDK package is missing required public artifacts."
  exit 1
fi

echo_y "[bc-revo3-sdk] Replacing the previous validated distribution..."
PREVIOUS_DIST="$DOWNLOAD_DIR/previous-dist"
if [ -d "$DIST_DIR" ]; then
  mv "$DIST_DIR" "$PREVIOUS_DIST"
fi
if ! mv "$STAGED_DIST" "$DIST_DIR"; then
  if [ -d "$PREVIOUS_DIST" ]; then
    mv "$PREVIOUS_DIST" "$DIST_DIR"
  fi
  echo_r "Error: Failed to install the validated SDK distribution."
  exit 1
fi
rm -rf "$PREVIOUS_DIST"

case "$OS_TYPE" in
"Linux")
  # 可以拷贝到系统目录
  # sudo cp -vf dist/shared/linux/*.so /usr/lib/
  # sudo ln -s /usr/lib/libusbcanfd.so /usr/lib/libusbcanfd.so.1.0.10
  ;;
"Darwin")
  ;;
"msys" | "MINGW"*)
  mkdir -p "$SCRIPT_DIR/python/dll"
  cp -vf "$DIST_DIR"/shared/win/*.dll "$SCRIPT_DIR/python/dll/"
  ;;
esac

# Create VERSION file
echo_y "[bc-revo3-sdk] Creating version file..."
cat >"$VERSION_FILE" <<EOF
[bc-revo3-sdk] Version: ${LIB_VERSION}
Update Time: $(date)
EOF

echo_y "[bc-revo3-${LIB_NAME}-sdk] (${LIB_VERSION}) downloaded successfully to ${DIST_DIR}"
