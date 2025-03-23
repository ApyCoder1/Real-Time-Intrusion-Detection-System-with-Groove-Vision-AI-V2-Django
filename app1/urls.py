from django.urls import path
from . import views

urlpatterns = [
    path('upload_image/',views.upload_image, name='upload_image'),
    path('images/', views.image_list, name='image_list'),  # For JSON response
    path('', views.image_list_template, name='image_list_template'),  # For HTML view


]
