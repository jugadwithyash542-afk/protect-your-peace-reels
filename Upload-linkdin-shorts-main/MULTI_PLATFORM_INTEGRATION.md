# Multi-Platform Auto-Posting Integration

## Overview

The auto-posting pipeline now supports **7 platforms** for automatic short-form video distribution:

1. ✅ **LinkedIn** - Professional network
2. ✅ **Instagram Reels** - Meta platform
3. ✅ **Threads** - Meta text/video platform
4. ✅ **Facebook** - Meta social network
5. ✅ **Twitter/X** - X platform
6. ✅ **TikTok** - Short-form video platform (NEW)
7. ✅ **YouTube Shorts** - Google video platform (NEW)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Overnight Pipeline                        │
│  (generate_overnight.py)                                    │
│  - Generates scripts across 8 viral genres                  │
│  - Renders TTS audio (CosyVoice3, Qwen3, or macOS say)      │
│  - Outputs to: output/overnight/{genre}/                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
              Scripts + Audio files ready
                          ↓
┌─────────────────────────────────────────────────────────────┐
│              Manual Upload to Google Drive                  │
│  - Upload to AUTOPOST_FOLDER_ID                             │
│  - Trigger: /autopost endpoint                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│              Auto-Posting Pipeline (app.py)                 │
│  1. Select random video from AUTOPOST_FOLDER_ID             │
│  2. Generate AI description with Gemini                     │
│  3. Post to all 7 platforms in parallel                     │
│  4. Post top comment on each platform                       │
│  5. Move video to Posted_Videos folder                      │
└─────────────────────────────────────────────────────────────┘
```

## New Files Added

### Platform Posters

1. **tiktok_poster.py** - TikTok API integration
   - `post_to_tiktok(video_path, caption)` - Main interface
   - Handles chunked upload, status polling, and publishing
   - Requires: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN`

2. **youtube_poster.py** - YouTube Shorts API integration
   - `post_to_youtube_shorts(video_path, caption, top_comment)` - Main interface
   - Uses resumable upload for reliability
   - Auto-adds #Shorts hashtag for better discovery
   - Requires: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_ACCESS_TOKEN`, `YOUTUBE_REFRESH_TOKEN`

### Setup Guides

3. **tiktok_setup_guide.md** - Complete TikTok API setup
4. **youtube_setup_guide.md** - Complete YouTube API setup

## Configuration

Add these environment variables to your `.env` file:

```bash
# TikTok Configuration
TIKTOK_CLIENT_KEY=your_client_key_here
TIKTOK_CLIENT_SECRET=your_client_secret_here
TIKTOK_ACCESS_TOKEN=your_access_token_here
TIKTOK_ENABLED=true  # Set to false to disable TikTok posting

# YouTube Configuration
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here
YOUTUBE_ACCESS_TOKEN=your_access_token_here
YOUTUBE_REFRESH_TOKEN=your_refresh_token_here
YOUTUBE_ENABLED=true  # Set to false to disable YouTube posting
```

## Usage

### Trigger Auto-Post

The autopost endpoint automatically posts to all enabled platforms:

```bash
# Async mode (returns immediately)
curl -X POST "http://localhost:5000/autopost?api_key=YOUR_API_KEY"

# Sync mode (wait for completion)
curl -X POST "http://localhost:5000/autopost?api_key=YOUR_API_KEY&sync=true"

# Browser (shows HTML result)
curl "http://localhost:5000/autopost?api_key=YOUR_API_KEY&format=html"
```

### Check Status

```bash
curl "http://localhost:5000/autopost/status?api_key=YOUR_API_KEY"
```

## Platform-Specific Notes

### TikTok
- **File size limit:** 256 MB
- **Duration:** 3 seconds to 10 minutes (optimal: 15-60 seconds)
- **Format:** MP4
- **Quota:** 100 videos per day per app
- **Approval required:** Yes (3-5 business days)

### YouTube Shorts
- **File size limit:** 256 MB
- **Duration:** Under 60 seconds
- **Aspect ratio:** 9:16 (vertical) recommended
- **Quota:** ~6 videos per day (10,000 units/day, ~1,600 per upload)
- **Approval required:** No (instant access)

## Parallel Posting Flow

The autopost pipeline uses concurrent execution for speed:

```
Video 1 (Random selection)     Video 2 (Promo)
        ↓                              ↓
  Generate AI description       Post immediately
        ↓                              ↓
  Post to all 7 platforms  ←→  Post to all 7 platforms
  (parallel, max 7 workers)     (parallel, no AI wait)
```

**Total platforms:** 7 per video × 2 videos = 14 parallel posts

## Error Handling

Each platform poster returns a standardized result:

```python
{
    'success': True/False,
    'media_id': 'platform-specific-id' or None,
    'error': 'error message' or None
}
```

Failed posts are logged but don't block other platforms.

## Testing

### Test Individual Platforms

```python
# Test TikTok
from tiktok_poster import post_to_tiktok
result = post_to_tiktok('test_video.mp4', 'Test caption #test')
print(result)

# Test YouTube
from youtube_poster import post_to_youtube_shorts
result = post_to_youtube_shorts('test_video.mp4', 'Test caption #shorts')
print(result)
```

### Test Full Pipeline

1. Upload test video to AUTOPOST_FOLDER_ID
2. Trigger autopost with sync=true
3. Monitor logs for each platform status

## Next Steps

### Immediate
- [ ] Set up TikTok Developer account and get API credentials
- [ ] Set up Google Cloud project and get YouTube API credentials
- [ ] Test individual platform posters
- [ ] Test full autopost pipeline

### Future Enhancements
- [ ] Automatic token refresh for YouTube
- [ ] Retry logic for failed uploads
- [ ] Platform-specific caption optimization
- [ ] Analytics dashboard for cross-platform performance
- [ ] A/B testing for captions and hooks

## References

- TikTok API: https://developers.tiktok.com/doc/upload-api
- YouTube API: https://developers.google.com/youtube/v3
- Parent issue: [MAR-5](/MAR/issues/MAR-5)
- Marketing strategy: [MAR-4](/MAR/issues/MAR-4)
