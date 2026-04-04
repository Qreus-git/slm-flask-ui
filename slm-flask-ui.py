from flask import Flask, request, render_template_string
from PIL import Image
import io
import base64
import requests
import json
import markdown

app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            background-color: #0a0a0a;
            color: white;
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
        }

        .chat-container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            height: 90vh;
            display: flex;
            flex-direction: column;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding-right: 10px;
        }

        .user-msg {
            background-color: #1b2b2b;
            border-left: 4px solid #4deeea; /* soft electric aqua */
            padding: 10px 15px;
            margin: 10px 0;
            border-radius: 6px;
            text-align: right;
            white-space: pre-wrap;
        }

        .ai-msg {
            background-color: #111;
            border-left: 4px solid #888;
            padding: 10px 15px;
            margin: 10px 0;
            border-radius: 6px;
            white-space: pre-wrap;
        }

        .input-area {
            display: flex;
            gap: 10px;
        }

        textarea {
            flex: 1;
            padding: 10px;
            background-color: #111;
            border: 1px solid #333;
            color: white;
            border-radius: 4px;
            resize: none;
            height: auto;
            min-height: 40px;
            max-height: 200px;
            overflow-y: auto;
        }

        button {
            padding: 10px 20px;
            background-color: #4deeea;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            color: black;
            font-weight: bold;
        }

        .image-preview img {
            max-width: 150px;
            border-radius: 6px;
            margin-bottom: 10px;
        }
    </style>
</head>

<body>
    <div class="chat-container">
        <div class="messages">
            {% for msg in messages %}
                {% if msg.role == 'user' %}
                    <div class="user-msg">{{ msg.text }}</div>
                {% else %}
                    <div class="ai-msg">{{ msg.text|safe }}</div>
                {% endif %}
            {% endfor %}
        </div>

        <form class="input-area" action="/chat" method="post" enctype="multipart/form-data">
            <div class="image-preview" style="display:none;"></div>
            <input type="file" name="image" id="hidden-image" style="display:none;">
            <textarea name="message" placeholder="Type your message..." rows="1"></textarea>
            <button type="submit">Send</button>
        </form>
    </div>

    <script>
        const messagesDiv = document.querySelector('.messages');
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    </script>

    <script>
        const textarea = document.querySelector('textarea');
        const form = document.querySelector('.input-area');

        textarea.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                form.submit();
            }
        });
    </script>

    <script>
        const preview = document.querySelector('.image-preview');

        document.addEventListener('paste', function(e) {
            const items = e.clipboardData.items;

            for (let item of items) {
                if (item.type.startsWith('image/')) {
                    const file = item.getAsFile();
                    const reader = new FileReader();

                    reader.onload = function(event) {
                        preview.style.display = "block";
                        preview.innerHTML = `<img src="${event.target.result}">`;
                    };
                    reader.readAsDataURL(file);

                    const hiddenInput = document.getElementById('hidden-image');
                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    hiddenInput.files = dataTransfer.files;

                    console.log("Image pasted:", file);
                }
            }
        });
    </script>
</body>
</html>
"""

messages = []


@app.route("/")
def home():
    return render_template_string(HTML_PAGE, messages=messages)


@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.form.get("message", "").strip()
    uploaded_image = request.files.get("image")

    # If no text and no image, just re-render
    if not user_msg and not uploaded_image:
        return render_template_string(HTML_PAGE, messages=messages)

    # Show what the user sent (text only; image is implicit)
    display_text = user_msg if user_msg else "[Image only]"
    messages.append({"role": "user", "text": display_text})

    payload = None
    ai_reply = ""

    # If an image is present → use BakLLaVA (non-streaming)
    if uploaded_image:
        image_bytes = uploaded_image.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        print("BASE64 (first 50):", image_b64[:50] + "...")
        print("Image size:", len(image_bytes))
        print("Received image:", uploaded_image.filename)

        prompt = user_msg if user_msg else "Describe this image and help me understand any issues you see."

        payload = {
            "model": "bakllava",
            "prompt": prompt,
            "images": [image_b64],
            "stream": False
        }

        response = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
        )

        data = response.json()
        print("DEBUG BakLLaVA JSON:", data)
        ai_reply = data.get("response", "")

    # If no image → use Dolphin-Mistral (streaming)
    else:
        payload = {
            "model": "dolphin-mistral",
            "prompt": user_msg
        }

        response = requests.post(
            "http://localhost:11434/api/generate",
            json=payload,
            stream=True,
        )

        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode("utf-8"))
                    ai_reply += data.get("response", "")
                except json.JSONDecodeError:
                    pass

    # Markdown → HTML
    ai_reply = markdown.markdown(ai_reply)

    messages.append({"role": "ai", "text": ai_reply})

    return render_template_string(HTML_PAGE, messages=messages)


@app.route("/upload", methods=["POST"])
def upload():
    uploaded_file = request.files.get("file")

    if not uploaded_file:
        return "No file uploaded."

    file_bytes = uploaded_file.read()

    try:
        image = Image.open(io.BytesIO(file_bytes))
        import pytesseract
        extracted_text = pytesseract.image_to_string(image)

        return f"""
        <h3>Image received!</h3>
        <h4>Extracted text:</h4>
        <pre>{extracted_text}</pre>
        """
    except Exception:
        pass

    try:
        text = file_bytes.decode("utf-8", errors="ignore")
        return f"<h3>Text file received!</h3><pre>{text}</pre>"
    except Exception:
        return "File uploaded, but could not be processed as text or image."


if __name__ == "__main__":
    app.run(debug=True)
