# In shorts_app/youtube_service.py
import logging
from django.conf import settings
from django.shortcuts import get_object_or_404  # Keep this for now, or use SocialAccount.objects.get below
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from .models import SocialAccount
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)
API_NAME = 'youtube'
API_VERSION = 'v3'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service():
    """
    Retrieves stored OAuth 2.0 credentials from the database.
    This uses the web-based login flow.
    """
    social_account = SocialAccount.objects.get(provider='youtube')  # Use .get() instead of get_object_or_404 for service

    creds = Credentials(
        token=social_account.access_token,
        refresh_token=social_account.refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=SCOPES
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        social_account.access_token = creds.token
        social_account.save()

    return build(API_NAME, API_VERSION, credentials=creds)

def upload_video(file_path, title, description, tags, privacy_status="private", made_for_kids=False):
    """
    Uploads a video to YouTube using the authenticated service.
    """
    try:
        youtube = get_authenticated_service()

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': '22'  # 'People & Blogs'
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': made_for_kids
            }
        }

        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media
        )
        response = request.execute()
        return {'status': 'success', 'video_id': response.get('id')}
    except HttpError as e:
        logger.error(f"Google API HttpError: {e.resp.status} - {e.content.decode('utf-8')}", exc_info=True)
        if e.resp.status == 403 and 'quotaExceeded' in str(e.content):
            return {'status': 'error', 'message': 'YouTube API daily upload quota has been exceeded.'}
        else:
            error_details = e.content.decode('utf-8')
            return {'status': 'error', 'message': f'An API error occurred: {error_details}'}
    except Exception as e:
        logger.error(f"A non-HttpError occurred during YouTube upload: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}