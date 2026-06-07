"""
Google Drive Video Manager
Handles video operations: list, download, delete from Google Drive
"""

import errno
import io
import os
import shutil
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import requests

# If modifying these scopes, delete the file token.pickle
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveManager:
    def __init__(self, credentials_path=None, use_service_account=True):
        """
        Initialize Google Drive Manager
        
        Args:
            credentials_path: Path to credentials JSON file
            use_service_account: If True, uses service account. If False, uses OAuth
        """
        self.credentials_path = credentials_path or 'credentials.json'
        self.use_service_account = use_service_account
        self.service = self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        creds = None
        
        if self.use_service_account:
            # Service Account authentication (best for automation)
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=SCOPES
            )
            print(f"✓ Authenticated with service account: {creds.service_account_email}")
        else:
            # OAuth 2.0 authentication (requires user consent)
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            
            # If credentials are invalid or don't exist
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                
                # Save credentials for next run
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
        
        # Build service with explicit credentials
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return service
    
    def list_videos_in_folder(self, folder_id, mime_types=None):
        """
        List all videos in a Google Drive folder with ROBUST randomization
        
        Args:
            folder_id: Google Drive folder ID
            mime_types: List of video MIME types to filter (default: common video types)
        
        Returns:
            List of video file metadata (in completely random order)
        """
        import random
        import time
        
        if mime_types is None:
            mime_types = [
                'video/mp4',
                'video/quicktime',  # .mov
                'video/x-msvideo',  # .avi
                'video/x-matroska',  # .mkv
                'video/x-ms-wmv',  # .wmv
            ]
        
        # Build query for videos in folder
        mime_query = " or ".join([f"mimeType='{mt}'" for mt in mime_types])
        query = f"'{folder_id}' in parents and ({mime_query}) and trashed=false"
        
        # Use orderBy to randomize from Google's side too
        # We'll override this with our own shuffle, but it helps prevent patterns
        results = self.service.files().list(
            q=query,
            pageSize=1000,  # Increased from 100 to get more videos
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink)",
            orderBy="modifiedTime desc"  # Get by modified time, then we shuffle
        ).execute()
        
        files = results.get('files', [])
        
        # Multi-level shuffling for maximum randomness
        # 1. Seed with high-precision timestamp
        random.seed(time.time() * 1000000)
        
        # 2. First shuffle
        random.shuffle(files)
        
        # 3. Second shuffle with different seed (paranoid mode!)
        random.seed(time.time() * 1000000 + random.randint(0, 999999))
        random.shuffle(files)
        
        # 4. One more shuffle for good measure
        random.shuffle(files)
        
        return files
    
    def get_random_video_fast(self, folder_id, sample_size=100):
        """
        Get a random video FAST and TRULY RANDOM across all videos
        
        Strategy:
        1. Fetch videos with randomly selected orderBy criteria
        2. This ensures we get videos from different time periods/categories
        3. Pick randomly from the fetched sample
        
        Args:
            folder_id: Google Drive folder ID
            sample_size: Number of videos to fetch (default 100)
        
        Returns:
            Single random video metadata dict
        """
        import random
        import time
        
        # Seed with timestamp
        random.seed(time.time())
        
        mime_types = [
            'video/mp4',
            'video/quicktime',
            'video/x-msvideo',
            'video/x-matroska',
            'video/x-ms-wmv',
        ]
        
        # Build query
        mime_query = " or ".join([f"mimeType='{mt}'" for mt in mime_types])
        query = f"'{folder_id}' in parents and ({mime_query}) and trashed=false"
        
        # Random orderBy to get different samples each time
        order_options = [
            'createdTime desc',    # Newest first
            'createdTime',         # Oldest first  
            'modifiedTime desc',   # Recently modified
            'modifiedTime',        # Least recently modified
            'name',                # Alphabetical
            'name desc',           # Reverse alphabetical
        ]
        
        random_order = random.choice(order_options)
        
        print(f"  🎲 Fetching videos with random order: {random_order}")
        
        # Fetch a sample with random ordering
        results = self.service.files().list(
            q=query,
            pageSize=sample_size,
            fields="files(id, name, mimeType, size)",
            orderBy=random_order
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            return None
        
        print(f"  📊 Found {len(files)} videos in sample")
        
        # Random selection from the sample
        selected = random.choice(files)
        
        return selected

    
    def download_video(self, file_id, destination_path):
        """
        Download a video from Google Drive with retry logic
        Uses requests library to avoid SSL issues
        
        Args:
            file_id: Google Drive file ID
            destination_path: Local path to save the video
        
        Returns:
            Path to downloaded file
        """
        import time
        import requests
        
        max_retries = 3
        retry_delay = 2
        destination_dir = Path(destination_path).parent
        destination_dir.mkdir(parents=True, exist_ok=True)

        expected_size = 0
        try:
            metadata = self.service.files().get(fileId=file_id, fields='size').execute()
            expected_size = int(metadata.get('size', 0) or 0)
        except Exception:
            expected_size = 0
        
        for attempt in range(max_retries):
            try:
                # Get the access token from credentials
                creds = self.service._http.credentials
                access_token = creds.token
                
                # If token is expired, refresh it
                if creds.expired:
                    creds.refresh(Request())
                    access_token = creds.token
                
                # Download using requests library (avoids SSL issues)
                download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
                headers = {
                    'Authorization': f'Bearer {access_token}'
                }
                
                response = requests.get(download_url, headers=headers, stream=True, timeout=300)
                response.raise_for_status()

                if expected_size:
                    free_space = shutil.disk_usage(destination_dir).free
                    # Keep a small safety buffer for concurrent temp usage and filesystem overhead.
                    required_space = expected_size + (10 * 1024 * 1024)
                    if free_space < required_space:
                        raise OSError(
                            errno.ENOSPC,
                            f"Insufficient temporary storage for download: need {required_space / 1024 / 1024:.2f} MB, have {free_space / 1024 / 1024:.2f} MB"
                        )
                
                # Write content to file
                total_size = 0
                with open(destination_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)
                
                print(f"  ✓ Downloaded: {destination_path} ({total_size / 1024 / 1024:.2f} MB)")
                return destination_path
                
            except Exception as e:
                if os.path.exists(destination_path):
                    try:
                        os.unlink(destination_path)
                        print("  → Removed partial download")
                    except OSError:
                        pass

                if attempt < max_retries - 1:
                    print(f"  ⚠️  Download attempt {attempt + 1} failed: {str(e)}")
                    print(f"  Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print(f"  ✗ Download failed after {max_retries} attempts")
                    raise
    
    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Create a folder in Google Drive
        
        Args:
            folder_name: Name of the folder to create
            parent_folder_id: ID of parent folder (None for root)
        
        Returns:
            Folder ID if successful, None otherwise
        """
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            print(f"  ✓ Created folder: {folder_name} (ID: {folder_id})")
            return folder_id
            
        except Exception as e:
            print(f"  ✗ Error creating folder: {str(e)}")
            return None
    
    def find_or_create_folder(self, folder_name, parent_folder_id=None):
        """
        Find existing folder or create it if it doesn't exist
        
        Args:
            folder_name: Name of the folder
            parent_folder_id: ID of parent folder (None for root)
        
        Returns:
            Folder ID
        """
        try:
            # Search for existing folder
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_folder_id:
                query += f" and '{parent_folder_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                print(f"  ✓ Found existing folder: {folder_name} (ID: {files[0]['id']})")
                return files[0]['id']
            else:
                # Create new folder
                return self.create_folder(folder_name, parent_folder_id)
                
        except Exception as e:
            print(f"  ✗ Error finding/creating folder: {str(e)}")
            return None
    
    def move_video(self, file_id, destination_folder_id):
        """
        Move a video to a different folder
        
        Args:
            file_id: Google Drive file ID
            destination_folder_id: ID of destination folder
        
        Returns:
            True if successful
        """
        try:
            # Get current parents
            file = self.service.files().get(
                fileId=file_id,
                fields='parents, name'
            ).execute()
            
            previous_parents = ",".join(file.get('parents', []))
            
            # Move file to new folder
            self.service.files().update(
                fileId=file_id,
                addParents=destination_folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            
            print(f"  ✓ Moved to archive: {file.get('name')}")
            return True
            
        except Exception as e:
            print(f"  ✗ Error moving file: {str(e)}")
            return False
    
    def delete_video(self, file_id):
        """
        Delete a video from Google Drive (moves to trash)
        
        Args:
            file_id: Google Drive file ID
        
        Returns:
            True if successful
        """
        try:
            # Try method 1: Move to trash (update trashed property)
            try:
                self.service.files().update(
                    fileId=file_id,
                    body={'trashed': True}
                ).execute()
                print(f"  ✓ Moved to trash: {file_id}")
                return True
            except Exception as e1:
                # Try method 2: Direct delete
                try:
                    self.service.files().delete(fileId=file_id).execute()
                    print(f"  ✓ Deleted file: {file_id}")
                    return True
                except Exception as e2:
                    # Both methods failed
                    raise e2
                    
        except Exception as e:
            error_msg = str(e)
            print(f"  ✗ Error deleting file: {error_msg}")
            
            if "insufficient" in error_msg.lower() or "permission" in error_msg.lower():
                print(f"  💡 The file was uploaded by someone else")
                print(f"  ℹ️  Only the file owner can delete it")
                print(f"  ⚠️  You'll need to manually delete from Drive, or re-upload files using this service account")
            
            return False
    
    def delete_video_permanently(self, file_id):
        """
        Permanently delete a video (cannot be recovered)
        
        Args:
            file_id: Google Drive file ID
        """
        # First trash it, then empty trash for this file
        self.delete_video(file_id)
    
    def get_file_metadata(self, file_id):
        """
        Get metadata for a specific file
        
        Args:
            file_id: Google Drive file ID
        
        Returns:
            File metadata dictionary
        """
        return self.service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, modifiedTime, webViewLink"
        ).execute()
    
    def upload_video(self, file_path, folder_id, filename=None):
        """
        Upload a video to Google Drive
        
        Args:
            file_path: Local path to video file
            folder_id: Google Drive folder ID to upload to
            filename: Custom filename (optional, uses original name if not provided)
        
        Returns:
            Uploaded file metadata
        """
        if filename is None:
            filename = Path(file_path).name
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(
            file_path,
            mimetype='video/mp4',
            resumable=True
        )
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        print(f"  ✓ Uploaded: {filename} (ID: {file.get('id')})")
        return file
    
    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Create a new folder in Google Drive
        
        Args:
            folder_name: Name of the folder to create
            parent_folder_id: Parent folder ID (optional, creates in root if not provided)
        
        Returns:
            Created folder metadata
        """
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        
        folder = self.service.files().create(
            body=file_metadata,
            fields='id, name, webViewLink'
        ).execute()
        
        print(f"  ✓ Created folder: {folder_name} (ID: {folder.get('id')})")
        return folder
    
    def list_images_in_folder(self, folder_id, mime_types=None):
        """
        List all images in a Google Drive folder with randomization.

        Args:
            folder_id: Google Drive folder ID
            mime_types: List of image MIME types to filter (default: common image types)

        Returns:
            List of image file metadata (in completely random order)
        """
        import random
        import time

        if mime_types is None:
            mime_types = [
                'image/jpeg',
                'image/png',
                'image/gif',
                'image/webp',
                'image/bmp',
                'image/tiff',
                'image/svg+xml',
            ]

        mime_query = " or ".join([f"mimeType='{mt}'" for mt in mime_types])
        query = f"'{folder_id}' in parents and ({mime_query}) and trashed=false"

        results = self.service.files().list(
            q=query,
            pageSize=1000,
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink)",
            orderBy="modifiedTime desc"
        ).execute()

        files = results.get('files', [])

        random.seed(time.time() * 1000000)
        random.shuffle(files)
        random.seed(time.time() * 1000000 + random.randint(0, 999999))
        random.shuffle(files)
        random.shuffle(files)

        return files

    def get_random_image_fast(self, folder_id, sample_size=100):
        """
        Get a random image FAST from a Google Drive folder.

        Args:
            folder_id: Google Drive folder ID
            sample_size: Number of images to fetch

        Returns:
            Single random image metadata dict
        """
        import random
        import time

        random.seed(time.time())

        mime_types = [
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
            'image/bmp',
        ]

        mime_query = " or ".join([f"mimeType='{mt}'" for mt in mime_types])
        query = f"'{folder_id}' in parents and ({mime_query}) and trashed=false"

        order_options = [
            'createdTime desc',
            'createdTime',
            'modifiedTime desc',
            'modifiedTime',
            'name',
            'name desc',
        ]

        random_order = random.choice(order_options)

        results = self.service.files().list(
            q=query,
            pageSize=sample_size,
            fields="files(id, name, mimeType, size)",
            orderBy=random_order
        ).execute()

        files = results.get('files', [])

        if not files:
            return None

        selected = random.choice(files)
        return selected

    def download_image(self, file_id, destination_path):
        """
        Download an image from Google Drive with retry logic.

        Args:
            file_id: Google Drive file ID
            destination_path: Local path to save the image

        Returns:
            Path to downloaded file
        """
        import time
        import requests

        max_retries = 3
        retry_delay = 2
        destination_dir = Path(destination_path).parent
        destination_dir.mkdir(parents=True, exist_ok=True)

        for attempt in range(max_retries):
            try:
                creds = self.service._http.credentials
                access_token = creds.token

                if creds.expired:
                    creds.refresh(Request())
                    access_token = creds.token

                download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
                headers = {
                    'Authorization': f'Bearer {access_token}'
                }

                response = requests.get(download_url, headers=headers, stream=True, timeout=300)
                response.raise_for_status()

                with open(destination_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                print(f"  ✓ Downloaded image: {destination_path}")
                return destination_path

            except Exception as e:
                if os.path.exists(destination_path):
                    try:
                        os.unlink(destination_path)
                    except OSError:
                        pass

                if attempt < max_retries - 1:
                    print(f"  ⚠️  Image download attempt {attempt + 1} failed: {str(e)}")
                    print(f"  Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"  ✗ Image download failed after {max_retries} attempts")
                    raise

    def get_video_categories(self, folder_id):
        """
        Organize videos by category based on filename prefix
        Videos within each category are heavily shuffled for maximum randomness
        
        Args:
            folder_id: Google Drive folder ID
        
        Returns:
            Dictionary of categories with video lists (completely randomized)
        """
        import random
        import time
        
        videos = self.list_videos_in_folder(folder_id)
        
        categories = {}
        for video in videos:
            filename = video['name']
            # Extract category prefix (text before first underscore)
            if '_' in filename:
                category = filename.split('_')[0]
            else:
                category = 'other'
            
            if category not in categories:
                categories[category] = []
            categories[category].append(video)
        
        # AGGRESSIVE shuffling within each category
        for category in categories:
            # Shuffle multiple times with different seeds
            random.seed(time.time() * 1000000)
            random.shuffle(categories[category])
            
            random.seed(time.time() * 1000000 + random.randint(0, 999999))
            random.shuffle(categories[category])
            
            # One more for paranoid-level randomness
            random.shuffle(categories[category])
        
        return categories


# Example usage
if __name__ == "__main__":
    print("🚀 Google Drive Video Manager Example")
    print("=" * 50)
    
    # Initialize manager (you'll need credentials.json)
    try:
        manager = GoogleDriveManager(
            credentials_path='credentials.json',
            use_service_account=True  # Change to False for OAuth
        )
        
        # Replace with your folder ID
        FOLDER_ID = "YOUR_FOLDER_ID_HERE"
        
        # List all videos
        print("\n📁 Listing videos...")
        videos = manager.list_videos_in_folder(FOLDER_ID)
        
        for video in videos:
            print(f"  • {video['name']}")
            print(f"    ID: {video['id']}")
            print(f"    Size: {int(video.get('size', 0)) / (1024*1024):.2f} MB")
            print(f"    Link: {video['webViewLink']}")
            print()
        
        # Get categories
        print("\n📊 Video categories:")
        categories = manager.get_video_categories(FOLDER_ID)
        for category, vids in categories.items():
            print(f"  {category}: {len(vids)} videos")
        
        # Download a video (example)
        if videos:
            print(f"\n⬇️  Downloading first video...")
            first_video = videos[0]
            manager.download_video(
                first_video['id'],
                f"downloads/{first_video['name']}"
            )
        
        print("\n✅ Done!")
        
    except FileNotFoundError:
        print("❌ credentials.json not found!")
        print("\nTo get started:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a project")
        print("3. Enable Google Drive API")
        print("4. Create Service Account credentials")
        print("5. Download credentials.json")
        print("6. Share your Drive folder with the service account email")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
