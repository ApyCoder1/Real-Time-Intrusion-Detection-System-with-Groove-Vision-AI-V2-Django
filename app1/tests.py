import os
import cv2
import numpy as np
import torch
import time
import base64
import pygame  # Import pygame for playing sounds
import threading
import json
from django.utils.timezone import now
from facenet_pytorch import InceptionResnetV1, MTCNN
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.utils import timezone
from .models import Employe, Attendance,CameraConfiguration,EmailConfig,Settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .models import LateCheckInPolicy
from .forms import LateCheckInPolicyForm
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import Attendance, EmailConfig,Leave  # Import models
from .models import Department,FaceEmbedding
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError
from .forms import LeaveForm
from django.shortcuts import render, get_object_or_404, redirect
from .models import Leave
from django.db.models import Q
###############################################################


####################################################################
# Home page view
def home(request):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return render(request, 'home.html')  # Display the home page for unauthenticated users
    
    # If the user is authenticated, check if they are admin or Employe
    if request.user.is_staff:
        return redirect('admin_dashboard')
    
    try:
        # Attempt to fetch the Employe's profile
        employe_profile = Employe.objects.get(user=request.user)
        # If the Employe profile exists, redirect to the Employe dashboard
        return redirect('employe_dashboard')
    except Employe.DoesNotExist:
        # If no Employe profile exists, redirect to an error page or home page
        return render(request, 'home.html')  # You can customize this if needed

##############################################################
def is_admin(user):
    return user.is_superuser

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    
    # Count total Employe
    total_employes = Employe.objects.count()

    # Total attendance records for today
    total_attendance = Attendance.objects.count()

    # Total present Employe for today
    total_present = Attendance.objects.filter(status='Present').count()

    # Total absent Employe for today
    total_absent = Attendance.objects.filter(status='Absent').count()

    # Total late check-ins for today
    total_late_checkins = Attendance.objects.filter(is_late=True).count()

    # Total check-ins for today
    total_checkins = Attendance.objects.filter(check_in_time__isnull=False).count()

    # Total check-outs for today
    total_checkouts = Attendance.objects.filter(check_out_time__isnull=False).count()

    # Total number of cameras
    total_cameras = CameraConfiguration.objects.count()
    # Total number of cameras


    # Passing the data to the template
    context = {
        'total_employes': total_employes,
        'total_attendance': total_attendance,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_late_checkins': total_late_checkins,
        'total_checkins': total_checkins,
        'total_checkouts': total_checkouts,
        'total_cameras': total_cameras,
    }

    return render(request, 'admin/admin-dashboard.html', context)

##############################################################

def mark_attendance(request):
    return render(request, 'Mark_attendance.html')

#############################################################
# Initialize MTCNN and InceptionResnetV1
mtcnn = MTCNN(keep_all=True)
resnet = InceptionResnetV1(pretrained='vggface2').eval()

# Function to detect and encode faces
def detect_and_encode(image):
    with torch.no_grad():
        boxes, _ = mtcnn.detect(image)
        if boxes is not None:
            faces = []
            for box in boxes:
                face = image[int(box[1]):int(box[3]), int(box[0]):int(box[2])]
                if face.size == 0:
                    continue
                face = cv2.resize(face, (160, 160))
                face = np.transpose(face, (2, 0, 1)).astype(np.float32) / 255.0
                face_tensor = torch.tensor(face).unsqueeze(0)
                encoding = resnet(face_tensor).detach().numpy().flatten()
                faces.append(encoding)
            return faces
    return []


# Function to encode all uploaded images based on face embeddings
def encode_uploaded_images():
    known_face_encodings = []
    known_face_names = []

    # Fetch only authorized employees who have face embeddings
    authorized_employees = Employe.objects.filter(authorized=True)

    for employe in authorized_employees:
        # Fetch all face embeddings for the employee
        face_embeddings = FaceEmbedding.objects.filter(employe=employe)

        for embedding in face_embeddings:
            known_face_encodings.append(np.array(embedding.embedding))
            known_face_names.append(employe.name)  # Append the employee name for each embedding

    return known_face_encodings, known_face_names

# Function to recognize faces
def recognize_faces(known_encodings, known_names, test_encodings, threshold=0.6):
    recognized_names = []
    for test_encoding in test_encodings:
        distances = np.linalg.norm(known_encodings - test_encoding, axis=1)
        min_distance_idx = np.argmin(distances)
        if distances[min_distance_idx] < threshold:
            recognized_names.append(known_names[min_distance_idx])
        else:
            recognized_names.append('Not Recognized')
    return recognized_names

#####################################################################

