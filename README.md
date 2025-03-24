# Real-Time Intrusion Detection System

## Overview
This project is a **Real-Time Intrusion Detection System** built using **Grove Vision AI v2, Xiao ESP32-C3, and Django**. The system detects a person using **[SenseCraft AI](https://sensecraft.seeed.cc/ai/#/home)** on the Grove Vision AI module, captures an image, encodes it to **Base64**, and sends it to a **Django backend** in real-time. When a person is detected, the **ESP32-C3** also triggers an LED indicator.

## Features
- **Real-time person detection** using Grove Vision AI v2.
- **ESP32-C3 processes and sends captured images** to Django via Base64 encoding.
- **Django backend saves images** in the database.
- **LED indication** when a person is detected.
- **Django dashboard to monitor intrusions**, showing:
  - Total detected images.
  - Time-based intrusion counts.
  - Most recent captured images.

## System Architecture
1. **Train Grove Vision AI v2** with SenseCraft AI to detect a person.
2. **ESP32-C3 receives detection results** from Grove Vision AI.
3. **ESP32-C3 captures an image** when a person is detected.
4. **Image is Base64 encoded** and sent to the Django backend.
5. **Django saves the image** in the database and updates the dashboard.
6. **LED glows on ESP32-C3** when a person is detected.

## Tech Stack
- **Hardware:** Grove Vision AI v2, Xiao ESP32-C3.
- **Embedded Programming:** C++ (Arduino framework for ESP32-C3).
- **Backend:** Django (Python).
- **Frontend:** Django Templates (HTML, CSS, JavaScript).

## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/ApyCoder1/Real-Time-Intrusion-Detection-System-with-Groove-Vision-AI-V2-Django

```

### 2. Setup Django Backend
#### Install Dependencies
```bash
pip install -r requirements.txt
```

#### Apply Migrations
```bash
python manage.py migrate
```

#### Run Django Server
```bash
python manage.py runserver 0.0.0.0:8000
```
Your Django API will be available at `http://127.0.0.1:8000/`

### 3. Flash ESP32-C3 with Arduino Code
#### Install Required Libraries
- Install **WiFi.h, HTTPClient.h, mbedtls/base64.h, [Seeed_Arduino_SSCMA](https://github.com/Seeed-Studio/Seeed_Arduino_SSCMA/), Base64.h** in the Arduino IDE.

#### Configure WiFi
Modify the following section in the ESP32 code with your WiFi credentials:
```cpp
const char* ssid = "Your_SSID";
const char* password = "Your_Password";
```

#### Upload Code to ESP32
1. Open **Arduino IDE**.
2. Select **ESP32-C3 Board**.
3. Upload the code to your ESP32-C3.

### 4. Train Grove Vision AI v2
1. Open **[SenseCraft AI](https://sensecraft.seeed.cc/ai/#/home)**.
2. Train the model to detect persons.
3. Flash the trained model to **Grove Vision AI v2**.

## How It Works
1. **ESP32 continuously checks for person detection** using Grove Vision AI.
2. When a person is detected:
   - The **LED turns ON**.
   - An image is **captured and Base64 encoded**.
   - The **image is sent to Django** via HTTP POST request.
3. **Django backend saves the image** and updates the dashboard.
4. **Django Dashboard displays**:
   - Total detections.
   - Recent detected images.
   - Time-based detection statistics.

## API Endpoints
### Upload Image
**Endpoint:**
```
POST /upload_image/
```
**Request Body:**
```json
{
  "image": "<Base64 Encoded Image>"
}
```
**Response:**
```json
{
  "message": "Image uploaded successfully",
  "image_id": 1
}
```

### Get Image List
**Endpoint:**
```
GET /image_list/
```
**Response:**
```json
{
  "total_images": 10,
  "images": [
    {
      "id": 1,
      "image_url": "/media/uploaded_image.jpg",
      "uploaded_at": "2025-03-23 14:30:00"
    }
  ],
  "time_based_counts": {
    "6 AM - 12 PM": 3,
    "12 PM - 6 PM": 2,
    "6 PM - 12 AM": 4,
    "12 AM - 6 AM": 1
  }
}
```

## Dashboard Preview
The Django dashboard shows:
- **Recent Intrusions** with image previews.
- **Total intrusion count**.
- **Intrusion statistics based on time of the day**.

## Future Enhancements
- Implement **email alerts** when an intrusion is detected.
- Store images in **cloud storage** (AWS S3, Firebase, etc.).
- Add **real-time notifications** via WebSockets.

## Contributing
Feel free to contribute by opening a **pull request**.

## License
This project is open-source and available under the **MIT License**.

---
🚀 **Built by [Asif Khan](https://apycoder.com) | ApyCoder**

