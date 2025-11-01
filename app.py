import os
import re
import html
import uuid
import asyncio
import tempfile
import unicodedata
from datetime import datetime, timedelta
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import edge_tts
from pydub import AudioSegment
from pydub.effects import normalize, compress_dynamic_range
from mutagen.mp3 import MP3

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
AUDIO_OUTPUT_DIR = 'audio_output'
MAX_CONCURRENT_TTS = 10
MAX_CHUNK_LENGTH = 80
THREAD_POOL_SIZE = 8
AUDIO_FILE_RETENTION_HOURS = 2

# Create output directory
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

# Voice mappings (only common voices to keep lightweight)
VOICE_MAPPINGS = {
    'en': 'en-US-JennyNeural',
    'ta': 'ta-IN-PallaviNeural',
    'hi': 'hi-IN-SwaraNeural',
    'fr': 'fr-FR-DeniseNeural',
    'de': 'de-DE-KatjaNeural',
    'es': 'es-ES-ElviraNeural',
    'ja': 'ja-JP-NanamiNeural',
    'zh': 'zh-CN-XiaoxiaoNeural'
}

# Tamil range detection
TAMIL_RANGE = range(0x0B80, 0x0C00)

def detect_tamil_content(text: str) -> bool:
    return any(ord(c) in TAMIL_RANGE for c in text)

def get_voice_for_text(text: str, language: str = None):
    if detect_tamil_content(text):
        return VOICE_MAPPINGS['ta']
    lang_code = (language or 'en').lower()
    return VOICE_MAPPINGS.get(lang_code, VOICE_MAPPINGS['en'])

@lru_cache(maxsize=256)
def clean_text(text: str) -> str:
    text = re.sub(r"http\S+", "", text)
    text = html.unescape(text)
    text = re.sub(r"[^A-Za-z0-9\u0B80-\u0BFF\s.,!?;:'-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def smart_chunk_text(text: str) -> List[str]:
    words = text.split()
    chunks = []
    chunk = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 <= MAX_CHUNK_LENGTH:
            chunk.append(word)
            current_len += len(word) + 1
        else:
            chunks.append(" ".join(chunk))
            chunk = [word]
            current_len = len(word)
    if chunk:
        chunks.append(" ".join(chunk))
    return chunks

async def generate_audio_chunk(text, voice):
    communicate = edge_tts.Communicate(text, voice)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

async def generate_all_chunks(chunks, voice):
    tasks = [generate_audio_chunk(c, voice) for c in chunks]
    return await asyncio.gather(*tasks)

def process_audio_segment(audio_data: bytes) -> AudioSegment:
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp:
        temp.write(audio_data)
        temp_path = temp.name
    segment = AudioSegment.from_mp3(temp_path)
    segment = normalize(segment)
    os.unlink(temp_path)
    return segment

def combine_audio_segments(audio_chunks: List[bytes]) -> str:
    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        segments = list(executor.map(process_audio_segment, audio_chunks))
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=200)
    for i, seg in enumerate(segments):
        combined += seg
        if i < len(segments) - 1:
            combined += pause
    combined = compress_dynamic_range(combined)
    filename = f"{uuid.uuid4()}.mp3"
    path = os.path.join(AUDIO_OUTPUT_DIR, filename)
    combined.export(path, format='mp3', bitrate='192k')
    return path

@app.route('/')
def home():
    return jsonify({
        "service": "Edge TTS Backend",
        "status": "running",
        "languages": list(VOICE_MAPPINGS.keys())
    })

@app.route('/generate-tts', methods=['POST'])
def generate_tts():
    try:
        data = request.get_json()
        text = data.get("text", "").strip()
        language = data.get("language", "en")

        if not text:
            return jsonify({"error": "Empty text"}), 400

        cleaned = clean_text(text)
        chunks = smart_chunk_text(cleaned)
        voice = get_voice_for_text(cleaned, language)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_chunks = loop.run_until_complete(generate_all_chunks(chunks, voice))
        loop.close()

        output_path = combine_audio_segments(audio_chunks)
        return send_file(output_path, mimetype='audio/mpeg', as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 7860))
    app.run(host='0.0.0.0', port=port)
