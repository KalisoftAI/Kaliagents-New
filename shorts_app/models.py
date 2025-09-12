# In shorts_app/models.py
import uuid
from django.db import models

class DownloadedVideo(models.Model):
    video_id = models.CharField(max_length=20, unique=True, primary_key=True)
    title = models.CharField(max_length=255)
    duration = models.IntegerField()
    file_path = models.CharField(max_length=512)
    thumbnail_path = models.CharField(max_length=512, null=True, blank=True)
    suggestions = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class GeneratedShort(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_video = models.ForeignKey(DownloadedVideo, on_delete=models.CASCADE, related_name='shorts')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list)
    short_path = models.CharField(max_length=512)
    thumbnail_path = models.CharField(max_length=512)
    start_time = models.CharField(max_length=12)
    end_time = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)

    # --- NEW FIELDS TO STORE AI-GENERATED SOCIAL CONTENT ---
    social_title = models.CharField(max_length=255, blank=True, null=True)
    social_description = models.TextField(blank=True, null=True)
    social_hashtags = models.JSONField(default=list, null=True, blank=True)
    
    def __str__(self):
        return f"Short: {self.title}"
