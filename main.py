from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import logging
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
import requests
from google import genai
from google.genai import types
import os
import logging
from io import BytesIO



load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("gemini_api_key not found in environment variables")
client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI( title = "Lyricyfy-music with AI")
logging.basicConfig(level = logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok = True)

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Audio → Text & Image with Gemini</title>
  <style>
    body { font-family: sans-serif; max-width: 600px; margin: auto; padding: 1em; }
    input, button, textarea { width: 100%; margin-top: .5em; }
    img { max-width: 100%; margin-top: 1em; }
  </style>
</head>
<body>
  <h1>Gemini Audio ⟶ Text & Image</h1>
  <form id="uploadForm">
    <label>Choose MP3 file:</label>
    <input type="file" id="audioFile" accept=".mp3" required />
    <button type="submit">Transcribe & Summarize</button>
  </form>
  <div id="textResult">
    <h2>Transcription & Summary</h2>
    <textarea id="summary" rows="4" readonly></textarea>
  </div>
  <form id="imageForm">
    <label>Or enter text to visualize:</label>
    <textarea id="lyrics" rows="3" placeholder="Paste summary or any text..."></textarea>
    <button type="submit">Generate Image</button>
  </form>
  <div id="imgResult">
    <h2>Generated Image</h2>
    <img id="genImage" src="" alt="Your generated image will appear here." />
  </div>

  <script>
    const uploadForm = document.getElementById('uploadForm');
    const imageForm = document.getElementById('imageForm');

    uploadForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fileInput = document.getElementById('audioFile');
      const file = fileInput.files[0];
      if (!file) return alert("Select an MP3 file");

      const form = new FormData();
      form.append("file", file);

      const res = await fetch('/uploadfile/', { method: 'POST', body: form });
      if (!res.ok) return alert("Upload failed");
      const data = await res.json();
      document.getElementById('summary').textContent = data.result;
      document.getElementById('lyrics').value = data.result;
    });

    imageForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = document.getElementById('lyrics').value.trim();
      if (!text) return alert("Enter some text");

      const res = await fetch('/generate_image/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lyrics: text })
      });
      if (!res.ok) return alert("Image generation failed");
      const { image_path } = await res.json();
      document.getElementById('genImage').src = image_path;
    });
  </script>
</body>
</html>
"""

@app.get("/", response_class= HTMLResponse)
async def homepage():
    return INDEX_HTML


@app.post("/uploadfile/")
async def upload_and_transcribe(file: UploadFile = File(...)):

    content = await file.read()
    if file.content_type != "audio/mpeg":
        raise HTTPException(400,"Invalid file type. Please upload an MP3 file.")

    contents = [
        types.Content(parts=[
            types.Part(text = "Transcribe the audio and summarize it in a few sentences."),
            types.Part(inline_data = types.Blob(
                mime_type = "audio/mpeg",
                data = content
            ))
        ])
    ]  

    try :
        resp = client.models.generate_content(
            model = "models/gemini-1.5-pro",
            contents = contents,
            config = types.GenerateContentConfig(response_mime_type = "text/plain")
        )
        summary = resp.text.strip()
        return {"result": summary}

    except Exception as e:

        logging.error("Gemini transcription error:", exc_info = e)
        raise HTTPException(500, "Gemini transcription error")
    

@app.post("/generate_image/")
async def generate_image(lyrics: dict = Form(None), payload: dict = None):
    text = (payload or lyrics).get("lyrics") if isinstance(payload or lyrics) else None
    if not text:
        raise HTTPException(400, "No text provided for image generation.")
    
    prompt = f"Create an image based on the following text: {text}"
    contents = [types.Content(parts=[types.part(text = prompt)])]

    try:
        resp = client.models.generate_content(
            model = "models/gemini-2.0-flash-preview-image-generation",
            contents = contents,
            config = types.GenerateContentConfig(response_modalities = ["IMAGE"])
        )

        Blob = resp.parts[0].inline_data
        image_bytes = Blob.data

        path = os.path.join(MEDIA_DIR,"generated_image.png")
        with open(path,"wb") as f:
            f.write(image_bytes)

        return {"image_path": path}
    
    except Exception as e:
        logging.error("Gemini image generation error:", exc_info = e)
        raise HTTPException(500, "Gemini image generation error")
    
@app.get("/media/{filename}")
async def media(filename: str):

    file_path = os.path.join(MEDIA_DIR,filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404,"file not found")
    return FileResponse(file_path)