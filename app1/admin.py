
# admin.py
from django.contrib import admin
from .models import UploadedImage

class UploadedImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'image', 'uploaded_at')  # Display the image, ID, and upload date in the list view
    search_fields = ('id',)  # Enable searching by image ID
    list_filter = ('uploaded_at',)  # Allow filtering by upload date

admin.site.register(UploadedImage, UploadedImageAdmin)