############################################################################
@csrf_exempt
def capture_and_recognize(request):
    if request.method != 'POST':
        return JsonResponse({'message': 'Invalid request method.'}, status=405)

    try:
        current_time = timezone.now()
        today = current_time.date()

        # Fetch global settings
        settings = Settings.objects.first()
        if not settings:
            return JsonResponse({'message': 'Settings not configured.'}, status=500)

        global_check_out_threshold_seconds = settings.check_out_time_threshold

        # Mark absent Employe and update leave attendance
        update_leave_attendance(today)

        # Parse image data from request
        data = json.loads(request.body)
        image_data = data.get('image')
        if not image_data:
            return JsonResponse({'message': 'No image data received.'}, status=400)

        # Decode the Base64 image
        image_data = image_data.split(',')[1]  # Remove Base64 prefix
        image_bytes = base64.b64decode(image_data)
        np_img = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

        # Convert BGR to RGB for face recognition
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Detect and encode faces
        test_face_encodings = detect_and_encode(frame_rgb)
        if not test_face_encodings:
            return JsonResponse({'message': 'No face detected.'}, status=200)

        # Retrieve known face encodings and recognize faces
        known_face_encodings, known_face_names = encode_uploaded_images()
        if not known_face_encodings:
            return JsonResponse({'message': 'No known faces available.'}, status=200)

        recognized_names = recognize_faces(
            np.array(known_face_encodings),
            known_face_names,
            test_face_encodings,
            threshold=0.6
        )

        # Prepare and update attendance records
        attendance_response = []
        for name in recognized_names:
            if name == 'Not Recognized':
                attendance_response.append({
                    'name': 'Unknown',
                    'status': 'Face not recognized',
                    'check_in_time': None,
                    'check_out_time': None,
                    'image_url': '/static/notrecognize.png',
                    'play_sound': False
                })
                continue

            employe = Employe.objects.filter(name=name).first()
            if not employe:
                continue

            # Use Employe-specific setting if available, otherwise use global setting
            employe_threshold_seconds = (
                employe.settings.check_out_time_threshold
                if employe.settings and employe.settings.check_out_time_threshold is not None
                else global_check_out_threshold_seconds
            )

            # Check if the Employe already has an attendance record for today
            attendance = Attendance.objects.filter(employe=employe, date=today).first()

            if not attendance:
                # If no attendance record exists for the Employe, create one
                attendance = Attendance.objects.create(employe=employe, date=today, status='Absent')

            # Handle attendance update for Employe
            if attendance.status == 'Leave':
                attendance_response.append({
                    'name': name,
                    'status': 'Leave',
                    'check_in_time': None,
                    'check_out_time': None,
                    'image_url': '/static/enjoye.jpg',
                    'play_sound': False
                })
            elif attendance.check_in_time is None:
                # Mark checked-in if not already checked-in
                attendance.mark_checked_in()
                attendance.save()

                attendance_response.append({
                    'name': name,
                    'status': 'Checked-in',
                    'check_in_time': attendance.check_in_time.isoformat() if attendance.check_in_time else None,
                    'check_out_time': None,
                    'image_url': '/static/success.png',
                    'play_sound': True
                })
            elif attendance.check_out_time is None and current_time >= attendance.check_in_time + timedelta(seconds=employe_threshold_seconds):
                # Mark checked-out if applicable
                attendance.mark_checked_out()
                attendance.save()

                attendance_response.append({
                    'name': name,
                    'status': 'Checked-out',
                    'check_in_time': attendance.check_in_time.isoformat(),
                    'check_out_time': attendance.check_out_time.isoformat(),
                    'image_url': '/static/success.png',
                    'play_sound': True
                })
            else:
                attendance_response.append({
                    'name': name,
                    'status': 'Already checked-in' if not attendance.check_out_time else 'Already checked-out',
                    'check_in_time': attendance.check_in_time.isoformat(),
                    'check_out_time': attendance.check_out_time.isoformat() if attendance.check_out_time else None,
                    'image_url': '/static/success.png',
                    'play_sound': False
                })

        return JsonResponse({'attendance': attendance_response}, status=200)

    except Exception as e:
        return JsonResponse({'message': f"Error: {str(e)}"}, status=500)


def update_leave_attendance(today):
    """
    Function to update attendance for Employe on leave and those without leave approval (Absent).
    """
    # Fetch the leaves approved for today
    approved_leaves = Leave.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
        approved=True
    )

    # Create a set of Employe with approved leave for today
    approved_leave_employe = {leave.employe.id for leave in approved_leaves}

    # Debugging log to check approved leaves and Employe ids
    # print(f"Approved Leave Employe IDs: {approved_leave_Employe}")

    # Mark attendance for leave Employe
    employe = Employe.objects.all()
    for employe in employe:
        # Check if the Employe has an attendance record for today
        existing_attendance = Attendance.objects.filter(employe=employe, date=today).first()

        # If the Employe has approved leave and no attendance record, mark as "Leave"
        if employe.id in approved_leave_employe:
            if not existing_attendance:
                # print(f"Marking {Employe.name} as Leave")  # Debug log
                Attendance.objects.create(employe=employe, date=today, status='Leave')
        else:
            # If no approved leave and no attendance record, mark as "Absent"
            if not existing_attendance:
                # print(f"Marking {Employe.name} as Absent")  # Debug log
                Attendance.objects.create(employe=employe, date=today, status='Absent')


#######################################################################

# Function to detect and encode faces
def detect_and_encode_uploaded_image_for_register(image):
    with torch.no_grad():
        boxes, _ = mtcnn.detect(image)
        if boxes is not None:
            for box in boxes:
                face = image[int(box[1]):int(box[3]), int(box[0]):int(box[2])]
                if face.size == 0:
                    continue
                face = cv2.resize(face, (160, 160))
                face = np.transpose(face, (2, 0, 1)).astype(np.float32) / 255.0
                face_tensor = torch.tensor(face).unsqueeze(0)
                encoding = resnet(face_tensor).detach().numpy().flatten()
                return encoding
    return None
######################################################################
from PIL import Image
# View for uploading an image and storing the embedding
def upload_face_image(request):
    employees = Employe.objects.all()  # Fetch all employees (only for admins)

    if request.method == 'POST' and request.FILES['image']:
        uploaded_image = request.FILES['image']
        employee_id = request.POST.get('employee')  # Get the selected employee ID
        employee = Employe.objects.get(id=employee_id)

        image = Image.open(uploaded_image).convert("RGB")  # Convert to RGB
        image_np = np.array(image)

        # Get the face embedding
        embedding = detect_and_encode_uploaded_image_for_register(image_np)

        if embedding is not None:
            # Save embedding to the database
            FaceEmbedding.objects.create(
                employe=employee,
                embedding=embedding.tolist()  # Convert numpy array to list
            )
            return JsonResponse({"message": "Face embedding saved successfully!", "status": "success"})
        else:
            return JsonResponse({"message": "No face detected in the image.", "status": "error"})

    return render(request, 'yolo/upload_image.html', {'employees': employees})

