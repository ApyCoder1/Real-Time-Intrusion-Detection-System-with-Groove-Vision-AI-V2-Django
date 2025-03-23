
import base64
import json
from django.http import JsonResponse
from rest_framework.decorators import api_view
from PIL import Image
import io
from django.core.files.base import ContentFile
from .models import UploadedImage  # Import the model
from django.shortcuts import render
from .models import UploadedImage
from django.http import JsonResponse
from datetime import datetime

@api_view(['POST'])
def upload_image(request):
    if request.method == 'POST':
        try:
            # Log incoming request data for debugging
            print(f"Received request data: {request.body.decode('utf-8')}")
            
            # Get the image data from the request body (it should be a JSON object with an 'image' field)
            image_data = request.data.get('image', None)
            if image_data is None:
                return JsonResponse({"error": "No image provided"}, status=400)

            # Decode the Base64 string into binary data
            image_data = base64.b64decode(image_data)

            # Create a file-like object from the binary data
            image_file = ContentFile(image_data, name='uploaded_image.jpg')

            # Save the image to the UploadedImage model
            uploaded_image = UploadedImage.objects.create(image=image_file)

            # Return the response with image ID
            return JsonResponse({"message": "Image uploaded successfully", "image_id": uploaded_image.id})

        except Exception as e:
            print(f"Error: {str(e)}")  # Print the error to the server log
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Invalid HTTP method. Only POST allowed."}, status=405)



# View to display images as JSON (list of image details)
def image_list(request):
    images = UploadedImage.objects.all()

    # Time-based categories
    time_categories = {
        "6 AM - 12 PM": 0,
        "12 PM - 6 PM": 0,
        "6 PM - 12 AM": 0,
        "12 AM - 6 AM": 0,
    }

    image_data = []
    for image in images:
        image_info = {
            "id": image.id,
            "image_url": image.image.url,
            "uploaded_at": image.uploaded_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        image_data.append(image_info)

        # Categorize by time of day
        upload_hour = image.uploaded_at.hour
        if 6 <= upload_hour < 12:
            time_categories["6 AM - 12 PM"] += 1
        elif 12 <= upload_hour < 18:
            time_categories["12 PM - 6 PM"] += 1
        elif 18 <= upload_hour < 24:
            time_categories["6 PM - 12 AM"] += 1
        else:
            time_categories["12 AM - 6 AM"] += 1

    total_images = images.count()

    return JsonResponse({
        "total_images": total_images,
        "images": image_data,
        "time_based_counts": time_categories
    })

# View to render the page (HTML template)
def image_list_template(request):
    return render(request, 'image_list.html')

