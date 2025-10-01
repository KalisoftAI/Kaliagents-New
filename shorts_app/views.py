from PIL import Image
if not hasattr(Image, "ANTIALIAS") and hasattr(Image, "Resampling"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS
import os
import uuid
import json
import logging
import re
import threading
import webvtt
import csv
import io
from urllib.parse import urlparse, parse_qs
import google.generativeai as genai
from google.api_core.exceptions import NotFound
from . import youtube_service, instagram_service 
import json 
from yt_dlp.utils import DownloadError
from django.shortcuts import redirect
from django.conf import settings
from google_auth_oauthlib.flow import Flow
import googleapiclient.discovery as discovery
from googleapiclient.errors import HttpError
import googleapiclient.discovery
import requests
from .models import SocialAccount

from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, FileResponse, Http404
from django.core.cache import cache
from yt_dlp import YoutubeDL

from moviepy.editor import VideoFileClip, CompositeVideoClip, ColorClip
from moviepy.video.fx.all import crop, resize

from .models import DownloadedVideo, GeneratedShort
import google.generativeai as genai
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from yt_dlp.utils import DownloadError
# Import for YouTube Data API
import googleapiclient.discovery
import googleapiclient.errors

logger = logging.getLogger(__name__)

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
YOUTUBE_OAUTH_REDIRECT_URI = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', 'http://127.0.0.1:8000/youtube/callback/')
# --- Configure Gemini (Unchanged) ---
genai_configured = False
try:
    if settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        genai_configured = True
    else:
        logger.error("GEMINI_API_KEY not set. AI features disabled.")
except Exception as e:
    logger.error(f"Error during Gemini configuration: {e}. AI features disabled.")
    genai = None


# --- NEW: CSV Logging Helper Function ---
def log_to_csv(full_transcript: str, ai_transcripts: list, output_link: str, feedback: str):
    """
    Creates and appends a row to the shorts_log.csv file.
    """
    csv_file_path = os.path.join(settings.BASE_DIR, 'shorts_log.csv')
    
    # Define the column headers for your CSV
    headers = [
        'Whole Input Transcript',
        'AI Generated Transcript',
        'Output Video Link',
        'Observation & Feedback'
    ]

    # Combine AI transcripts into a single string
    # Assuming ai_transcripts is a list of descriptions from the suggestions JSON
    ai_transcript_str = "\n".join(ai_transcripts)

    # The data row to be appended
    data_row = [
        full_transcript,
        ai_transcript_str,
        output_link,
        feedback
    ]

    # Check if the file already exists. If not, create it and write headers.
    file_exists = os.path.isfile(csv_file_path)

    # Use 'a' for append mode. newline='' is important for csv.
    with open(csv_file_path, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)

        # If the file didn't exist, write the headers first
        if not file_exists:
            writer.writerow(headers)
            logger.info(f"Created new CSV file at {csv_file_path}")

        # Now, write the actual data row
        writer.writerow(data_row)
        logger.info(f"Appended a new row to {csv_file_path}")


INSTAGRAM_SCOPES = 'instagram_basic,instagram_content_publish,pages_show_list'

def instagram_connect(request):
    """
    Initiates the OAuth flow to connect an Instagram Business account.
    """
    auth_url = (
        f"https://www.facebook.com/v19.0/dialog/oauth?"
        f"client_id={settings.INSTAGRAM_APP_ID}"
        f"&redirect_uri={settings.INSTAGRAM_REDIRECT_URI}"
        f"&scope={INSTAGRAM_SCOPES}"
        f"&response_type=code"
    )
    return redirect(auth_url)


def instagram_callback(request):
    """
    Handles the redirect from Facebook after user authorization.
    """
    code = request.GET.get('code')
    if not code:
        return redirect('shorts_app:index')

    # 1. Exchange code for a user access token
    token_url = 'https://graph.facebook.com/v19.0/oauth/access_token'
    token_params = {
        'client_id': settings.INSTAGRAM_APP_ID,
        'redirect_uri': settings.INSTAGRAM_REDIRECT_URI,
        'client_secret': settings.INSTAGRAM_APP_SECRET,
        'code': code,
    }
    r = requests.get(token_url, params=token_params)
    user_access_token = r.json().get('access_token')

    # 2. Get the user's Facebook Page connected to their Instagram account
    pages_url = f"https://graph.facebook.com/me/accounts?access_token={user_access_token}"
    r = requests.get(pages_url)
    pages_data = r.json()['data']
    if not pages_data:
        # Handle error: User has no Facebook pages
        return redirect('shorts_app:index') 
    
    page_id = pages_data[0]['id']
    page_access_token = pages_data[0]['access_token']

    # 3. Get the Instagram Business Account ID
    ig_account_url = f"https://graph.facebook.com/{page_id}?fields=instagram_business_account&access_token={page_access_token}"
    r = requests.get(ig_account_url)
    ig_business_account_id = r.json()['instagram_business_account']['id']
    
    SocialAccount.objects.update_or_create(
        provider='instagram',
        defaults={
            'provider_user_id': ig_business_account_id,
            'access_token': page_access_token,
        }
    )
    return redirect('shorts_app:index')

def youtube_connect(request):
    """
    Initiates the OAuth flow to connect a YouTube account.
    """
    flow = Flow.from_client_config(
        {
            'web': {
                'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
                'redirect_uris': [YOUTUBE_OAUTH_REDIRECT_URI],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
        },
        scopes=YOUTUBE_SCOPES,
        state=uuid.uuid4().hex  # For CSRF protection
    )
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force refresh token
    )
    return redirect(auth_url)



def burn_subtitles_into_video(video_path, vtt_path):
    """
    Takes a video file and a VTT transcript file and returns the path
    to a new video with the subtitles burned in.
    """
    video_clip = VideoFileClip(video_path)
    captions = webvtt.read(vtt_path)

    subtitle_clips = []
    for caption in captions:
        # Create a moviepy TextClip for each caption line
        text_clip = TextClip(
            caption.text,
            fontsize=40,
            color='white',
            font='Arial-Bold', # You may need to have this font installed or provide a path
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(video_clip.w * 0.8, None) # Subtitles will take up 80% of the video width
        )
        
        # Set the duration and start time of the text clip
        text_clip = text_clip.set_duration(caption.end_in_seconds - caption.start_in_seconds)
        text_clip = text_clip.set_start(caption.start_in_seconds)
        
        # Set the position of the subtitles
        # ('center', 0.8) places it horizontally centered and 80% down the screen.
        text_clip = text_clip.set_position(('center', 0.8), relative=True)
        
        subtitle_clips.append(text_clip)

    # Overlay the subtitle clips on the original video
    final_clip = CompositeVideoClip([video_clip] + subtitle_clips)

    # Create a new filename for the subtitled video
    original_dir = os.path.dirname(video_path)
    original_filename = os.path.basename(video_path)
    new_filename = f"{os.path.splitext(original_filename)[0]}_subtitled.mp4"
    output_path = os.path.join(original_dir, new_filename)

    # Write the final video file
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

    video_clip.close()
    final_clip.close()
    
    # Return the web-accessible path to the new video
    return f'/media/shorts/{new_filename}'

# In shorts_app/views.py
# shorts_app/views.py (around line 348)

# ...

def add_subtitles(request, short_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'})

    task_id = str(uuid.uuid4())
    # Note: Initializing the task message for the frontend
    cache.set(task_id, {"status": "starting", "progress": 0, "message": "Initializing subtitle task..."})

    def subtitle_task():
        try:
            short = get_object_or_404(GeneratedShort, id=short_id)
            parent_video = short.parent_video

            # Construct the full file paths
            # The short_path should already be a web-accessible path starting with /media/shorts/
            video_full_path = os.path.join(settings.BASE_DIR, short.short_path.lstrip('/'))
            
            # The VTT path must point to the actual file location on the filesystem
            vtt_filename = f'{parent_video.video_id}.en.vtt'
            vtt_full_path = os.path.join(settings.MEDIA_ROOT, 'videos', vtt_filename)

            if not os.path.exists(vtt_full_path):
                 # --- FIX: Log the missing path for debugging ---
                 logger.warning(f"Transcript file NOT FOUND at expected path: {vtt_full_path}")
                 
                 # The frontend expects a specific error status, but since this is a known external reason (no YT subs),
                 # we use 'error' status and the message reported in the logs.
                 cache.set(task_id, {'status': 'error', 'message': 'Transcript file not found.'})
                 return

            cache.set(task_id, {"status": "processing", "progress": 50, "message": "Burning subtitles into video..."})
            
            # Call the helper function
            new_video_path = burn_subtitles_into_video(video_full_path, vtt_full_path)
            
            # Update the database record to point to the new video file
            short.short_path = new_video_path
            short.save()
            
            # The frontend is polling for this 'complete' status
            cache.set(task_id, {
                'status': 'complete', 
                'progress': 100,
                'message': 'Subtitles burned successfully!',
                'result': {'new_path': new_video_path}
            })

        except Exception as e:
            logger.error(f"Error in subtitle task for {short_id}: {e}", exc_info=True)
            # Ensure the error status is sent back to the frontend
            cache.set(task_id, {'status': 'error', 'message': f'A critical error occurred: {e}'})

    threading.Thread(target=subtitle_task).start()
    return JsonResponse({'status': 'processing', 'task_id': task_id})

def youtube_connect(request):
    """
    Initiates the OAuth 2.0 flow to connect a YouTube account.
    """
    flow = Flow.from_client_secrets_file(
        'client_secret.json',
        scopes=YOUTUBE_SCOPES,
        redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    request.session['oauth_state'] = state
    return redirect(authorization_url)

def youtube_callback(request):
    """
    Handles the redirect from Google after user authorization.
    """
    state = request.GET.get('state')
    if not state:
        return redirect('shorts_app:index')  # Or error page

    flow = Flow.from_client_config(
        {
            'web': {
                'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
                'redirect_uris': [getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', 'http://127.0.0.1:8000/youtube/callback/')],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
        },
        scopes=YOUTUBE_SCOPES,
        state=state
    )

    flow.fetch_token(authorization_response=request.build_absolute_uri())
    credentials = flow.credentials

    # Get user info (channel ID) - use discovery.build here
    youtube = discovery.build('youtube', 'v3', credentials=credentials)
    channels_response = youtube.channels().list(
        part='id,snippet',
        mine=True
    ).execute()
    channel_id = channels_response['items'][0]['id'] if channels_response['items'] else None

    if not channel_id:
        return redirect('shorts_app:index')  # No channel

    # Save to SocialAccount
    SocialAccount.objects.update_or_create(
        provider='youtube',
        defaults={
            'provider_user_id': channel_id,
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'expires_at': credentials.expiry,
        }
    )
    return redirect('shorts_app:index')


def post_to_youtube(request, short_id):
    """
    Handles posting a short to YouTube via AJAX/POST.
    Expects form data: title, description, tags, privacy, made_for_kids.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    short = get_object_or_404(GeneratedShort, id=short_id)
    file_path = os.path.join(settings.MEDIA_ROOT, short.short_path.lstrip('/'))

    if not os.path.exists(file_path):
        return JsonResponse({'status': 'error', 'message': 'Video file not found.'}, status=404)

    title = request.POST.get('title', short.social_title or short.title)
    description = request.POST.get('description', short.social_description or short.description)
    tags = [tag.strip() for tag in request.POST.get('tags', '').split(',') if tag.strip()] or short.social_hashtags or short.tags
    privacy_status = request.POST.get('privacy', 'private')
    made_for_kids = request.POST.get('made_for_kids') == 'on'

    result = youtube_service.upload_video(
        file_path=file_path,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status,
        made_for_kids=made_for_kids
    )

    if result['status'] == 'success':
        # Optionally save video_id to model or log
        logger.info(f"Uploaded to YouTube: {result['video_id']}")
        return JsonResponse({'status': 'success', 'video_id': result['video_id'], 'url': f'https://youtu.be/{result["video_id"]}'} )
    else:
        return JsonResponse({'status': 'error', 'message': result['message']}, status=400)

def post_to_instagram(request, short_id):
    """
    Handles posting a short to Instagram as a Reel via AJAX/POST.
    Expects form data: caption, share_to_feed.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    short = get_object_or_404(GeneratedShort, id=short_id)
    caption = request.POST.get('caption', short.social_description or short.description)
    share_to_feed = request.POST.get('share_to_feed') == 'on'

    result = instagram_service.upload_reel(request, short, caption, share_to_feed)

    if result['status'] == 'success':
        logger.info(f"Uploaded to Instagram: {result['media_id']}")
        return JsonResponse({'status': 'success', 'media_id': result['media_id']})
    else:
        return JsonResponse({'status': 'error', 'message': result['message']}, status=400)
    
    
def get_ai_suggested_clips(transcript, video_duration):
    if not genai_configured:
        logger.warning("Gemini API not configured. Returning empty suggestions.")
        return {"clips": []}

    try:
        # Try a supported model
        model_name = 'gemini-1.5-flash-latest'  # Use latest version to ensure availability
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        You are an expert video editor specializing in creating engaging short-form content (e.g., YouTube Shorts, TikTok, Instagram Reels).
        Given the transcript of a video and its duration, suggest 3 short clips (each 15-60 seconds long) that would maximize engagement for social media platforms.
        The transcript is:
        {transcript}
        Video duration: {video_duration} seconds
        For each clip, provide:
        - Start time (in MM:SS format)
        - End time (in MM:SS format)
        - A brief description of why this clip is engaging
        - Suggested title for the clip
        - Suggested hashtags (as a list)
        Return the response as a JSON object with a list of clips under the key 'clips'.
        **Success Criteria:**
        The content should be designed to achieve high watch time, strong engagement rates, and maximum shareability while maintaining authenticity and brand alignment.
        """
        response = model.generate_content(prompt)
        
        # Clean response to extract JSON
        cleaned_text = response.text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        json_start_index = cleaned_text.find('{')
        if json_start_index != -1:
            json_response_text = cleaned_text[json_start_index:]
            return json.loads(json_response_text)
        else:
            logger.error(f"No JSON object found in Gemini response: {cleaned_text}")
            return {"clips": []}
    except NotFound as e:
        logger.error(f"Gemini model {model_name} not found: {str(e)}")
        # List available models for debugging
        try:
            models = genai.list_models()
            available_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
            logger.info(f"Available Gemini models: {available_models}")
        except Exception as list_error:
            logger.error(f"Failed to list Gemini models: {str(list_error)}")
        return {"clips": []}
    except Exception as e:
        logger.error(f"Error generating AI suggestions with Gemini: {str(e)}", exc_info=True)
        return {"clips": []}

def save_analysis_to_csv(original_transcript, suggested_clips):
    """
    Saves the video transcript analysis to a CSV file.
    """
    analysis_dir = os.path.join(settings.MEDIA_ROOT, 'analysis')
    os.makedirs(analysis_dir, exist_ok=True)
    csv_file_path = os.path.join(analysis_dir, 'transcript_analysis.csv')
    headers = ["Normal Input transcript", "Gemini AI Generated transcript", "Video 1", "Video 2", "Video 3", "observation", "feedback"]
    file_exists = os.path.isfile(csv_file_path)

    try:
        with open(csv_file_path, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists or os.path.getsize(csv_file_path) == 0:
                writer.writerow(headers)
            
            video_suggestions = []
            for i in range(3):
                if i < len(suggested_clips):
                    clip = suggested_clips[i]
                    content = (f"Title: {clip.get('title', 'N/A')}\n"
                               f"Time: {clip.get('start_time', 'N/A')} - {clip.get('end_time', 'N/A')}\n"
                               f"Description: {clip.get('description', 'N/A')}")
                    video_suggestions.append(content)
                else:
                    video_suggestions.append("")

            row_to_write = [original_transcript, json.dumps(suggested_clips, indent=2)] + video_suggestions + ["", ""]
            writer.writerow(row_to_write)
            logger.info(f"Successfully saved analysis to {csv_file_path}")
    except Exception as e:
        logger.error(f"An unexpected error in save_analysis_to_csv: {e}", exc_info=True)


def get_youtube_id(url):
    # This function remains unchanged from your original code
    # ... (function body) ...
    if not url: return None
    query = urlparse(url)
    if query.hostname in ('youtu.be', 'www.youtube.com', 'youtube.com'):
        if query.path == '/watch': return parse_qs(query.query).get('v', [None])[0]
        if query.path.startswith(('/embed/', '/v/')): return query.path.split('/')[2]
    if query.hostname == 'youtu.be': return query.path[1:]
    return None

# In shorts_app/views.py

def regenerate_social_content(request, short_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

    try:
        short = get_object_or_404(GeneratedShort, id=short_id)
        
        # Call the existing AI helper function
        social_post_data = generate_social_post_content(short.title, short.description)
        
        if social_post_data:
            # Update the short in the database with the new content
            short.social_title = social_post_data.get('catchy_title')
            short.social_description = social_post_data.get('engaging_description')
            short.social_hashtags = social_post_data.get('hashtags', [])
            short.save()
            
            # Return the newly generated content
            return JsonResponse({
                'status': 'success',
                'social_title': short.social_title,
                'social_description': short.social_description,
                'social_hashtags': short.social_hashtags
            })
        else:
            return JsonResponse({'status': 'error', 'message': 'Failed to generate content from AI.'}, status=500)

    except Exception as e:
        logger.error(f"Error regenerating social content: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Error: {e}'}, status=500)


def index(request):
    # This function remains unchanged from your original code
    processed_videos = DownloadedVideo.objects.all().order_by('-created_at')
    generated_shorts = GeneratedShort.objects.select_related('parent_video').order_by('-created_at')
    return render(request, 'shorts_app/index.html', {'videos': processed_videos, 'shorts': generated_shorts})


def check_progress(request, task_id):
    # This function remains unchanged from your original code
    return JsonResponse(cache.get(task_id, {"status": "PENDING", "progress": 0, "message": "Initializing..."}))
def process_video(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'})

    try:
        # The request body is expected to be JSON now, thanks to the frontend fix
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON body.'}, status=400)

    video_url = data.get('video_url')
    # If the client used the 'Use Previous Video' button, the payload will contain video_id
    video_id_from_payload = data.get('video_id')

    if not video_url and not video_id_from_payload:
        return JsonResponse({'status': 'error', 'message': 'No video URL or ID provided.'}, status=400)
    
    # If video_id is present, we are using a previously downloaded video and skip download.
    if video_id_from_payload:
        video_url = f"https://www.youtube.com/watch?v={video_id_from_payload}" # Dummy URL for consistent logging

    task_id = str(uuid.uuid4())
    cache.set(task_id, {"status": "starting", "progress": 0, "message": "Initializing task..."})

    def background_task():
        video_id = None
        try:
            # --- 1. HANDLE EXISTING VIDEO ---
            if video_id_from_payload:
                video_id = video_id_from_payload
                video_obj = get_object_or_404(DownloadedVideo, video_id=video_id)
                
                if video_obj.suggestions and video_obj.suggestions.get('clips'):
                    suggestions = video_obj.suggestions
                    logger.info(f"Using cached AI suggestions for video ID: {video_id}")
                    title = video_obj.title
                else:
                    transcript_file = os.path.join(settings.MEDIA_ROOT, 'videos', f"{video_id}.en.vtt")
                    transcript = ""
                    if os.path.exists(transcript_file):
                        with open(transcript_file, 'r', encoding='utf-8') as f:
                            transcript = f.read()
                    
                    logger.info(f"Re-running AI suggestions for existing video {video_id}...")
                    suggestions = get_ai_suggested_clips(transcript, video_obj.duration) or {"clips": []}
                    video_obj.suggestions = suggestions
                    video_obj.save()
                    title = video_obj.title
            
            # --- 2. HANDLE NEW VIDEO DOWNLOAD ---
            else:
                ydl_opts = {
                    'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                    'outtmpl': os.path.join(settings.MEDIA_ROOT, 'videos', '%(id)s.%(ext)s'),
                    'writeautomaticsub': True,
                    'subtitleslangs': ['en'],
                    'quiet': False,
                    'no_check_certificate': True,
                    'extractor_retries': 5,
                    'cookiefile': os.path.join(settings.BASE_DIR, 'cookies.txt'),
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
                }
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    video_id = info['id']
                    title = info['title']
                    duration = int(info.get('duration', 0))
                    file_ext = info.get('ext')
                    file_path = f"/media/videos/{video_id}.{file_ext}"
                    thumbnail_path = f"/media/videos/{video_id}.jpg"

                    # Save thumbnail
                    if info.get('thumbnail'):
                        thumbnail_response = requests.get(info['thumbnail'])
                        with open(os.path.join(settings.MEDIA_ROOT, 'videos', f"{video_id}.jpg"), 'wb') as f:
                            f.write(thumbnail_response.content)

                    # Get AI suggestions
                    transcript = ""
                    transcript_file = os.path.join(settings.MEDIA_ROOT, 'videos', f"{video_id}.en.vtt")
                    if os.path.exists(transcript_file):
                        with open(transcript_file, 'r', encoding='utf-8') as f:
                            transcript = f.read()
                    
                    cache.set(task_id, {"status": "processing", "progress": 80, "message": "Generating AI suggestions..."})
                    logger.info(f"Attempting to get AI suggestions for {video_id}...")
                    
                    suggestions = get_ai_suggested_clips(transcript, duration) or {"clips": []}
                    
                    if not suggestions:
                        logger.warning(f"AI suggestions failed or returned empty for {video_id}. Falling back to empty suggestions.")
                        suggestions = {"clips": []}

                    # Save to database
                    DownloadedVideo.objects.update_or_create(
                        video_id=video_id,
                        defaults={
                            'title': title,
                            'duration': duration,
                            'file_path': file_path,
                            'thumbnail_path': thumbnail_path,
                            'suggestions': suggestions,
                        }
                    )
            
            # --- 3. FINAL SUCCESS UPDATE ---
            logger.info(f"Video {video_id} data saved to DB and task complete.")
            cache.set(task_id, {
                "status": "complete",
                "progress": 100,
                "message": "Video processed successfully",
                "result": {
                    "video_id": video_id,
                    "video_title": title,
                    "suggested_clips": suggestions.get('clips', [])
                }
            })

        except DownloadError as e:
            if '403' in str(e):
                error_msg = "403 Forbidden: Video may be age-restricted or geo-blocked. Update cookies or check settings."
                logger.error(f"403 error for {video_url}: {str(e)}", exc_info=True)
            else:
                error_msg = f"Download failed: {str(e)}"
                logger.error(f"Download error for {video_url}: {str(e)}", exc_info=True)
            cache.set(task_id, {"status": "error", "progress": 100, "message": error_msg})
        except Exception as e:
            error_msg = f"A critical error occurred: {str(e)}"
            logger.error(f"Error processing video {video_url}: {str(e)}", exc_info=True)
            cache.set(task_id, {"status": "error", "progress": 100, "message": error_msg})

    threading.Thread(target=background_task, daemon=True).start()
    return JsonResponse({'status': 'started', 'task_id': task_id})
def generate_social_post_content(clip_title: str, clip_description: str):
    """
    Generates engaging social media post content for a given video clip.
    """
    if not genai_configured or not genai:
        logger.warning("Gemini AI not configured. Cannot generate social post.")
        return None

    # FIX: Use the stable alias for the Pro model for the best creative results
    model = genai.GenerativeModel('gemini-2.5-pro') 

    prompt = f"""
        You are an expert viral social media marketing strategist with proven experience creating content that achieves millions of views across YouTube Shorts, Instagram Reels, and TikTok. Your task is to create a compelling social media post for a short video clip that maximizes engagement and viral potential.

        **Context and Requirements:**
        - Platform focus: YouTube Shorts, Instagram Reels, TikTok
        - Goal: Maximum engagement, shareability, and viral potential
        - Audience: All People ages, primarily 18-34, interested in trending and relatable content
        - Brand voice: Professional/Casual/Humorous 

        **Clip Information:**
        - Title: "{clip_title}"
        - Description: "{clip_description}"

        **Generate the following optimized content:**

        1. **catchy_title**: Create a scroll-stopping, click-worthy title that:
        - Uses power words and emotional triggers
        - Includes numbers or "How to" when relevant
        - Stays under 60 characters for mobile optimization
        - Incorporates 1-2 strategic emojis
        - Creates curiosity or promises value

        2. **engaging_description**: Write a compelling description that:
        - Opens with a hook that grabs attention in the first line
        - Explains the video's value proposition clearly
        - Uses short, punchy sentences (max 15 words each)
        - Includes strategic line breaks for mobile readability
        - Incorporates a strong call-to-action
        - Adds 2-3 relevant emojis for visual appeal
        - Ends with an engagement question to boost comments

        3. **hashtags**: Provide an array of 12-15 strategic hashtags that include:
        - 3-4 trending/broad hashtags (high volume)
        - 4-5 niche-specific hashtags (targeted audience)
        - 3-4 community hashtags (engagement-focused)
        - 2-3 branded or unique hashtags
        - Mix of popular and less competitive tags

        4. **best_posting_time**: Suggest optimal posting times based on platform and audience

        5. **engagement_strategy**: Provide 2-3 specific tactics to boost initial engagement

        **Output Format Requirements:**
        Respond ONLY with a valid JSON object containing these exact keys: "catchy_title", "engaging_description", "hashtags", "best_posting_time", "engagement_strategy". No markdown formatting, no additional text, no code blocks.

        **Success Criteria:**
        The content should be designed to achieve high watch time, strong engagement rates, and maximum shareability while maintaining authenticity and brand alignment.

    """
    
    cleaned_text = "" # Define here to be accessible in the exception block
    try:
        response = model.generate_content(prompt)
        
        # More robust cleaning to handle markdown code blocks
        cleaned_text = response.text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        # Find the start of the actual JSON object
        json_start_index = cleaned_text.find('{')
        if json_start_index != -1:
            json_response_text = cleaned_text[json_start_index:]
            return json.loads(json_response_text)
        else:
            # If no '{' is found, the response is invalid
            raise json.JSONDecodeError("No JSON object found in the response", cleaned_text, 0)
            
    except json.JSONDecodeError as e:
        # The log will now show the cleaned text for better debugging
        logger.error(f"Failed to decode JSON from Gemini API: {e}\nCleaned response text was: {cleaned_text}")
        return None
    except Exception as e:
        logger.error(f"Error generating social post content: {e}", exc_info=True)
        return None



def generate_short(request):
    if request.method != 'POST': return JsonResponse({'status': 'error', 'message': 'Invalid request.'})
    try:
        data = json.loads(request.body)
        video_id, clip_data, aspect_ratio = data.get('video_id'), data.get('clip_data', {}), data.get('aspect_ratio', '9:16')
        parent_video = get_object_or_404(DownloadedVideo, video_id=video_id)
        video_full_path = os.path.join(settings.BASE_DIR, parent_video.file_path.lstrip('/'))
        
        def time_to_seconds(t): return sum(int(x) * 60 ** i for i, x in enumerate(reversed(t.split(':'))))
        start_s, end_s = time_to_seconds(clip_data.get('start_time')), time_to_seconds(clip_data.get('end_time'))

        with VideoFileClip(video_full_path) as video:
            subclip = video.subclip(start_s, min(end_s, video.duration))
            audio_codec_to_use = "aac" if subclip.audio is not None else None
            (w, h), final_clip = subclip.size, subclip
            if aspect_ratio == '9:16':
                final_clip = CompositeVideoClip([ColorClip(size=(1080, 1920), color=(0,0,0)), subclip.resize(width=1080).set_position("center")], use_bgclip=True)
            elif aspect_ratio == '16:9':
                target_h = int(w * 9 / 16)
                if h > target_h: final_clip = crop(subclip, height=target_h, y_center=h / 2)

            shorts_dir = os.path.join(settings.MEDIA_ROOT, 'shorts')
            os.makedirs(shorts_dir, exist_ok=True)
            short_uuid = uuid.uuid4()
            short_filename, thumb_filename = f'{short_uuid}.mp4', f'{short_uuid}.png'
            short_path, thumb_path = os.path.join(shorts_dir, short_filename), os.path.join(shorts_dir, thumb_filename)

            final_clip.write_videofile(short_path, codec="libx264", audio_codec=audio_codec_to_use, threads=os.cpu_count() or 1, preset="medium")
            final_clip.save_frame(thumb_path, t=final_clip.duration / 2)

        social_post_data = generate_social_post_content(clip_data.get('title'), clip_data.get('description')) or {}
        new_short = GeneratedShort.objects.create(id=short_uuid, parent_video=parent_video, title=clip_data.get('title'), description=clip_data.get('description'), tags=clip_data.get('tags', []), short_path=f'/media/shorts/{short_filename}', thumbnail_path=f'/media/shorts/{thumb_filename}', start_time=clip_data.get('start_time'), end_time=clip_data.get('end_time'), social_title=social_post_data.get('catchy_title'), social_description=social_post_data.get('engaging_description'), social_hashtags=social_post_data.get('hashtags', []))

        return JsonResponse({'status': 'success', 'new_short_details': {
            'id': str(new_short.id), 
            'title': new_short.title, 
            'description': new_short.description, 
            'thumbnail_path': new_short.thumbnail_path, 
            'short_path': new_short.short_path, 
            'download_url': f"/download_short/{short_filename}/", 
            'social_title': new_short.social_title, 
            'social_description': new_short.social_description, 
            'social_hashtags': new_short.social_hashtags or []
        }})
    except Exception as e:
        logger.error(f"Error generating short: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Error: {e}'}, status=500)


def download_short(request, filename):
    # This function remains unchanged from your original code
    file_path = os.path.join(settings.MEDIA_ROOT, 'shorts', filename)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
    else:
        raise Http404


def _delete_files(paths):
    # This function remains unchanged from your original code
    # ... (function body) ...
    for rel_path in paths:
        if not rel_path: continue
        full_path = os.path.join(settings.BASE_DIR, rel_path.lstrip('/'))
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError as e:
                logger.error(f"Failed to delete file {full_path}: {e}")


def delete_video(request, video_id):
    # This function remains unchanged from your original code
    # ... (function body) ...
    if request.method == 'POST':
        video = get_object_or_404(DownloadedVideo, video_id=video_id)
        _delete_files([video.file_path, video.thumbnail_path, f'/media/videos/{video.video_id}.en.vtt'])
        video.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


def delete_short(request, short_id):
    # This function remains unchanged from your original code
    # ... (function body) ...
    if request.method == 'POST':
        short = get_object_or_404(GeneratedShort, id=short_id)
        _delete_files([short.short_path, short.thumbnail_path])
        short.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

def get_trending_videos(request):
    api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
    if not api_key:
        return JsonResponse({'status': 'error', 'message': 'YouTube API key not configured.'}, status=500)
    
    topic, page_token = request.GET.get('topic'), request.GET.get('pageToken')
    try:
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)
        videos, next_page_token = [], None
        
        if topic:
            req = youtube.search().list(part='snippet', q=topic, type='video', videoDefinition='high', maxResults=12, order='date', pageToken=page_token or None)
            res = req.execute()
            video_ids = [item['id']['videoId'] for item in res.get('items', []) if item.get('id', {}).get('kind') == 'youtube#video']
            if video_ids:
                video_req = youtube.videos().list(part='snippet', id=','.join(video_ids))
                video_res = video_req.execute()
                videos = [{'video_id': i['id'], 'title': i['snippet']['title'], 'thumbnail_url': i['snippet']['thumbnails'].get('high', {}).get('url'), 'video_url': f"https://www.youtube.com/watch?v={i['id']}"} for i in video_res.get('items', [])]
            next_page_token = res.get('nextPageToken')
        else:
            req = youtube.videos().list(part='snippet', chart='mostPopular', regionCode='US', maxResults=12, pageToken=page_token or None)
            res = req.execute()
            videos = [{'video_id': i['id'], 'title': i['snippet']['title'], 'thumbnail_url': i['snippet']['thumbnails'].get('high', {}).get('url'), 'video_url': f"https://www.youtube.com/watch?v={i['id']}"} for i in res.get('items', [])]
            next_page_token = res.get('nextPageToken')
            
        return JsonResponse({'status': 'success', 'videos': videos, 'nextPageToken': next_page_token})
    except googleapiclient.errors.HttpError as e:
        msg = f"YouTube API error: {e.resp.status} - {e.content.decode('utf-8')}"
        logger.error(msg)
        return JsonResponse({'status': 'error', 'message': msg}, status=e.resp.status)
    except Exception as e:
        logger.error(f"Error fetching trending videos: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Error: {e}'}, status=500)
