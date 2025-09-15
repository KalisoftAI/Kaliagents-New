# In shorts_app/urls.py

from django.urls import path
from . import views

app_name = 'shorts_app'

urlpatterns = [
    # Main page
    path('', views.index, name='index'),

    # Background task and video processing URLs
    path('process_video/', views.process_video, name='process_video'),
    path('check_progress/<str:task_id>/', views.check_progress, name='check_progress'),
    path('post/youtube/<uuid:short_id>/', views.post_to_youtube, name='post_to_youtube'),
    # Short generation and management URLs
    path('generate_short/', views.generate_short, name='generate_short'),
    path('download_short/<str:filename>/', views.download_short, name='download_short'),

    # Deletion URLs
    path('delete_video/<str:video_id>/', views.delete_video, name='delete_video'),
    path('delete_short/<uuid:short_id>/', views.delete_short, name='delete_short'),

    # New: Trending Videos API
    path('get_trending_videos/', views.get_trending_videos, name='get_trending_videos'),
]
