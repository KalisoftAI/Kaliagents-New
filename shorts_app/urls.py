from django.urls import path
from . import views

app_name = 'shorts_app'

urlpatterns = [
    # Main page
    path('', views.index, name='index'),

    # Background task and video processing URLs
    path('process_video/', views.process_video, name='process_video'),
    path('check_progress/<str:task_id>/', views.check_progress, name='check_progress'),

    # Short generation and management URLs
    path('generate_short/', views.generate_short, name='generate_short'),
    path('download_short/<str:filename>/', views.download_short, name='download_short'),
    path('regenerate_social/<uuid:short_id>/', views.regenerate_social_content, name='regenerate_social_content'),

    # Deletion URLs
    path('delete_video/<str:video_id>/', views.delete_video, name='delete_video'),
    path('delete_short/<uuid:short_id>/', views.delete_short, name='delete_short'),

    # Trending Videos API
    path('get_trending_videos/', views.get_trending_videos, name='get_trending_videos'),
    # Social Media Integration URLs
    path('connect/youtube/', views.youtube_connect, name='youtube_connect'),
    path('youtube/callback/', views.youtube_callback, name='youtube_callback'),
    path('connect/instagram/', views.instagram_connect, name='instagram_connect'),
    path('instagram/callback/', views.instagram_callback, name='instagram_callback'),
    path('edit/add_subtitles/<uuid:short_id>/', views.add_subtitles, name='add_subtitles'),
    # --- POSTING URLs ---
    path('post/youtube/<uuid:short_id>/', views.post_to_youtube, name='post_to_youtube'),
    path('post/instagram/<uuid:short_id>/', views.post_to_instagram, name='post_to_instagram'),
]