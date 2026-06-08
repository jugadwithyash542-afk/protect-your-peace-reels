#!/usr/bin/env python3
"""
fetch_reels.py — Pull the last N reels and their engagement from the Instagram Graph API.

Run from the folder that contains your .env file:

    pip install requests python-dotenv
    python fetch_reels.py

Outputs:
    - reels_engagement.csv   (one row per reel)
    - prints a readable summary table to the terminal

Requirements:
    - .env must contain INSTAGRAM_ACCESS_TOKEN=...
    - The token must belong to a Business/Creator IG account with
      instagram_basic + instagram_manage_insights permissions.
"""

import csv
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime

# Global configuration variables
GRAPH = "https://graph.facebook.com/v22.0"
IG_GRAPH = "https://graph.instagram.com/v22.0"
NUM_REELS = 7
TOKEN = None

# Track if we had a permission error fetching insights
had_insight_permission_error = False

class GraphAPIError(Exception):
    """Exception raised for Instagram Graph API errors."""
    def __init__(self, message, error_data=None):
        super().__init__(message)
        self.error_data = error_data or {}


def load_env_fallback():
    """Manually parse .env file if python-dotenv is not installed."""
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            val = parts[1].strip()
                            # Strip quotes if present
                            if val.startswith(('"', "'")) and val.endswith(val[0]):
                                val = val[1:-1]
                            os.environ.setdefault(key, val)
        except Exception:
            pass


try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env from the current directory
except ImportError:
    load_env_fallback()


def _get(url, params):
    """Single GET using urllib that surfaces Graph API errors instead of failing silently."""
    params = {**params, "access_token": TOKEN}
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"
    
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            error_data = json.loads(e.read().decode("utf-8"))
            if "error" in error_data:
                raise GraphAPIError(
                    f"Graph API error from {url}: {error_data['error'].get('message')}",
                    error_data["error"]
                )
        except GraphAPIError:
            raise
        except Exception:
            pass
        raise GraphAPIError(f"HTTP Error {e.code} calling {url}: {e.reason}")
    except Exception as e:
        raise GraphAPIError(f"Failed to connect to {url}: {e}")


def resolve_ig_user_id():
    """
    Find the Instagram Business account ID the token can act on.

    First checks if INSTAGRAM_ACCOUNT_ID is already present in the environment/dotenv.
    Otherwise, tries the Facebook-Login path and falls back to Instagram-Login path.
    """
    env_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if env_id:
        return env_id

    # tried1: Facebook Login for Business -> /me/accounts -> page.instagram_business_account
    try:
        pages = _get(f"{GRAPH}/me/accounts",
                     {"fields": "name,instagram_business_account"}).get("data", [])
        for page in pages:
            iba = page.get("instagram_business_account")
            if iba:
                return iba["id"]
    except GraphAPIError:
        pass  # fall through to the Instagram-Login path

    # tried2: Instagram API with Instagram Login -> /me is itself the IG user
    try:
        me = _get(f"{IG_GRAPH}/me", {"fields": "id,username"})
        if me.get("id"):
            return me["id"]
    except GraphAPIError:
        pass

    raise SystemExit("Could not resolve an Instagram Business account from this token. "
                     "Please ensure INSTAGRAM_ACCOUNT_ID is set in your .env file.")


def fetch_reels(ig_user_id, want=NUM_REELS):
    """
    Return the most recent `want` reels.

    # ISSUE: /media returns ALL media types (images, carousels, reels) mixed together,
    #         so we over-fetch then filter to media_product_type == REELS.
    """
    fields = "id,caption,media_product_type,permalink,timestamp,like_count,comments_count"
    try:
        media = _get(f"{GRAPH}/{ig_user_id}/media",
                     {"fields": fields, "limit": 50}).get("data", [])
    except GraphAPIError as e:
        raise SystemExit(f"ERROR: Failed to fetch reels: {e}")
    
    reels = [m for m in media if m.get("media_product_type") == "REELS"]
    return reels[:want]


def fetch_insights(media_id):
    """
    Pull per-reel insight metrics, degrading gracefully if Meta rejects a metric name.

    # PAST: A single fixed metric list was used.
    # ISSUE: Meta renames/deprecates reel metrics often (e.g. plays -> views in v21),
    #        and one bad name fails the whole request.
    # PRESENT: Request a full set, and on error retry with a known-safe subset.
    # RATIONALE: Keeps the script working across API versions without manual edits.
    """
    global had_insight_permission_error
    full = "views,reach,likes,comments,shares,saved,total_interactions," \
           "ig_reels_avg_watch_time,ig_reels_video_view_total_time,reels_skip_rate"
    safe = "reach,likes,comments,shares,saved,total_interactions"
    for metrics in (full, safe):
        try:
            data = _get(f"{GRAPH}/{media_id}/insights", {"metric": metrics})["data"]
            return {row["name"]: row["values"][0]["value"] for row in data}
        except GraphAPIError as e:
            err = e.error_data
            if err.get("code") == 10 or "permission" in err.get("message", "").lower():
                had_insight_permission_error = True
            continue
    return {}


def ms_to_sec(v):
    """Watch-time metrics come back in milliseconds; show seconds."""
    try:
        return round(int(v) / 1000, 1)
    except (TypeError, ValueError):
        return ""


def main():
    global TOKEN
    TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not TOKEN:
        sys.exit("ERROR: INSTAGRAM_ACCESS_TOKEN not found in .env or environment.")

    ig_id = resolve_ig_user_id()
    print(f"Instagram account ID: {ig_id}\n")

    reels = fetch_reels(ig_id)
    if not reels:
        sys.exit("No reels found on this account.")

    rows = []
    for r in reels:
        ins = fetch_insights(r["id"])
        rows.append({
            "date": r.get("timestamp", "")[:10],
            "caption": (r.get("caption") or "").replace("\n", " ")[:60],
            "views": ins.get("views", ""),
            "reach": ins.get("reach", ""),
            "likes": ins.get("likes", r.get("like_count", "")),
            "comments": ins.get("comments", r.get("comments_count", "")),
            "shares": ins.get("shares", ""),
            "saves": ins.get("saved", ""),
            "interactions": ins.get("total_interactions", ""),
            "avg_watch_s": ms_to_sec(ins.get("ig_reels_avg_watch_time")),
            "skip_rate": ins.get("reels_skip_rate", ""),
            "permalink": r.get("permalink", ""),
        })

    # Write CSV
    fieldnames = list(rows[0].keys())
    with open("reels_engagement.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Print readable table
    cols = ["date", "views", "reach", "likes", "comments", "shares", "saves",
            "interactions", "avg_watch_s", "skip_rate", "caption"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    line = "  ".join(c.ljust(widths[c]) for c in cols)
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))

    print(f"\nSaved {len(rows)} reels -> reels_engagement.csv")

    if had_insight_permission_error:
        print("\nWARNING: Detailed insights (views, reach, shares, saves, watch time, skip rate) could not be fetched.")
        print("This is because the INSTAGRAM_ACCESS_TOKEN does not have 'instagram_manage_insights' permission.")
        print("Basic engagement metrics (likes, comments) were still successfully fetched directly.")


if __name__ == "__main__":
    main()
