# TikTok + YouTube Shorts API Setup Guide

This guide walks you through setting up API access for auto-posting to TikTok and YouTube Shorts.

## Prerequisites

- Business/Creator account on TikTok
- Google Cloud Project with YouTube Data API v3 enabled
- OAuth 2.0 credentials for both platforms

---

## TikTok API Setup

### Step 1: Create TikTok Developer Account

1. Go to https://developers.tiktok.com/
2. Sign in with your TikTok account
3. Apply for a developer account (requires business verification)

### Step 2: Create a New App

1. Navigate to **My Apps** → **Create App**
2. Select **TikTok for Developers** platform
3. Fill in app details:
   - App Name: MemoryStore Auto-Poster
   - Description: Automated video posting for marketing content
   - Category: Business/Marketing
4. Submit for review (approval takes 1-3 business days)

### Step 3: Configure OAuth 2.0

1. In your app dashboard, go to **Authentication** → **OAuth 2.0**
2. Add redirect URI: `https://your-domain.com/callback` (or `http://localhost:5000/callback` for local dev)
3. Note your credentials:
   - **Client Key** (public)
   - **Client Secret** (keep private)

### Step 4: Request Upload API Access

1. Go to **Products** → **Upload API**
2. Request access (requires business justification)
3. Wait for approval (separate from app approval)

### Step 5: Get Access Token

For testing, you can get a token manually:

```
https://www.tiktok.com/auth/authorize/?client_key=YOUR_CLIENT_KEY&scope=video.upload,user.info&response_type=code&redirect_uri=YOUR_REDIRECT_URI
```

Exchange the code for tokens:

```bash
curl -X POST "https://open.tiktokapis.com/v2/oauth/token/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_key=YOUR_CLIENT_KEY&client_secret=YOUR_CLIENT_SECRET&code=AUTH_CODE&grant_type=authorization_code&redirect_uri=YOUR_REDIRECT_URI"
```

### Step 6: Configure Environment Variables

Add to your `.env` file:

```bash
# TikTok Configuration
TIKTOK_CLIENT_KEY=your_client_key_here
TIKTOK_CLIENT_SECRET=your_client_secret_here
TIKTOK_ACCESS_TOKEN=your_access_token_here
TIKTOK_ENABLED=true
```

---

## YouTube Shorts API Setup

### Step 1: Create Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Create a new project: **MemoryStore Marketing**
3. Enable billing (required for API quota)

### Step 2: Enable YouTube Data API v3

1. Go to **APIs & Services** → **Library**
2. Search for "YouTube Data API v3"
3. Click **Enable**

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** user type
3. Fill in required fields:
   - App name: MemoryStore Auto-Poster
   - User support email: your-email@company.com
   - Developer contact: your-email@company.com
4. Add scopes:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube`
5. Add test users (for development)

### Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Application type: **Web application**
4. Add authorized redirect URIs:
   - `http://localhost:5000/oauth2callback` (local dev)
   - `https://your-domain.com/oauth2callback` (production)
5. Download the credentials JSON

### Step 5: Get Access Token

Run the OAuth flow or use the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/):

1. Select YouTube Data API v3 scopes
2. Authorize with your Google account
3. Exchange authorization code for tokens
4. Copy the **Access Token** and **Refresh Token**

### Step 6: Configure Environment Variables

Add to your `.env` file:

```bash
# YouTube Configuration
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here
YOUTUBE_ACCESS_TOKEN=your_access_token_here
YOUTUBE_REFRESH_TOKEN=your_refresh_token_here
YOUTUBE_ENABLED=true
```

---

## Testing the Integration

### Test TikTok Upload

```python
from tiktok_poster import post_to_tiktok

result = post_to_tiktok(
    video_path="path/to/your/video.mp4",
    caption="Test upload #shorts #test",
    privacy_level="PUBLIC_TO_EVERYONE"
)

print(result)
```

### Test YouTube Shorts Upload

```python
from youtube_poster import post_to_youtube_shorts

result = post_to_youtube_shorts(
    video_path="path/to/your/video.mp4",
    title="Test Video #Shorts",
    description="This is a test upload",
    tags=["test", "shorts"],
    privacy_status="public"
)

print(result)
```

---

## API Quotas and Limits

### TikTok Upload API
- **Daily upload limit**: 100 videos per app (during beta)
- **Max video size**: 500MB
- **Max video duration**: 10 minutes
- **Supported formats**: MP4, MOV

### YouTube Data API
- **Daily quota**: 10,000 units (default)
- **Upload cost**: ~1,600 units per video
- **Max videos per day**: ~6 uploads on free tier
- **Max video size**: 256GB
- **Max video duration**: 12 hours
- **Shorts requirement**: Must be vertical (9:16) and ≤60 seconds

**Note**: To increase YouTube quota, request a quota extension at https://developers.google.com/youtube/v3/getting-started#quota

---

## Troubleshooting

### TikTok Issues

**"Invalid access token"**
- Token expired (TikTok tokens last 24 hours)
- Refresh using the refresh token or re-authorize

**"Upload API not approved"**
- Wait for Upload API access approval
- Contact TikTok developer support

**"Video format not supported"**
- Convert to MP4 with H.264 codec
- Ensure aspect ratio is 9:16 for Shorts

### YouTube Issues

**"Quota exceeded"**
- Wait 24 hours for quota reset
- Request quota increase from Google
- Reduce upload frequency

**"Authentication failed"**
- Check if access token is expired
- Use refresh token to get new access token
- Verify OAuth consent screen is configured

**"Video processing failed"**
- Check video format (MP4 with H.264 recommended)
- Ensure video meets Shorts requirements (vertical, ≤60s)
- Verify file size is within limits

---

## Production Deployment

### Token Refresh Automation

For production, implement automatic token refresh:

```python
# In your deployment script
def refresh_tiktok_token():
    # Call TikTok OAuth token refresh endpoint
    pass

def refresh_youtube_token():
    # Use google.auth library with refresh token
    pass

# Schedule daily refresh
```

### Security Best Practices

1. **Never commit tokens to git**
2. Use environment variables or secret management (AWS Secrets Manager, etc.)
3. Rotate tokens monthly
4. Monitor API usage in developer dashboards
5. Set up alerts for quota warnings

---

## Next Steps

Once configured:
1. Test with a small video file
2. Verify posting succeeds on both platforms
3. Enable in production by setting `TIKTOK_ENABLED=true` and `YOUTUBE_ENABLED=true`
4. Monitor the first few automated posts
5. Check platform analytics for engagement metrics

For issues, check:
- TikTok: https://developers.tiktok.com/support
- YouTube: https://developers.google.com/youtube/v3/support