############################################################################################
def register_employe(request):
    if request.method == 'POST':
        try:
            # Get Employee information from the form
            name = request.POST.get('name')
            email = request.POST.get('email')
            phone_number = request.POST.get('phone_number')
            images = request.FILES.getlist('images')  # Multiple uploaded images
            emp_id = request.POST.get('emp_id')
            address = request.POST.get('address')

            # Convert numeric values properly, handling empty strings
            def safe_float(value):
                return float(value) if value.strip() else 0.0  # Convert to float only if non-empty

            base_salary = safe_float(request.POST.get('base_salary', '0'))
            allowances = safe_float(request.POST.get('allowances', '0'))
            per_day_salary = safe_float(request.POST.get('per_day_salary', '0'))
            
            date_of_birth = request.POST.get('date_of_birth')
            joining_date = request.POST.get('joining_date')
            mother_name = request.POST.get('mother_name')
            father_name = request.POST.get('father_name')
            department_ids = request.POST.getlist('department')
            username = request.POST.get('username')
            password = request.POST.get('password')

            # Check for existing username
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists. Please choose another one.')
                return render(request, 'register_employe.html')

            # Check for existing employee ID
            if Employe.objects.filter(emp_id=emp_id).exists():
                messages.error(request, 'Employee ID already exists. Please use a different one.')
                return render(request, 'register_employe.html')

            # Create the user
            user = User.objects.create_user(username=username, email=email, password=password)
            user.save()

            # Create the Employee record
            employe = Employe(
                user=user,
                name=name,
                email=email,
                phone_number=phone_number,
                authorized=False,
                emp_id=emp_id,
                address=address,
                allowances=allowances,
                base_salary=base_salary,
                per_day_salary=per_day_salary,
                date_of_birth=date_of_birth,
                joining_date=joining_date,
                mother_name=mother_name,
                father_name=father_name,
            )
            employe.save()

            # Assign departments to employee
            employe.department.set(Department.objects.filter(id__in=department_ids))

            # Process each uploaded image to extract face embeddings
            for image_file in images:
                image_array = np.frombuffer(image_file.read(), np.uint8)
                image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                face_embedding = detect_and_encode_uploaded_image_for_register(image_rgb)

                if face_embedding is not None:
                    FaceEmbedding.objects.create(employe=employe, embedding=face_embedding.tolist())

            messages.success(request, 'Registration successful! Welcome.')
            return redirect('register_success')

        except Exception as e:
            print(f"Error during registration: {e}")
            messages.error(request, 'An error occurred during registration. Please try again.')
            return render(request, 'register_employe.html')

    # Query all necessary data to pass to the template
    departments = Department.objects.all()

    return render(request, 'register_employe.html', {
        'departments': departments,
    })

########################################################################

# Success view after capturing Employe information and image
def register_success(request):
    return render(request, 'register_success.html')

#########################################################################

#this is for showing Attendance list
def is_admin(user):
    return user.is_superuser

@login_required
@user_passes_test(is_admin)
def employe_attendance_list(request):
    # Get the search query, date filter, roll number filter, and attendance status filter from the request
    search_query = request.GET.get('search', '')
    date_filter = request.GET.get('attendance_date', '')
    roll_no_filter = request.GET.get('roll_no', '')  # Filter by roll number
    status_filter = request.GET.get('status', '')  # Filter by status (Present/Absent)

    # Get all Employe
    employe = Employe.objects.all()

    # Filter Employe based on the search query (name)
    if search_query:
        employe = employe.filter(name__icontains=search_query)

    # Filter Employe based on roll number if provided
    if roll_no_filter:
        employe = employe.filter(emp_id__icontains=roll_no_filter)

    # Prepare the attendance data
    employe_attendance_data = []
    total_attendance_count = 0  # Initialize the total attendance count

    for employe in employe:
        # Get the attendance records for each Employe
        attendance_records = Attendance.objects.filter(employe=employe)

        # Filter by date if provided
        if date_filter:
            # Assuming date_filter is in the format YYYY-MM-DD
            attendance_records = attendance_records.filter(date=date_filter)

        # Filter by status if provided
        if status_filter:
            attendance_records = attendance_records.filter(status=status_filter)

        # Order attendance records by date
        attendance_records = attendance_records.order_by('date')

        # Count the attendance records for this Employe
        employe_attendance_count = attendance_records.count()
        total_attendance_count += employe_attendance_count  # Add to the total count

        employe_attendance_data.append({
            'employe': employe,
            'attendance_records': attendance_records,
            'attendance_count': employe_attendance_count  # Add count per Employe
        })

    context = {
        'employe_attendance_data': employe_attendance_data,
        'search_query': search_query,  # Pass the search query to the template
        'date_filter': date_filter,    # Pass the date filter to the template
        'roll_no_filter': roll_no_filter,  # Pass the roll number filter to the template
        'status_filter': status_filter,  # Pass the status filter to the template
        'total_attendance_count': total_attendance_count  # Pass the total attendance count to the template
    }

    return render(request, 'employe_attendance_list.html', context)



######################################################################

@staff_member_required
def employe_list(request):
    employes = Employe.objects.all()
    return render(request, 'employe_list.html', {'employes': employes})

