# Auto-Posting Error Handling with Retry Logic

## Overview

This document describes the error handling and retry logic implemented for the auto-posting pipeline.

## Features Implemented

### 1. Retry Logic with Exponential Backoff

All platform posting functions now include automatic retry logic:

- **Max retries**: 3 attempts
- **Base delay**: 2 seconds
- **Exponential backoff**: Delay doubles after each failed attempt (2s → 4s → 8s)
- **Max delay**: Capped at 60 seconds between retries

**Retryable errors include:**
- Network timeouts
- Connection errors
- HTTP 5xx server errors
- Rate limiting (HTTP 429)

### 2. CMO Alert System

When posting fails after all retry attempts, an alert is automatically sent to the CMO.

**Alert channels:**
- **Email** (via SendGrid)
- **Webhook** (Slack, Discord, Teams, or custom)
- **Console** (fallback if no channels configured)

**Alert triggers:**
1. Individual platform failure (after 3 retries)
2. Systemic failure (5+ platforms fail simultaneously)

**Alert information includes:**
- Video name and ID
- Platform(s) that failed
- Error message
- Timestamp
- Number of retry attempts

## Files Added

1. **`retry_utils.py`** - Core retry logic with exponential backoff
2. **`cmo_alerts.py`** - CMO alert management system

## Files Modified

1. **`app.py`** - Integrated retry logic into all platform posting functions

## Configuration

Add these environment variables to your `.env` file:

```bash
# CMO Alert Configuration
CMO_ALERT_EMAIL=cmo@memorystore.in
CMO_ALERT_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
CMO_ALERT_ENABLED=true
SENDGRID_API_KEY=your_sendgrid_api_key
SENDGRID_FROM_EMAIL=noreply@memorystore.in
```

## Usage

The retry logic and CMO alerts are automatically enabled for all auto-posting operations. No code changes are needed in the posting workflow.

### Example Flow

1. Auto-posting starts for a video
2. Platform API call fails (e.g., LinkedIn timeout)
3. System waits 2 seconds, retries (attempt 2)
4. If it fails again, waits 4 seconds, retries (attempt 3)
5. If all 3 retries fail:
   - Logs the failure
   - Sends CMO alert with error details
   - Continues with other platforms

## Platform Support

Retry logic and CMO alerts are implemented for:

- ✅ LinkedIn
- ✅ Instagram Reels
- ✅ Threads
- ✅ Facebook
- ✅ Twitter (X)
- ✅ TikTok
- ✅ YouTube Shorts

## Testing

To test the retry logic:

1. Temporarily set an invalid API key for a platform
2. Trigger auto-posting
3. Observe the logs for retry attempts
4. Verify CMO alert is sent after all retries fail

To test CMO alerts:

```bash
# Set test environment variables
export CMO_ALERT_ENABLED=true
export CMO_ALERT_EMAIL=test@example.com
export CMO_ALERT_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ

# Run the app and trigger a failure
python app.py
```

## Monitoring

Check the application logs for:

- `⚠️` - Retry attempt warnings
- `❌` - Final failure after all retries
- `🚨` - CMO alert sent
- `✅` - Successful operations

## Future Enhancements

Potential improvements:

1. **Configurable retry count** per platform
2. **Circuit breaker pattern** to stop posting to a platform after repeated failures
3. **Alert throttling** to prevent alert spam during outages
4. **Recovery notifications** when a platform starts working again
5. **Metrics dashboard** to track failure rates and patterns
