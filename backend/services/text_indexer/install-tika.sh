#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly VERSION="4.0.0"
readonly ARCHIVE_NAME="tika-app-${VERSION}.zip"
readonly DOWNLOAD_URL="https://archive.apache.org/dist/tika/${VERSION}/${ARCHIVE_NAME}"
readonly CHECKSUM_FILE="${SCRIPT_DIR}/TIKA-DISTRIBUTION.sha512"
readonly TARGET_DIR="${PROJECT_DIR}/vendor/tika"
readonly TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/wathiq-tika.XXXXXX")"

cleanup() { rm -rf "${TEMP_DIR}"; }
trap cleanup EXIT INT TERM

for command_name in curl unzip; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        echo "${command_name} is required." >&2
        exit 1
    }
done

checksum() {
    if command -v sha512sum >/dev/null 2>&1; then
        sha512sum "$1" | awk '{print $1}'
    else
        shasum -a 512 "$1" | awk '{print $1}'
    fi
}

readonly ARCHIVE="${TEMP_DIR}/${ARCHIVE_NAME}"
readonly EXTRACTED="${TEMP_DIR}/extracted"
echo "Downloading the official Apache Tika ${VERSION} app distribution..."
curl --fail --location --retry 3 --output "${ARCHIVE}" "${DOWNLOAD_URL}"

readonly EXPECTED_ARCHIVE_CHECKSUM="$(awk -v name="${ARCHIVE_NAME}" '$2==name {print $1}' "${CHECKSUM_FILE}")"
readonly ACTUAL_ARCHIVE_CHECKSUM="$(checksum "${ARCHIVE}")"
if [[ -z "${EXPECTED_ARCHIVE_CHECKSUM}" || "${ACTUAL_ARCHIVE_CHECKSUM}" != "${EXPECTED_ARCHIVE_CHECKSUM}" ]]; then
    echo "Apache Tika archive checksum verification failed." >&2
    exit 1
fi

mkdir -p "${EXTRACTED}"
unzip -q "${ARCHIVE}" -d "${EXTRACTED}"
readonly APP_JAR="${EXTRACTED}/tika-app-${VERSION}.jar"
readonly FORK_JAR="${EXTRACTED}/lib/tika-pipes-fork-parser-${VERSION}.jar"
[[ -f "${APP_JAR}" ]] || { echo "The distribution is missing the application JAR." >&2; exit 1; }
[[ -f "${FORK_JAR}" ]] || { echo "The distribution is missing the fork-parser JAR." >&2; exit 1; }

readonly EXPECTED_JAR_CHECKSUM="$(awk -v name="tika-app-${VERSION}.jar" '$2==name {print $1}' "${CHECKSUM_FILE}")"
readonly ACTUAL_JAR_CHECKSUM="$(checksum "${APP_JAR}")"
if [[ -z "${EXPECTED_JAR_CHECKSUM}" || "${ACTUAL_JAR_CHECKSUM}" != "${EXPECTED_JAR_CHECKSUM}" ]]; then
    echo "Apache Tika application JAR checksum verification failed." >&2
    exit 1
fi

mkdir -p "$(dirname "${TARGET_DIR}")"
if [[ -e "${TARGET_DIR}" ]]; then
    readonly BACKUP_DIR="${TARGET_DIR}.previous.$$"
    mv "${TARGET_DIR}" "${BACKUP_DIR}"
    if ! mv "${EXTRACTED}" "${TARGET_DIR}"; then
        mv "${BACKUP_DIR}" "${TARGET_DIR}"
        exit 1
    fi
    rm -rf "${BACKUP_DIR}"
else
    mv "${EXTRACTED}" "${TARGET_DIR}"
fi
echo "Apache Tika ${VERSION} installed and verified at ${TARGET_DIR}."
