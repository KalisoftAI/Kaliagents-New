# In shorts_app/instagram_service.py
import os
import time
import requests
import logging
from django.conf import settings
from django.shortcuts import get_object_or_404
from .models import SocialAccount, GeneratedShort

logger = logging.getLogger(__name__)

def get_public_url_for_short(request, short: GeneratedShort):
    """
    Generates a full, publicly accessible URL for a short video file.
    NOTE: This only works if your Django app is running on a public server (not localhost).
    For localhost testing, you would need a tool like ngrok.
    """
    return request.build_absolute_uri(short.short_path)

def upload_reel(request, short: GeneratedShort, caption: str, share_to_feed: bool):
    try:
        social_account = get_object_or_404(SocialAccount, provider='instagram')
        ig_user_id = social_account.provider_user_id
        access_token = social_account.access_token

        video_url = get_public_url_for_short(request, short)
        
        # Step 1: Create Media Container
        container_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
        container_params = {
            'media_type': 'REELS',
            'video_url': video_url,
            'caption': caption,
            'share_to_feed': share_to_feed,
            'access_token': access_token,
        }
        r = requests.post(container_url, params=container_params)
        response_data = r.json()
        creation_id = response_data.get('id')
        if not creation_id:
            error_msg = response_data.get('error', {}).get('message', 'Unknown error')
            logger.error(f"Instagram container creation failed: {error_msg}")
            return {'status': 'error', 'message': f"Failed to create container: {error_msg}"}

        # Step 2: Poll for status until it's finished
        for _ in range(15):  # Poll for up to 1.5 minutes
            status_url = f"https://graph.facebook.com/v19.0/{creation_id}"
            status_params = {'fields': 'status_code', 'access_token': access_token}
            r = requests.get(status_url, params=status_params)
            status = r.json().get('status_code')
            if status == 'FINISHED':
                break
            time.sleep(6)
        else:
            logger.error("Instagram media processing timed out")
            return {'status': 'error', 'message': 'Media processing timed out.'}

        # Step 3: Publish Media Container
        publish_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"
        publish_params = {'creation_id': creation_id, 'access_token': access_token}
        r = requests.post(publish_url, params=publish_params)
        
        if 'id' in r.json():
            media_id = r.json().get('id')
            logger.info(f"Instagram Reel uploaded successfully: {media_id}")
            return {'status': 'success', 'media_id': media_id}
        else:
            error_msg = r.json().get('error', {}).get('message', 'Unknown error')
            logger.error(f"Instagram publish failed: {error_msg}")
            return {'status': 'error', 'message': f"Failed to publish Reel: {error_msg}"}

    except Exception as e:
        logger.error(f"Unexpected error in Instagram upload: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}