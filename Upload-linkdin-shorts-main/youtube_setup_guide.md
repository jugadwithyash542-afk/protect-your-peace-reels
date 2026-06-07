# YouTube Shorts API Setup Guide

## Overview
This guide walks you through setting up YouTube Data API v3 access for automatic Shorts posting.

## Prerequisites
- Google Account
- YouTube channel
- Google Cloud Project

## Step 1: Create Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Click "Select a project" → "New Project"
3. Name: MemoryStore Auto-Poster
4. Click "Create"

## Step 2: Enable YouTube Data API v3

1. In your project, go to "APIs & Services" → "Library"
2. Search for "YouTube Data API v3"
3. Click on it and press "Enable"

## Step 3: Configure OAuth Consent Screen

1. Go to "APIs & Services" → "OAuth consent screen"
2. Select "External" user type (unless you have Google Workspace)
3. Fill in required fields:
   - App name: MemoryStore Auto-Poster
   - User support email: your-email@example.com
   - Developer contact email: your-email@example.com
4. Click "Save and Continue"
5. Add scopes (Step 2):
   - Click "Add or Remove Scopes"
   - Add: `https://www.googleapis.com/auth/youtube.upload`
   - Add: `https://www.googleapis.com/auth/youtube`
   - Click "Update" → "Save and Continue"
6. Add test users (for development):
   - Click "Add Users"
   - Add your Google account email
   - Click "Save and Continue"

## Step 4: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Web application"
4. Name: MemoryStore Auto-Poster Client
5. Authorized redirect URIs:
   - For local development: `http://localhost:5000/auth/youtube/callback`
   - For production: `https://yourdomain.com/auth/youtube/callback`
6. Click "Create"
7. Download the JSON file or copy:
   - **Client ID**
   - **Client Secret**

## Step 5: Get Access Token and Refresh Token

### Option A: Use Google's OAuth 2.0 Playground (Easiest for Testing)

1. Go to https://developers.google.com/oauthplayground/
2. Click the gear icon (⚙️) in the top right
3. Check "Use your own OAuth credentials"
4. Enter your Client ID and Client Secret
5. Close the settings
6. In "Step 1", find and select:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube`
7. Click "Authorize APIs"
8. Sign in with your Google account and grant permissions
9. In "Step 2", click "Exchange authorization code for tokens"
10. Copy:
    - **Access token** (expires in 1 hour)
    - **Refresh token** (use this to get new access tokens)

### Option B: Use Python Script

Create a script to get tokens:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

# Define scopes
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube'
]

# Create flow
flow = InstalledAppFlow.from_client_secrets_file(
    'client_secret.json',  # Download from Google Cloud Console
    SCOPES
)

# Run OAuth flow
credentials = flow.run_local_server(port=5000)

# Print tokens
print(f"Access Token: {credentials.token}")
print(f"Refresh Token: {credentials.refresh_token}")
```

## Step 6: Configure Environment Variables

Add these to your `.env` file:

```bash
# YouTube API Configuration
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here
YOUTUBE_ACCESS_TOKEN=your_access_token_here
YOUTUBE_REFRESH_TOKEN=your_refresh_token_here
YOUTUBE_ENABLED=true
```

## Step 7: Test the Integration

Run the autopost endpoint:
```bash
curl -X POST "http://localhost:5000/autopost?api_key=YOUR_API_KEY&sync=true"
```

Check logs for YouTube posting status:
```
📺 AUTOPOST: Posting to YouTube Shorts...
✅ AUTOPOST: Posted to YouTube Shorts! Video ID: abc123XYZ
  → YouTube: URL: https://youtube.com/shorts/abc123XYZ
```

## YouTube Shorts Specifications

For optimal Shorts performance:

- **Aspect Ratio:** 9:16 (vertical) or 1:1 (square)
- **Resolution:** 1080x1920 pixels (minimum 720x1280)
- **Duration:** Under 60 seconds (optimal: 15-45 seconds)
- **File Size:** Maximum 256 MB
- **Format:** MP4 (H.264 video codec, AAC audio codec)
- **Title:** Include #Shorts for better discovery

## Token Refresh

Access tokens expire after 1 hour. To refresh:

```python
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

credentials = Credentials(
    token=ACCESS_TOKEN,
    refresh_token=REFRESH_TOKEN,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    token_uri='https://oauth2.googleapis.com/token'
)

# Refresh if expired
if credentials.expired and credentials.refresh_token:
    credentials.refresh(Request())
    new_access_token = credentials.token
    # Update your .env file with new token
```

## Troubleshooting

### Error: "Token expired"
- Use the refresh token to get a new access token
- Access tokens last 1 hour
- Refresh tokens don't expire unless revoked

### Error: "Quota exceeded"
- YouTube API has a daily quota of 10,000 units
- Video upload costs ~1,600 units
- You can upload ~6 videos per day on free tier
- Request quota increase in Google Cloud Console

### Error: "Video format not supported"
- Ensure video is MP4 format
- Check aspect ratio (9:16 for Shorts)
- Verify duration is under 60 seconds

### Error: "Channel not verified"
- Your YouTube channel may need phone verification
- Go to youtube.com/verify to complete verification
- Some features require channel verification

## API Quotas

Default quota: 10,000 units per day

Common operations:
- Video upload: ~1,600 units
- Video update: 50 units
- Comment insert: 50 units
- Channel info: 1 unit

**You can upload approximately 6 videos per day on the free tier.**

To request a quota increase:
1. Go to Google Cloud Console
2. Navigate to "APIs & Services" → "Dashboard"
3. Click "YouTube Data API v3"
4. Click "Request higher quota"

## References

- YouTube Data API v3: https://developers.google.com/youtube/v3
- Upload Video Guide: https://developers.google.com/youtube/v3/guides/uploading_a_video
- API Quotas: https://developers.google.com/youtube/v3/getting-started#quota
- Shorts Best Practices: https://support.google.com/youtube/answer/10133694
