#!/usr/bin/env bash
set -euo pipefail
: "${RCLONE_CONFIG_TEXT:?請設定 GitHub Actions Secret RCLONE_CONFIG}"
: "${DRIVE_FOLDER_ID:?請設定 GitHub Actions Variable DRIVE_FOLDER_ID}"
[[ "$DRIVE_FOLDER_ID" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Drive 資料夾 ID 格式錯誤'; exit 1; }
[[ -d cloud-publish ]] || { echo '缺少已驗證的報表'; exit 1; }
umask 077
config_dir=$(mktemp -d "${RUNNER_TEMP:-/tmp}/news-rclone.XXXXXX")
trap 'rm -rf "$config_dir"' EXIT
printf '%s' "$RCLONE_CONFIG_TEXT" > "$config_dir/rclone.conf"
export RCLONE_CONFIG="$config_dir/rclone.conf"
export RCLONE_CONFIG_GDRIVE_ROOT_FOLDER_ID="$DRIVE_FOLDER_ID"
destination="gdrive:${GITHUB_REPOSITORY##*/}/run-${GITHUB_RUN_ID}-attempt-${GITHUB_RUN_ATTEMPT}"
# copy preserves existing files; do not replace this with sync or move.
rclone copy cloud-publish "$destination" --checksum --retries 3 --low-level-retries 5
rclone check cloud-publish "$destination" --one-way
printf '\nGoogle Drive 上傳與檔案核對完成。\n' >> "$GITHUB_STEP_SUMMARY"
