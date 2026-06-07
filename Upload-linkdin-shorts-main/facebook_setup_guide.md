# Facebook Posting Setup Guide

This guide explains how to set up the Facebook Feed/Reels posting integration.

## Prerequisites

1.  **Facebook Page**: You must have a Facebook Page (not just a profile) to post via API.
2.  **Meta Developer Account**: You are already using this for Threads/Instagram.

## Step 1: Get Page ID

1.  Go to your Facebook Page.
2.  The Page ID is often in the URL (e.g., `facebook.com/PageName-123456789`) or in the "About" section.
3.  Alternatively, use the Graph API Explorer: 
    *   GET `/me/accounts`
    *   Look for the `id` field next to your page name.

## Step 2: Get Page Access Token

1.  Go to **Tools** > **[Graph API Explorer](https://developers.facebook.com/tools/explorer/)**.
2.  Select your App.
3.  In "User or Page", select **"Get Page Access Token"**.
4.  Authorization window will pop up. Select the page(s) you want to manage.
5.  **Permissions Required**:
    *   `pages_manage_posts`
    *   `pages_show_list`
    *   `pages_read_engagement`
6.  Once authorized, the "Access Token" field will contain your **Page Access Token**.

## Step 3: Configure Environment Variables

Add the following to your `.env` file:

```bash
# Facebook Configuration
FACEBOOK_ENABLED=true
FACEBOOK_PAGE_ID=your_page_id_here
FACEBOOK_ACCESS_TOKEN=your_page_access_token_here
```

## Step 4: Verify Integration

1.  Restart the application.
2.  When posting, logs should show:
    *   `📘 Posting to Facebook...`
    *   `✅ Posted to Facebook! Media ID: ...`

## Troubleshooting: "Found 0 Pages" Error

If the logs say "Found 0 pages" or "Global ID not allowed", it means you **unchecked the page** during the login popup.

**How to Fix:**
1.  Go back to **Graph API Explorer**.
2.  Click **"Generate Access Token"** again.
3.  **IMPORTANT**: In the popup, do not just click "Continue".
    *   Click **"Edit Settings"** (or it might ask "What Pages?").
    *   **CHECK THE BOX** next to your Page (`Posting`).
    *   If you don't check it, the API cannot see it.
4.  After the popup closes:
    *   Look at the "User or Page" dropdown on the right.
    *   It should now list your Page Name.
    *   **Select your Page Name** from that list.
    *   Copy the **NEW** token.

## Notes

*   **Token Expiry**: Like Threads, this token might expire (Short-Lived vs Long-Lived). You can exchange it for a long-lived one (never expires for Pages usually) using the "Open in Access Token Tool" button.
*   **Video Format**: Facebook generally handles vertical videos as Reels automatically, but they might appear as normal videos on the feed depending on platform logic.
