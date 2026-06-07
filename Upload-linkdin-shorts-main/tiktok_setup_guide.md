# TikTok API Setup Guide

## Overview
This guide walks you through setting up TikTok API access for automatic video posting.

## Prerequisites
- TikTok Developer Account
- TikTok Business or Creator account (for API access)
- App approved by TikTok

## Step 1: Create TikTok Developer Account

1. Go to https://developers.tiktok.com/
2. Sign up or log in with your TikTok account
3. Complete developer verification (may require business documentation)

## Step 2: Create a New App

1. Navigate to "My Apps" → "Create App"
2. Select app type: "Business" or "Creator Tools"
3. Fill in app details:
   - App Name: MemoryStore Auto-Poster
   - Description: Automated video posting for content distribution
   - Category: Business/Marketing
   - Website: Your company website
   - Redirect URI: `https://localhost:5000/auth/tiktok/callback` (for local dev)

## Step 3: Request API Permissions

Your app needs these permissions:
- `video.upload` - Upload videos to TikTok
- `video.publish` - Publish uploaded videos
- `user.info.basic` - Get basic user info (optional)

**Important:** TikTok requires app review for most permissions. This can take 3-5 business days.

## Step 4: Get Credentials

After app approval:
1. Go to your app dashboard
2. Navigate to "Credentials" or "App Settings"
3. You'll find:
   - **Client Key** (also called App Key)
   - **Client Secret** (also called App Secret)

## Step 5: Configure Environment Variables

Add these to your `.env` file:

```bash
# TikTok API Configuration
TIKTOK_CLIENT_KEY=your_client_key_here
TIKTOK_CLIENT_SECRET=your_client_secret_here
TIKTOK_ACCESS_TOKEN=your_access_token_here
TIKTOK_ENABLED=true
```

## Step 6: Get Access Token

### Option A: OAuth Flow (Recommended for Production)

1. Direct users to:
```
https://www.tiktok.com/v2/auth/authorize/?
  client_key=YOUR_CLIENT_KEY&
  redirect_uri=YOUR_REDIRECT_URI&
  state=random_state_string&
  response_type=code&
  scope=user.info.basic,video.upload,video.publish
```

2. After user authorization, TikTok redirects to your `redirect_uri` with a `code` parameter

3. Exchange code for access token:
```bash
curl -X POST "https://open.tiktokapis.com/v2/oauth/token/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_key=YOUR_CLIENT_KEY" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "code=CODE_FROM_REDIRECT" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=YOUR_REDIRECT_URI"
```

### Option B: Personal Access Token (For Testing)

1. Go to TikTok Developer Dashboard
2. Navigate to "My Apps" → Your App → "Access Tokens"
3. Generate a personal access token with required scopes
4. **Note:** Personal tokens expire and are for testing only

## Step 7: Test the Integration

Run the autopost endpoint:
```bash
curl -X POST "http://localhost:5000/autopost?api_key=YOUR_API_KEY&sync=true"
```

Check logs for TikTok posting status:
```
🎵 AUTOPOST: Posting to TikTok...
✅ AUTOPOST: Posted to TikTok! Video ID: 123456789
```

## Troubleshooting

### Error: "Invalid access token"
- Token may have expired (TikTok tokens typically last 24 hours)
- Refresh token using the OAuth refresh flow
- Ensure scopes match the permissions you requested

### Error: "Video format not supported"
- TikTok requires MP4 format
- Maximum file size: 256 MB
- Recommended: 9:16 aspect ratio for Shorts/Reels
- Duration: 15-60 seconds optimal

### Error: "App not approved"
- Wait for TikTok to review and approve your app
- Check app status in developer dashboard
- Ensure all required permissions are requested

## API Limits

- **Upload limit:** 100 videos per day per app
- **Rate limit:** 100 requests per minute
- **File size:** Maximum 256 MB
- **Duration:** 3 seconds to 10 minutes (Shorts: under 60 seconds)

## References

- TikTok Upload API: https://developers.tiktok.com/doc/upload-api
- TikTok API Documentation: https://developers.tiktok.com/doc/
- Video Best Practices: https://developers.tiktok.com/doc/posting-video-best-practices
