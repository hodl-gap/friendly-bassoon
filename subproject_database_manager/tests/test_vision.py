import sys
import base64
sys.path.append('../')
from models import call_claude_sonnet

def encode_image(image_path):
    """Encode image to base64"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

# Read the image
image_path = 'test_data/ChatExport_2025-11-21/photos/photo_583@18-11-2025_14-45-51.jpg'
image_data = encode_image(image_path)

# Create message with image
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_data
                }
            },
            {
                "type": "text",
                "text": "Please analyze this chart and answer: i) What does the chart explain? ii) What is the source of the chart? iii) Who made the chart?"
            }
        ]
    }
]

# Call Claude
response = call_claude_sonnet(messages)

print("=== FULL RAW LLM RESPONSE ===")
print(response)
