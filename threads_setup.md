# Threads Profile Setup Guide 🚀

To publish posts to your Threads account automatically via the `upload_pipeline.py` script, you need to configure two environment variables in your `.env` file:
* **`THREADS_ACCESS_TOKEN`**: A long-lived access token to authorize API requests.
* **`THREADS_ACCOUNT_ID`**: The specific ID of your Threads profile.

Follow the step-by-step instructions below to set these up.

---

## Step 1: Create a Meta Developer App
Since Threads is a Meta platform, it is managed through the Meta for Developers portal.

> [!WARNING]
> **DO NOT select "Business" when creating your app.**
> Selecting "Business" restricts permissions to ad metrics/insights only, which is why you only see scopes like `threads_business_basic`. To publish video reels and text posts, you need the standard consumer publishing permissions.

1. Go to the [Meta for Developers Dashboard](https://developers.facebook.com/).
2. Log in with your Facebook account (it must be connected to your Threads/Instagram account).
3. Click **Create App**.
4. During the setup flow, choose one of these options:
   * **Recommended**: Select the **Access the Threads API** use case directly.
   * **Alternative**: Select **Other** -> **Consumer** (or **None/Other**).
5. Enter an App Display Name (e.g., `Protect Your Peace Automation`) and click **Create App**.

---

## Step 2: Configure the Threads Product
Once your app is created, you need to add the Threads product.

1. In the left-hand sidebar of your App Dashboard, click **Add Product** (or find it on the main Dashboard page).
2. Find **Threads** (or **Threads API**) and click **Set Up**.
3. Under the **Threads** product settings in the sidebar:
   * Go to **Settings** / **Use Cases**.
   * Ensure that the **Threads API** use case is selected and active.
   * Add the required permissions (scopes) under the configuration:
     * `threads_basic` (Read profile information)
     * `threads_content_publish` (Publish text, images, and videos)

---

## Step 3: Add a Threads Test User
Before your Meta app goes through App Review (which is only needed if other people are going to log in), you must add your own Threads account as a tester.

1. In your Meta App Dashboard, go to **App Roles** -> **Roles** (or find **Threads Testers** under the Threads configuration).
2. Click **Add Threads Tester**.
3. Enter your Threads username (e.g., `heysis.co` or your personal Threads handle) and submit.
4. **Accept the Invitation on Threads:**
   * Open the **Instagram / Threads** app on your phone, or go to [Threads.net](https://www.threads.net/) on your desktop.
   * Go to **Settings** -> **Account** -> **Website permissions** (or Apps and Websites) -> **Tester Invitations**.
   * Locate your Meta App's invitation and click **Accept**.

---

## Step 4: Generate your Access Token
The easiest way to get an access token for your own developer account without building a website is to use the built-in **User Token Generator**.

1. Return to the [Meta Developer Dashboard](https://developers.facebook.com/).
2. Navigate to **Threads** -> **User Token Generator** in the left sidebar (or under the Threads configuration page).
3. You should see your authorized Threads account listed under the testers.
4. Click **Generate Token** next to your username.
5. Authorize the requested permissions on the popup window.
6. Copy the generated **Access Token**. (By default, tokens generated here are long-lived 60-day tokens).

---

## Step 5: Run the Automated Setup Helper
To verify your access token, fetch your Threads Account ID, and automatically save them to your `.env` file, we have created a python helper script:

1. Open your terminal in the workspace root.
2. Run the helper script:
   ```bash
   python scripts/threads_auth_helper.py
   ```
3. When prompted, paste the **Access Token** you copied in Step 4.
4. The helper script will:
   * Verify the token by calling the Threads Profile API (`/me`).
   * Retrieve your **Threads Account ID** and **Username**.
   * Automatically update your `.env` file with the values.

---

## Step 6: Test the Integration
Once your `.env` is updated, make sure `THREADS_ENABLED=true` is set. The next time you run:
```bash
python scripts/upload_pipeline.py
```
It will automatically post the rendered video to your Threads feed!

> ⚠️ **Token Lifespan Note:** Long-lived tokens are valid for **60 days**. After that, you will need to regenerate them via the Meta Developer portal, or refresh them.
