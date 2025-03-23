#include <WiFi.h>
#include <HTTPClient.h>
#include <mbedtls/base64.h>
#include <Base64.h>  // Include the Base64 library for encoding/decoding
#include <Seeed_Arduino_SSCMA.h>

#define DECODED_IMAGE_MAX_SIZE (15 * 1024) // Maximum size of the decoded image
#define LED_PIN 10  // Define the LED pin (D10)

const char* ssid = "ApyCoder";  // Replace with your WiFi SSID
const char* password = "Asif12345";  // Replace with your WiFi password
const String apiUrl = "http://your-system-ip:8000/upload_image/";  // Django API URL

static unsigned char jpegImage[DECODED_IMAGE_MAX_SIZE + 1];

SSCMA AI;

// Function to decode the Base64 image data
size_t decode_base64_image(const unsigned char* p_data, unsigned char* decoded_str) {
  if (!p_data || !decoded_str) return 0;

  size_t str_len = strlen((const char*) p_data);
  size_t output_len = 0;

  // Decode the Base64 image
  int decode_ret = mbedtls_base64_decode(NULL, 0, &output_len, p_data, str_len);
  if (decode_ret == MBEDTLS_ERR_BASE64_INVALID_CHARACTER) {
    Serial.println("Invalid character in Base64 string");
    return 0;
  }

  if (output_len == 0 || output_len > DECODED_IMAGE_MAX_SIZE) {
    Serial.println("Base64 decode output size is too large or zero.");
    return 0;
  }

  decode_ret = mbedtls_base64_decode(decoded_str, DECODED_IMAGE_MAX_SIZE, &output_len, p_data, str_len);
  if (decode_ret != 0) {
    Serial.printf("Failed to decode Base64 string, error: %d\n", decode_ret);
    return 0;
  }

  return output_len;
}

// Function to send the decoded Base64 image to Django backend
void send_image_to_django(const unsigned char* image, size_t size) {
  HTTPClient http;

  // Encode the image to Base64
  String base64Image = base64::encode(image, size);  // Use Base64 library's encode function

  // Prepare the JSON payload
  String payload = "{\"image\": \"" + base64Image + "\"}";

  http.begin(apiUrl);  // Specify the URL
  http.addHeader("Content-Type", "application/json");  // Specify content type

  // Send the POST request
  int httpResponseCode = http.POST(payload);

  // Check the response code
  if (httpResponseCode > 0) {
    Serial.print("HTTP Response code: ");
    Serial.println(httpResponseCode);
  } else {
    Serial.print("Error sending POST request: ");
    Serial.println(httpResponseCode);
  }

  http.end();  // Close the HTTP connection
}

// Function to display the decoded image (modify based on your display logic)
void display_jpeg_image(const unsigned char* image, size_t size) {
  Serial.println("Displaying decoded JPEG image...");
  Serial.printf("Image size: %d bytes\n", size);
  // Add your display logic here (OLED/TFT, etc.)
}

void setup() {
  AI.begin();
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);  // Set LED pin as output
  digitalWrite(LED_PIN, LOW); // Ensure LED is off at start
  
  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("Connected to WiFi");
}

void loop() {
  if (!AI.invoke(1, false, true)) {
    Serial.println("invoke success");
    
    bool personDetected = false;  // Variable to track person detection

    // Check detected classes for person detection
    for (int i = 0; i < AI.classes().size(); i++) {
      int target = AI.classes()[i].target;
      int score = AI.classes()[i].score;

      Serial.print("Class[");
      Serial.print(i);
      Serial.print("] target=");
      Serial.print(target);
      Serial.print(", score=");
      Serial.println(score);

      // If person detected (target = 1 and score >= 70), set flag
      if (target == 1 && score >= 70) {
        Serial.println("Person detected!");
        personDetected = true;
      }
    }

    // Control LED based on person detection
    if (personDetected) {
      digitalWrite(LED_PIN, HIGH);  // Turn LED on

      // Check if the last image is available
      if (AI.last_image().length() > 0) {
        Serial.print("Last image: ");
        Serial.println(AI.last_image());

        // Decode the Base64 image and display it
        size_t jpegImageSize = decode_base64_image((const unsigned char*) AI.last_image().c_str(), jpegImage);
        if (jpegImageSize > 0) {
          // Call the display function after decoding the image
          display_jpeg_image(jpegImage, jpegImageSize);
          
          // Send the image to Django server
          send_image_to_django(jpegImage, jpegImageSize);
        }
      }
    } else {
      digitalWrite(LED_PIN, LOW);  // Turn LED off if no person detected
    }
  }
}
