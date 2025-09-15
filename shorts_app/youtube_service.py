# In shorts_app/youtube_service.py

import os
from django.conf import settings
from django.shortcuts import get_object_or_404
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from .models import SocialAccount # Import your model

API_NAME = 'youtube'
API_VERSION = 'v3'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service():
    """
    Retrieves stored credentials from the database and builds an authenticated service object.
    This replaces the command-line flow.
    """
    # Get the globally stored credentials for YouTube
    social_account = get_object_or_404(SocialAccount, provider='youtube')

    creds = Credentials(
        token=social_account.access_token,
        refresh_token=social_account.refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=SCOPES
    )

    # If credentials have expired, refresh them
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save the new, refreshed tokens back to the database
        social_account.access_token = creds.token
        social_account.expires_at = creds.expiry
        social_account.save()

    return build(API_NAME, API_VERSION, credentials=creds)


def upload_video(file_path, title, description, tags, privacy_status="private"):
    """
    This function is adapted from your youtube_uploader.py.
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
                'selfDeclaredMadeForKids': False
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
        if e.resp.status == 403 and 'quotaExceeded' in str(e.content):
            return {'status': 'error', 'message': 'YouTube API daily upload quota has been exceeded.'}
        else:
            return {'status': 'error', 'message': f'An API error occurred: {e}'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}