@staff_member_required
def employe_detail(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    return render(request, 'employe_detail.html', {'employe': employe})

@staff_member_required
def employe_authorize(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    
    if request.method == 'POST':
        authorized = request.POST.get('authorized', False)
        employe.authorized = bool(authorized)
        employe.save()
        return redirect('employe-list')
    
    return render(request, 'employe_authorize.html', {'employe': employe})

###############################################################################

def employe_edit(request, pk):
    employe = get_object_or_404(Employe, pk=pk)

    if request.method == 'POST':
        # Updating employee details manually
        employe.name = request.POST.get('name', employe.name)
        employe.email = request.POST.get('email', employe.email)
        employe.phone_number = request.POST.get('phone_number', employe.phone_number)
        employe.emp_id = request.POST.get('emp_id', employe.emp_id)
        employe.address = request.POST.get('address', employe.address)
        employe.date_of_birth = request.POST.get('date_of_birth', employe.date_of_birth)
        employe.joining_date = request.POST.get('joining_date', employe.joining_date)
        employe.mother_name = request.POST.get('mother_name', employe.mother_name)
        employe.father_name = request.POST.get('father_name', employe.father_name)
        employe.base_salary = request.POST.get('base_salary', employe.base_salary)
        employe.allowances = request.POST.get('allowances', employe.allowances)
        employe.per_day_salary = request.POST.get('per_day_salary', employe.per_day_salary)
        employe.authorized = request.POST.get('authorized') == 'on'  # Handling checkbox

        employe.save()
        messages.success(request, 'Employee details updated successfully.')
        return redirect('employe-detail', pk=employe.pk)

    return render(request, 'employe_edit.html', {'employe': employe})
###########################################################
# This views is for Deleting Employe
@staff_member_required
def employe_delete(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    
    if request.method == 'POST':
        employe.delete()
        messages.success(request, 'Employe deleted successfully.')
        return redirect('employe-list')  # Redirect to the Employe list after deletion
    
    return render(request, 'employe_delete_confirm.html', {'employe': employe})

########################################################################

def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Check if the user is a staff or Employe by checking if they have a linked Employe profile
            try:
                # Attempt to fetch the Employe's profile
                employe_profile = Employe.objects.get(user=user)
                # If the Employe profile exists, redirect to the Employe dashboard
                return redirect('employe_dashboard')
            except Employe.DoesNotExist:
                # If no Employe profile exists, assume the user is a staff member
                return redirect('admin_dashboard')

        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'login.html')

#########################################################################

# This is for user logout
def user_logout(request):
    logout(request)
    return redirect('login')  # Replace 'login' with your desired redirect URL after logout
##############################################################################
 
@staff_member_required
def send_attendance_notifications(request):
    # Fetch email configuration from the database
    email_config = EmailConfig.objects.first()  # Get the first email configuration or handle multiple configurations

    if email_config is None:
        messages.error(request, "No email configuration found!")
        return render(request, 'notification_sent.html')

    # Set up the email backend dynamically based on the configuration
    settings.EMAIL_HOST = email_config.email_host
    settings.EMAIL_PORT = email_config.email_port
    settings.EMAIL_USE_TLS = email_config.email_use_tls
    settings.EMAIL_HOST_USER = email_config.email_host_user
    settings.EMAIL_HOST_PASSWORD = email_config.email_host_password

    # Filter late Employe who haven't been notified
    late_attendance_records = Attendance.objects.filter(is_late=True, email_sent=False)
    # Filter absent Employe who haven't been notified
    absent_employes = Attendance.objects.filter(status='Absent', email_sent=False)

    # Process late Employe
    for record in late_attendance_records:
        employe = record.employe
        subject = f"Late Check-in Notification for {employe.name}"

        # Render the email content from the HTML template for late employe
        html_message = render_to_string(
            'email_templates/late_attendance_email.html',  # Path to the template
            {'employe': employe, 'record': record}  # Context to be passed into the template
        )

        recipient_email = employe.email

        # Send the email with HTML content
        send_mail(
            subject,
            "This is an HTML email. Please enable HTML content to view it.",
            settings.EMAIL_HOST_USER,
            [recipient_email],
            fail_silently=False,
            html_message=html_message
        )

        # Mark email as sent to avoid resending
        record.email_sent = True
        record.save()

    # Process absent employe
    for record in absent_employes:
        employe = record.employe
        subject = "Absent Attendance Notification"

        # Render the email content from the HTML template for absent employe
        html_message = render_to_string(
            'email_templates/absent_attendance_email.html',  # Path to the new template
            {'employe': employe, 'record': record}  # Context to be passed into the template
        )

        # Send the email notification for absent employe
        send_mail(
            subject,
            "This is an HTML email. Please enable HTML content to view it.",
            settings.EMAIL_HOST_USER,
            [employe.email],
            fail_silently=False,
            html_message=html_message
        )

        # After sending the email, update the `email_sent` field to True
        record.email_sent = True
        record.save()

    # Combine late and absent employe for the response
    all_notified_employes = late_attendance_records | absent_employes

    # Fetch employe who already received the email (email_sent=True)
    already_notified_employes = Attendance.objects.filter(email_sent=True)

    # Display success message
    messages.success(request, "Attendance notifications have been sent successfully!")

    # Return a response with a template that displays the notified employe
    return render(request, 'notification_sent.html', {
        'notified_employes': already_notified_employes  # Show only those who have been notified
    })


############################################################################################

@staff_member_required
def late_checkin_policy_list(request):
    policies = LateCheckInPolicy.objects.select_related('employe').all()
    return render(request, 'latecheckinpolicy_list.html', {'policies': policies})

def create_late_checkin_policy(request):
    if request.method == 'POST':
        form = LateCheckInPolicyForm(request.POST)
        if form.is_valid():
            employe = form.cleaned_data['employe']
            if LateCheckInPolicy.objects.filter(employe=employe).exists():
                messages.error(request, f"A late check-in policy for {employe} already exists.")
            else:
                form.save()
                messages.success(request, "Late check-in policy created successfully!")
                return redirect('late_checkin_policy_list')
    else:
        form = LateCheckInPolicyForm()

    return render(request, 'latecheckinpolicy_form.html', {'form': form})

@staff_member_required
def update_late_checkin_policy(request, policy_id):
    policy = get_object_or_404(LateCheckInPolicy, id=policy_id)
    if request.method == 'POST':
        form = LateCheckInPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, "Late check-in policy updated successfully!")
            return redirect('late_checkin_policy_list')
    else:
        form = LateCheckInPolicyForm(instance=policy)

    return render(request, 'latecheckinpolicy_form.html', {'form': form, 'policy': policy})

@staff_member_required
def delete_late_checkin_policy(request, policy_id):
    policy = get_object_or_404(LateCheckInPolicy, id=policy_id)
    if request.method == 'POST':
        policy.delete()
        messages.success(request, "Late check-in policy deleted successfully!")
        return redirect('late_checkin_policy_list')
    return render(request, 'latecheckinpolicy_confirm_delete.html', {'policy': policy})

#######################################################################################

def capture_and_recognize_with_cam(request):
    stop_events = []  # List to store stop events for each thread
    camera_threads = []  # List to store threads for each camera
    camera_windows = []  # List to store window names
    error_messages = []  # List to capture errors from threads

    def process_frame(cam_config, stop_event):
        """Thread function to capture and process frames for each camera."""
        cap = None
        window_created = False  # Flag to track if the window was created
        try:
            # Check if the camera source is a number (local webcam) or a string (IP camera URL)
            if cam_config.camera_source.isdigit():
                cap = cv2.VideoCapture(int(cam_config.camera_source))  # Use integer index for webcam
            else:
                cap = cv2.VideoCapture(cam_config.camera_source)  # Use string for IP camera URL

            if not cap.isOpened():
                raise Exception(f"Unable to access camera {cam_config.name}.")

            threshold = cam_config.threshold

            # Initialize pygame mixer for sound playback
            pygame.mixer.init()
            success_sound = pygame.mixer.Sound('static/success.wav')  # Load sound path

            window_name = f'Camera Location - {cam_config.location}'
            camera_windows.append(window_name)  # Track the window name

            while not stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    print(f"Failed to capture frame for camera: {cam_config.name}")
                    break  # If frame capture fails, break from the loop

                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                test_face_encodings = detect_and_encode(frame_rgb)  # Function to detect and encode face in frame

                if test_face_encodings:
                    known_face_encodings, known_face_names = encode_uploaded_images()  # Load known face encodings once
                    if known_face_encodings:
                        names = recognize_faces(
                            np.array(known_face_encodings), known_face_names, test_face_encodings, threshold
                        )

                        for name, box in zip(names, mtcnn.detect(frame_rgb)[0]):
                            if box is not None:
                                (x1, y1, x2, y2) = map(int, box)
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

                                if name != 'Not Recognized':
                                    employe = Employe.objects.filter(name=name)
                                    if employe.exists():
                                        employe = employe.first()
                                        print(f"Recognized employe: {employe.name}")  # Debugging log

                                        # Fetch the check-out time threshold
                                        if employe.settings:
                                            check_out_threshold_seconds = employe.settings.check_out_time_threshold

                                        # Check if attendance exists for today
                                        attendance, created = Attendance.objects.get_or_create(
                                            employe=employe, date=now().date()
                                        )

                                        if attendance.check_in_time is None:
                                            attendance.mark_checked_in()
                                            success_sound.play()
                                            cv2.putText(
                                                frame, f"{name}, checked in.", (50, 50), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA
                                            )
                                            print(f"Attendance checked in for {employe.name}")
                                        elif attendance.check_out_time is None:
                                            if now() >= attendance.check_in_time + timedelta(seconds=check_out_threshold_seconds):
                                                attendance.mark_checked_out()
                                                success_sound.play()
                                                cv2.putText(
                                                    frame, f"{name}, checked out.", (50, 50), 
                                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA
                                                )
                                                print(f"Attendance checked out for {employe.name}")
                                            else:
                                                cv2.putText(
                                                    frame, f"{name}, already checked in.", (50, 50), 
                                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA
                                                )
                                        else:
                                            cv2.putText(
                                                frame, f"{name}, already checked out.", (50, 50), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA
                                            )
                                            print(f"Attendance already completed for {employe.name}")

                # Display frame in a separate window for each camera
                if not window_created:
                    cv2.namedWindow(window_name)  # Only create window once
                    window_created = True  # Mark window as created
                cv2.imshow(window_name, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    stop_event.set()  # Signal the thread to stop when 'q' is pressed
                    break

        except Exception as e:
            print(f"Error in thread for {cam_config.name}: {e}")
            error_messages.append(str(e))  # Capture error message
        finally:
            if cap is not None:
                cap.release()
            if window_created:
                cv2.destroyWindow(window_name)  # Only destroy if window was created

    try:
        # Get all camera configurations
        cam_configs = CameraConfiguration.objects.all()
        if not cam_configs.exists():
            raise Exception("No camera configurations found. Please configure them in the admin panel.")

        # Create threads for each camera configuration
        for cam_config in cam_configs:
            stop_event = threading.Event()
            stop_events.append(stop_event)

            camera_thread = threading.Thread(target=process_frame, args=(cam_config, stop_event))
            camera_threads.append(camera_thread)
            camera_thread.start()

        # Keep the main thread running while cameras are being processed
        while any(thread.is_alive() for thread in camera_threads):
            time.sleep(1)  # Non-blocking wait, allowing for UI responsiveness

    except Exception as e:
        error_messages.append(str(e))  # Capture the error message
    finally:
        # Ensure all threads are signaled to stop
        for stop_event in stop_events:
            stop_event.set()

        # Ensure all windows are closed in the main thread
        for window in camera_windows:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) >= 1:  # Check if window exists
                cv2.destroyWindow(window)

    # Check if there are any error messages
    if error_messages:
        # Join all error messages into a single string
        full_error_message = "\n".join(error_messages)
        return render(request, 'error.html', {'error_message': full_error_message})  # Render the error page with message

    return redirect('employe_attendance_list')

##############################################################################

# Function to handle the creation of a new camera configuration
@login_required
@user_passes_test(is_admin)
def camera_config_create(request):
    # Check if the request method is POST, indicating form submission
    if request.method == "POST":
        # Retrieve form data from the request
        name = request.POST.get('name')
        camera_source = request.POST.get('camera_source')
        threshold = request.POST.get('threshold')
        location = request.POST.get('location')

        try:
            # Save the data to the database using the CameraConfiguration model
            CameraConfiguration.objects.create(
                name=name,
                camera_source=camera_source,
                threshold=threshold,
                location=location
            )
            # Redirect to the list of camera configurations after successful creation
            return redirect('camera_config_list')

        except IntegrityError:
            # Handle the case where a configuration with the same name already exists
            messages.error(request, "A configuration with this name already exists.")
            # Render the form again to allow user to correct the error
            return render(request, 'camera/camera_config_form.html')

    # Render the camera configuration form for GET requests
    return render(request, 'camera/camera_config_form.html')


# READ: Function to list all camera configurations
@login_required
@user_passes_test(is_admin)
def camera_config_list(request):
    # Retrieve all CameraConfiguration objects from the database
    configs = CameraConfiguration.objects.all()
    # Render the list template with the retrieved configurations
    return render(request, 'camera/camera_config_list.html', {'configs': configs})


# UPDATE: Function to edit an existing camera configuration
@login_required
@user_passes_test(is_admin)
def camera_config_update(request, pk):
    # Retrieve the specific configuration by primary key or return a 404 error if not found
    config = get_object_or_404(CameraConfiguration, pk=pk)

    # Check if the request method is POST, indicating form submission
    if request.method == "POST":
        # Update the configuration fields with data from the form
        config.name = request.POST.get('name')
        config.camera_source = request.POST.get('camera_source')
        config.threshold = request.POST.get('threshold')
        config.location = request.POST.get('location')

        # Save the changes to the database
        config.save()  

        # Redirect to the list page after successful update
        return redirect('camera_config_list')  
    
    # Render the configuration form with the current configuration data for GET requests
    return render(request, 'camera/camera_config_form.html', {'config': config})


# DELETE: Function to delete a camera configuration
@login_required
@user_passes_test(is_admin)
def camera_config_delete(request, pk):
    # Retrieve the specific configuration by primary key or return a 404 error if not found
    config = get_object_or_404(CameraConfiguration, pk=pk)

    # Check if the request method is POST, indicating confirmation of deletion
    if request.method == "POST":
        # Delete the record from the database
        config.delete()  
        # Redirect to the list of camera configurations after deletion
        return redirect('camera_config_list')

    # Render the delete confirmation template with the configuration data
    return render(request, 'camera/camera_config_delete.html', {'config': config})



######################## start employe views  ####################################

@login_required
def employe_dashboard(request):
    try:
        # Get the employe object for the currently logged-in user
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        messages.error(request, "Employe record does not exist for this user.")
        return redirect('admin_dashboard')  # Redirect to home or profile creation page if employe does not exist

    # Calculate total present, total absent, and total late attendance for the employe
    total_late_count = Attendance.objects.filter(employe=employe, is_late=True).count()
    total_present = Attendance.objects.filter(employe=employe, status='Present').count()
    total_absent = Attendance.objects.filter(employe=employe, status='Absent').count()

    # Calculate total attendance count (Present + Absent + Late)
    total_classes = total_present + total_absent + total_late_count

    # Calculate attendance percentage
    if total_classes > 0:
        attendance_percentage = (total_present / total_classes) * 100
    else:
        attendance_percentage = 0  # If there are no attendance records, set percentage to 0

    # Retrieve the most recent attendance record for the employe
    attendance_records = employe.attendance_set.all().order_by('-date')[:2]

    departments = employe.department.all()  # Get the departments the employe is part of

    context = {
        'employe': employe,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_late_count': total_late_count,
        'attendance_percentage': attendance_percentage,  # Pass the attendance percentage
        'attendance_records': attendance_records,
        'departments': departments,
    }

    return render(request, 'employe/employe-dashboard.html', context)


##############################################################
@login_required
def employe_attendance(request):
    user = request.user
    employe = Employe.objects.get(user=user)  # Fetch the logged-in employe's profile
    
    # Filters for search and date
    search_query = request.GET.get('search', '')
    date_filter = request.GET.get('attendance_date', '')
    
    # Query attendance records for the employe
    attendance_records = Attendance.objects.filter(employe=employe)
    
    if search_query:
        attendance_records = attendance_records.filter(Q(employe__name__icontains=search_query) | 
                                                      Q(employe__roll_no__icontains=search_query))
    
    if date_filter:
        attendance_records = attendance_records.filter(date=date_filter)
    
    # Render the attendance records
    return render(request, 'employe/employe_attendance.html', {
        'employe_attendance_data': attendance_records,
        'search_query': search_query,
        'date_filter': date_filter
    })


##############################################################

# View to add a new email configuration
def add_email_config(request):
    if request.method == 'POST':
        email_host = request.POST.get('email_host')
        email_port = request.POST.get('email_port')
        email_use_tls = request.POST.get('email_use_tls') == 'on'
        email_host_user = request.POST.get('email_host_user')
        email_host_password = request.POST.get('email_host_password')

        # Create and save the new EmailConfig instance
        EmailConfig.objects.create(
            email_host=email_host,
            email_port=email_port,
            email_use_tls=email_use_tls,
            email_host_user=email_host_user,
            email_host_password=email_host_password
        )

        messages.success(request, "Email configuration added successfully.")
        return redirect('view_email_configs')  # Redirect to view the email configs

    return render(request, 'email/add_email_config.html')

# View to edit an existing email configuration
def edit_email_config(request, email_config_id):
    email_config = get_object_or_404(EmailConfig, id=email_config_id)

    if request.method == 'POST':
        email_config.email_host = request.POST.get('email_host')
        email_config.email_port = request.POST.get('email_port')
        email_config.email_use_tls = request.POST.get('email_use_tls') == 'on'
        email_config.email_host_user = request.POST.get('email_host_user')
        email_config.email_host_password = request.POST.get('email_host_password')

        email_config.save()
        messages.success(request, "Email configuration updated successfully.")
        return redirect('view_email_configs')  # Redirect to view the email configs

    return render(request, 'email/edit_email_config.html', {'email_config': email_config})

# View to delete an email configuration
def delete_email_config(request, email_config_id):
    email_config = get_object_or_404(EmailConfig, id=email_config_id)
    email_config.delete()
    messages.success(request, "Email configuration deleted successfully.")
    return redirect('view_email_configs')  # Redirect to view the email configs

# View to list all email configurations
def view_email_configs(request):
    email_configs = EmailConfig.objects.all()
    return render(request, 'email/view_email_configs.html', {'email_configs': email_configs})


###################################################################################

# Department Views
def department_list(request):
    departments = Department.objects.all()
    return render(request, 'department_list.html', {'departments': departments})

def department_create(request):
    if request.method == "POST":
        name = request.POST['name']
        description = request.POST.get('description', '')
        Department.objects.create(name=name, description=description)
        return redirect('department_list')
    return render(request, 'department_form.html')

def department_update(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        department.name = request.POST['name']
        department.description = request.POST.get('description', '')
        department.save()
        return redirect('department_list')
    return render(request, 'department_form.html', {'department': department})

def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        department.delete()
        return redirect('department_list')
    return render(request, 'department_confirm_delete.html', {'department': department})


##############################################################################
def create_settings(request):
    employes = Employe.objects.all()
    if request.method == 'POST':
        employe_id = request.POST.get('employe')
        check_out_time_threshold = request.POST.get('check_out_time_threshold')

        employe = Employe.objects.get(id=employe_id) if employe_id else None

        # Check if settings already exist for the selected employe
        if employe and Settings.objects.filter(employe=employe).exists():
            messages.error(request, f"Check-out Threshold  for employe '{employe.name}' already exist.")
            return redirect('create_settings')

        # Create new settings
        try:
            Settings.objects.create(
                employe=employe, 
                check_out_time_threshold=check_out_time_threshold
            )
            # Success message
            messages.success(request, "Settings created successfully!")
        except IntegrityError:
            messages.error(request, "An error occurred while saving the settings. Please try again.")
            return redirect('create_settings')

        return redirect('settings_list')

    return render(request, 'settings_form.html', {'employes': employes})



# Read settings (list view)
def settings_list(request):
    settings = Settings.objects.all()
    for setting in settings:
        time_in_seconds = setting.check_out_time_threshold

        if time_in_seconds < 60:
            setting.formatted_time = f"{time_in_seconds} seconds"
        elif time_in_seconds < 3600:
            minutes = time_in_seconds // 60
            setting.formatted_time = f"{minutes} minutes"
        else:
            hours = time_in_seconds // 3600
            setting.formatted_time = f"{hours} hours"

    return render(request, 'settings_list.html', {'settings': settings})

# Update settings
def update_settings(request, pk):
    settings = get_object_or_404(Settings, pk=pk)
    
    if request.method == 'POST':
        employe_id = request.POST.get('employe')
        check_out_time_threshold = request.POST.get('check_out_time_threshold', 60)
        
        settings.employe = get_object_or_404(Employe, id=employe_id) if employe_id else None
        settings.check_out_time_threshold = check_out_time_threshold
        settings.save()
        return redirect('settings_list')
    
    employes = Employe.objects.all()
    return render(request, 'settings_form.html', {'settings': settings, 'employes': employes})

# Delete settings
def delete_settings(request, pk):
    settings = get_object_or_404(Settings, pk=pk)
    if request.method == 'POST':
        settings.delete()
        return redirect('settings_list')
    return render(request, 'settings_confirm_delete.html', {'settings': settings})


#################################################################################

# Function to list all leave records
def is_admin(user):
    return user.is_superuser

@login_required
@user_passes_test(is_admin)
def leave_list(request):
    leaves = Leave.objects.all()
    return render(request, 'leave_list.html', {'leaves': leaves})

# Function to delete a leave record
def is_admin(user):
    return user.is_superuser

@login_required
@user_passes_test(is_admin)
def leave_delete(request, pk):
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == "POST":
        leave.delete()
        return redirect('leave_list')
    return render(request, 'leave_confirm_delete.html', {'leave': leave})

# Function to approve a leave
def is_admin(user):
    return user.is_superuser

@login_required
@user_passes_test(is_admin)
def leave_approve(request, pk):
    leave = get_object_or_404(Leave, pk=pk)
    leave.approved = True
    leave.save()
    return redirect('leave_list')

# Function to reject a leave
def is_admin(user):
    return user.is_superuser

@login_required
@user_passes_test(is_admin)
def leave_reject(request, pk):
    leave = get_object_or_404(Leave, pk=pk)
    leave.approved = False
    leave.save()
    return redirect('leave_list')


#########################################################################
@login_required
def employe_leave_list(request):
    # Fetch the leave records of the currently logged-in employe
    employe_profile = Employe.objects.get(user=request.user)
    # Get the leave records for the employe
    employe_leaves = Leave.objects.filter(employe=employe_profile)

    return render(request, 'employe/leave_list.html', {'employe_leaves': employe_leaves})

@login_required
def apply_leave(request):
    # Handle the leave application form
    if request.method == 'POST':
        form = LeaveForm(request.POST)
        if form.is_valid():
            # Associate the leave request with the logged-in employe
            leave = form.save(commit=False)
            employe_profile = Employe.objects.get(user=request.user)
            leave.employe = employe_profile
            leave.save()

            return redirect('employe_leave_list')  # Redirect to the leave list after submitting

    else:
        form = LeaveForm()

    return render(request, 'employe/apply_leave.html', {'form': form})


####################################################

def ppe(request): 
    return render(request, 'yolo/ppe.html')








# views.py

from django.shortcuts import render, redirect
from django.http import HttpResponse
from .models import Salary
from .forms import SalaryForm

from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Salary
from .forms import SalaryForm

def salary_list(request):
    """ List all salaries with filtering, searching, and pagination """
    salaries = Salary.objects.all()

    # Filtering by month and year
    month = request.GET.get('month')
    year = request.GET.get('year')
    if month:
        salaries = salaries.filter(month=month)
    if year:
        salaries = salaries.filter(year=year)

    # Searching by employee name or employee ID
    search_query = request.GET.get('search')
    if search_query:
        salaries = salaries.filter(
            Q(employee__name__icontains=search_query) | 
            Q(employee__emp_id__icontains=search_query)
        )

    # Order the queryset before pagination
    salaries = salaries.order_by('employee__name')  # Or any other field to order by, like 'id', 'month', etc.

    # Pagination
    paginator = Paginator(salaries, 10)  # Show 10 salaries per page
    page_number = request.GET.get('page')
    salaries = paginator.get_page(page_number)

    # Create lists for months and years
    months = list(range(1, 13))  # Months from 1 to 12
    years = list(range(2022, 2026))  # Years from 2022 to 2025

    # Return context including salaries, months, and years
    return render(request, 'salary/salary_list.html', {
        'salaries': salaries,
        'months': months,
        'years': years,
    })

def salary_detail(request, salary_id):
    """ Display salary details """
    salary = get_object_or_404(Salary, id=salary_id)
    return render(request, 'salary/salary_detail.html', {'salary': salary})

def add_salary(request):
    """ Add a new salary record with automatic calculations """
    if request.method == 'POST':
        form = SalaryForm(request.POST)
        if form.is_valid():
            salary = form.save(commit=False)
            salary.save()  # save triggers the model's save() method for calculations
            messages.success(request, "Salary record added successfully.")
            return redirect('salary_list')
        else:
            messages.error(request, "Error adding salary. Please check the form.")
    else:
        form = SalaryForm()
    
    return render(request, 'salary/add_salary.html', {'form': form})

def update_salary(request, salary_id):
    """ Update an existing salary record """
    salary = get_object_or_404(Salary, id=salary_id)
    if request.method == 'POST':
        form = SalaryForm(request.POST, instance=salary)
        if form.is_valid():
            salary = form.save(commit=False)
            salary.save()  # Trigger calculations again
            messages.success(request, "Salary record updated successfully.")
            return redirect('salary_list')
        else:
            messages.error(request, "Error updating salary. Please check the form.")
    else:
        form = SalaryForm(instance=salary)

    return render(request, 'salary/update_salary.html', {'form': form, 'salary': salary})

def delete_salary(request, salary_id):
    """ Delete a salary record """
    salary = get_object_or_404(Salary, id=salary_id)
    if request.method == 'POST':
        salary.delete()
        messages.success(request, "Salary record deleted successfully.")
        return redirect('salary_list')
    
    return render(request, 'salary/delete_salary.html', {'salary': salary})

######################################################

@login_required
def employe_salary_detail(request):
    user = request.user
    employe = Employe.objects.get(user=user)  # Fetch the logged-in employe's profile

    # Fetch salary details for the logged-in employee
    salary_detail = Salary.objects.filter(employee=employe)

    # Filtering by month and year
    month = request.GET.get('month')
    year = request.GET.get('year')

    if month:
        salary_detail = salary_detail.filter(month=month)
    if year:
        salary_detail = salary_detail.filter(year=year)

    # Create lists for months and years
    months = list(range(1, 13))  # Months from 1 to 12
    years = list(range(2022, 2026))  # Years from 2022 to 2025

    # Render the salary details
    return render(request, 'employe/salary_details.html', {
        'salary_detail': salary_detail,
        'months': months,
        'years': years,
        'selected_month': month,
        'selected_year': year,
    })