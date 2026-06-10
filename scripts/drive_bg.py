#!/usr/bin/env python3
"""
drive_bg.py — fetch a RANDOM background video from a Google Drive folder.

Used by the render step to vary the background per reel. Everything here is best-effort:
any failure (no creds, no network, empty folder) returns None so the caller falls back to
the bundled local background loop — the pipeline must never break because Drive is down.

Auth (reuses the same convention as upload_pipeline.py):
  - GOOGLE_DRIVE_CREDENTIALS_JSON  (inline service-account JSON), OR
  - GOOGLE_DRIVE_CREDENTIALS_PATH  (path to the service-account .json; default below)
The Drive folder must be SHARED with the service-account client_email, or it sees nothing.
"""

import os
import sys
import json
import random

# Prioritise the local python_packages folder (same as the other scripts).
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_workspace = os.path.dirname(_scripts_dir)
_local_packages = os.path.join(_workspace, 'python_packages')
if os.path.exists(_local_packages) and _local_packages not in sys.path:
    sys.path.insert(0, _local_packages)

# Folder of background videos. Override with BG_DRIVE_FOLDER_ID; defaults to the configured folder.
DEFAULT_FOLDER_ID = "11rWzUxqCT1QUH8O5oygi-qz4zhfZqiDd"
DEFAULT_CREDS_PATH = os.path.join(_workspace, "drive_service_account.json")
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _load_credentials():
    """Service-account creds from inline JSON env, else a key file. Returns None if unavailable."""
    from google.oauth2 import service_account
    creds_json = os.environ.get("GOOGLE_DRIVE_CREDENTIALS_JSON", "").strip()
    if creds_json:
        return service_account.Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
    creds_path = os.environ.get("GOOGLE_DRIVE_CREDENTIALS_PATH", "").strip() or DEFAULT_CREDS_PATH
    if not os.path.exists(creds_path):
        print(f"[BG] No Drive credentials (looked for env JSON and file '{creds_path}').")
        return None
    return service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)


def download_random_background(dest_path):
    """
    Pick a random video from the Drive folder and download it to dest_path.
    Returns dest_path on success, or None on any failure (caller should fall back).
    """
    folder_id = os.environ.get("BG_DRIVE_FOLDER_ID", "").strip() or DEFAULT_FOLDER_ID
    if os.environ.get("BG_DISABLE_DRIVE") == "1":
        print("[BG] Drive background disabled via BG_DISABLE_DRIVE=1.")
        return None
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

        creds = _load_credentials()
        if creds is None:
            return None

        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        # List video files in the folder (supports Shared Drives too).
        query = f"'{folder_id}' in parents and mimeType contains 'video/' and trashed = false"
        resp = service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = resp.get("files", [])
        if not files:
            print(f"[BG] No videos found in folder {folder_id} (is it shared with the service account?).")
            return None

        chosen = random.choice(files)
        print(f"[BG] Downloading random background: {chosen['name']} ({len(files)} available)")

        request = service.files().get_media(fileId=chosen["id"])
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=5 * 1024 * 1024)
            done = False
            while not done:
                _status, done = downloader.next_chunk()
        return dest_path
    except Exception as e:
        print(f"[BG] Random background fetch failed ({e}); falling back to local loop.")
        return None


if __name__ == "__main__":
    out = download_random_background(os.path.join(_workspace, "generated-audio", "bg_random.mp4"))
    print(f"Result: {out}")
