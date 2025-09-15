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
from . import youtube_service

from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, FileResponse, Http404
from django.core.cache import cache
from yt_dlp import YoutubeDL

from moviepy.editor import VideoFileClip, CompositeVideoClip, ColorClip
from moviepy.video.fx.all import crop, resize

from .models import DownloadedVideo, GeneratedShort
import google.generativeai as genai

# Import for YouTube Data API
import googleapiclient.discovery
import googleapiclient.errors

logger = logging.getLogger(__name__)

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


def post_to_youtube(request, short_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

    try:
        # 1. Get the GeneratedShort object from the database
        short = get_object_or_404(GeneratedShort, id=short_id)

        # 2. Construct the full, absolute path to the video file
        video_full_path = os.path.join(settings.BASE_DIR, short.short_path.lstrip('/'))

        # 3. Get the social media content from the short's record
        # We use the AI-generated content if available, otherwise fall back to the original.
        title = short.social_title or short.title
        description = short.social_description or short.description
        tags = short.social_hashtags or short.tags

        # 4. Call the upload function from your new service file
        result = youtube_service.upload_video(
            file_path=video_full_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status="private"  # Or "public" or "unlisted"
        )

        # 5. Return the result to the frontend
        return JsonResponse(result)

    except Exception as e:
        logger.error(f"Error in post_to_youtube view: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {e}'}, status=500)

        
def get_ai_suggested_clips(transcript: str, video_duration: int, video_title: str):
    """
    Analyzes a video transcript to suggest relevant, contextual clips for shorts.
    """
    if not genai_configured or not genai:
        logger.warning("Gemini AI not configured. Cannot generate clip suggestions.")
        return []

    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
        You are an expert viral content strategist specializing in short-form video.

        *Your Task:*
        Analyze the provided timestamped transcript. Identify up to 3 compelling segments ideal for short videos.
        The ideal length for a short is between 15 and 60 seconds.

        For each segment, provide:
        1.  `start_time` and `end_time` in "MM:SS" format, derived strictly from the transcript's timestamps.
        2.  `title`: A concise, highly engaging title for the clip.
        3.  `description`: A brief summary of the clip.
        4.  `tags`: A JSON array of 5-7 relevant keywords.
        5.  `copyright_concern`: A boolean (true/false).

        *Transcript to Analyze:*
        ---
        {transcript}
        ---

        Your output MUST be a valid JSON array of objects, without any markdown formatting.
        """
    
    cleaned_text = "" # Define here to be accessible in the exception block
    try:
        response = model.generate_content(prompt)
        print("response 1", response)
        # More robust cleaning to handle markdown code blocks
        cleaned_text = response.text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        
        # Find the start of the actual JSON array
        json_start_index = cleaned_text.find('[')
        # If a JSON array is found, parse it from that point
        if json_start_index != -1:
            json_response_text = cleaned_text[json_start_index:]
            raw_clips = json.loads(json_response_text)
        else:
            # If no '[' is found, the response is invalid
            raise json.JSONDecodeError("No JSON array found in the response", cleaned_text, 0)

        if isinstance(raw_clips, list):
            # Validate that each item in the list is a dictionary with the required keys
            return [
                c for c in raw_clips
                if isinstance(c, dict) and all(k in c for k in ['start_time', 'end_time', 'title', 'description', 'tags'])
            ]
        else:
            logger.error(f"AI response was not a JSON list as expected. Received: {raw_clips}")
            return []

    except json.JSONDecodeError as e:
        # The log will now show the cleaned text for better debugging
        logger.error(f"Failed to decode JSON from Gemini API response: {e}\nCleaned response text was: {cleaned_text}")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred calling Gemini API: {e}", exc_info=True)
        return []

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
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

    video_url = request.POST.get('video_url')
    video_id = request.POST.get('video_id') or get_youtube_id(video_url)
    
    if not video_id:
        return JsonResponse({'status': 'error', 'message': 'Valid YouTube URL or Video ID is required.'})

    task_id = str(uuid.uuid4())

    def long_running_task():
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                percent_str = d.get('_percent_str', '0.0%').strip()
                cleaned_str = re.sub(r'\x1b\[[0-9;]*m', '', percent_str).replace('%', '')
                try:
                    progress = float(cleaned_str)
                    cache.set(task_id, {"status": "processing", "progress": progress, "message": "Downloading video..."})
                except (ValueError, TypeError):
                    pass 
            elif d['status'] == 'finished':
                cache.set(task_id, {"status": "processing", "progress": 100, "message": "Analyzing transcript..."})

        try:
            output_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
            os.makedirs(output_dir, exist_ok=True)
            video_full_path = os.path.join(output_dir, f'{video_id}.mp4')
            transcript_path = os.path.join(output_dir, f'{video_id}.en.vtt')

            if not os.path.exists(video_full_path) or not os.path.exists(transcript_path):
                if not video_url:
                    cache.set(task_id, {'status': 'error', 'message': 'Video files not found. Please re-process with the original URL.'})
                    return

                ydl_opts = {
                    'format': 'best[height<=1080][ext=mp4]', 'outtmpl': os.path.join(output_dir, f'{video_id}.%(ext)s'),
                    'merge_output_format': 'mp4', 'noplaylist': True, 'writesubtitles': True,
                    'writeautomaticsub': True, 'subtitleslangs': ['en'], 'subtitlesformat': 'vtt',
                    'writethumbnail': True, 'nocolor': True, 'progress_hooks': [progress_hook],
                    'cookiefile': 'cookies.txt', 'ignoreerrors': 'only_subtitles',
                    'sleep_interval': 5, 'max_sleep_interval': 15 
                }
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)

                if not info:
                    cache.set(task_id, {'status': 'error', 'message': 'Download failed. Video may be private or unavailable.'})
                    return
                
                thumbnail_path = f'/media/videos/{video_id}.webp' if os.path.exists(os.path.join(output_dir, f'{video_id}.webp')) else f'/media/videos/{video_id}.jpg'
                DownloadedVideo.objects.update_or_create(
                    video_id=video_id,
                    defaults={
                        'title': info.get('title', 'N/A'), 'duration': info.get('duration', 0),
                        'file_path': f'/media/videos/{video_id}.mp4', 'thumbnail_path': thumbnail_path
                    }
                )

            video_record = get_object_or_404(DownloadedVideo, video_id=video_id)

            suggested_clips = []
            if os.path.exists(transcript_path):
                captions = webvtt.read(transcript_path)
                timestamped_transcript = "\n".join([f"[{c.start} -> {c.end}] {c.text.strip()}" for c in captions])
                if timestamped_transcript:
                    suggested_clips = get_ai_suggested_clips(timestamped_transcript, video_record.duration, video_record.title)
                    save_analysis_to_csv(timestamped_transcript, suggested_clips)
            else:
                logger.warning(f"Transcript file not found at {transcript_path}. Cannot generate suggestions or CSV.")

            video_record.suggestions = suggested_clips
            video_record.save()
            
            cache.set(task_id, {'status': 'complete', 'result': {
                'video_id': video_id,
                'video_title': video_record.title,
                'suggested_clips': video_record.suggestions
            }})

        except Exception as e:
            logger.error(f"Critical error in video processing task for {video_id}: {e}", exc_info=True)
            cache.set(task_id, {'status': 'error', 'message': f'A critical error occurred: {e}'})

    threading.Thread(target=long_running_task).start()
    return JsonResponse({'status': 'processing', 'task_id': task_id})


def generate_social_post_content(clip_title: str, clip_description: str):
    """
    Generates engaging social media post content for a given video clip.
    """
    if not genai_configured or not genai:
        logger.warning("Gemini AI not configured. Cannot generate social post.")
        return None

    model = genai.GenerativeModel('gemini-1.5-flash')

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
