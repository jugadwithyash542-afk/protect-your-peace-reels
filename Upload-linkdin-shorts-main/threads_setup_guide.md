# Threads Posting Setup Guide

This guide explains how to set up the Threads posting integration.

## Prerequisites

1.  **Instagram Business/Creator Account**: Your Threads profile must be linked to an Instagram Business or Creator account.
2.  **Facebook Page**: Your Instagram account must be connected to a Facebook Page.
3.  **Meta Developer Account**: You need access to [Meta for Developers](https://developers.facebook.com/).

## Step 1: Create/Configure Meta App

1.  Go to [Meta for Developers](https://developers.facebook.com/apps/).
2.  Select your existing app (used for Instagram) or create a new one (Type: "Business" or "Consumer" depending on your needs, commonly "Business" for API access).
3.  In the **Dashboard**, look for "Add products to your app".
    *   **Recommendation**: If you are having permission issues, **Create a NEW Business App**.
        1.  Go to "My Apps" -> **Create App**.
        2.  Select **"Other"** -> **"Next"** -> **"Business"**.
        3.  Name it something like "AutoPoster-v2".
        4.  This resets all permissions and gives you a clean slate.
    *   **CRITICAL**: If you do not see "Threads" in the list, verify you are in the new app you just created.
    *   **WORKAROUND**: If "Threads" is still missing, look at the left sidebar:
        1.  Expand **"App Review"** -> click **"Permissions and Features"**.
        2.  Search for `threads_basic`.
        3.  Click **"Request"** or "Get Advanced Access" next to it.
        4.  This effectively enables the Threads API for your app.
    
    **💡 PRO TIP: Bypass the Dashboard UI**
    If you are the App Admin (which you are), you don't actually need to "Add" the product to get a token for testing. You can use the **Tools > Graph API Explorer** directly.

## Step 2: Get Access Token & Account ID

1.  Go to **Tools** > **[Graph API Explorer](https://developers.facebook.com/tools/explorer/)**.
2.  **Select your App** in the top right dropdown (make sure it's the "Business" app you just created).
3.  In the **"Permissions"** section (left side), search and add:
    *   `threads_basic`
    *   `threads_content_publish`
    *   *(If you can't find them in the search, just type them in manually and press Enter)*
4.  Click **"Generate Access Token"**.
5.  Follow the popup flow to login with your Threads account.
6.  You now have a **Short-Lived User Token**.
    *   **Note**: `threads_business_basic` is NOT the correct permission. Ignore it. You need `threads_basic` and `threads_content_publish`.

1.  In your Meta App Dashboard, go to **Threads API** > **User Token Generator** (if available) or use the **Graph API Explorer**.
2.  **Scopes Required**:
    *   `threads_basic`
    *   `threads_content_publish`
3.  Generate a **User Access Token**.
4.  **CRITICAL STEP: Get Long-Lived Token**
    *   The token you copy from the Explorer is valid for only **1 hour**.
    *   To make it last **60 days**:
        1.  Copy the short token.
        2.  Click the **"Info" (i)** icon next to the token in Explorer.
        3.  Click **"Open in Access Token Tool"**.
        4.  Click the blue **"Extend Access Token"** button.
        5.  Copy the **NEW, longer token** provided at the bottom.
        6.  Use THIS new token in your `.env` file.
    *   Start with a Short-Lived User Token.
    *   Exchange it for a Long-Lived User Token (valid for 60 days) using the Token Exchanger tool or API.
5.  Get your **Threads User ID**.
    *   Use the Graph API Explorer or make a GET request to `/me` with your Threads token.
    *   Note: This ID is specific to the Threads API and different from your Instagram ID.

## Step 3: Configure Environment Variables

Add the following variables to your `.env` file or deployment environment variables (e.g., Vercel):

```bash
# Threads Configuration
THREADS_ENABLED=true
THREADS_ACCESS_TOKEN=your_long_lived_threads_access_token
THREADS_ACCOUNT_ID=your_threads_user_id
```

## Step 4: Verify Integration

1.  Restart your application.
2.  When you "Accept" a video or use the "Autopost" feature, the logs will show:
    *   `⚡ Posting to LinkedIn, Instagram, and Threads in parallel...`
    *   `🧵 Posting to Threads...`
    *   `✅ Posted to Threads! Media ID: ...`

## Troubleshooting

*   **Token Expiry**: User tokens expire after 60 days. You need to refresh them.
*   **Video Hosting**: The system uses `tmpfiles.org` to host videos temporarily for the API to download. If uploads fail, check if the video size is too large or if the service is down.
*   **Rate Limits**: Threads API has rate limits (e.g., 250 posts per 24 hours).

## Resources

*   [Threads API Documentation](https://developers.facebook.com/docs/threads/)
*   [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
