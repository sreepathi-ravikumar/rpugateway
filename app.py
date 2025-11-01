
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
MAX_CONCURRENT_TTS = 15
MAX_CHUNK_LENGTH = 80
THREAD_POOL_SIZE = 8
AUDIO_FILE_RETENTION_HOURS = 1

# Pre-compiled regex patterns for performance
URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
TAG_PATTERN = re.compile(r'<[^>]+>')
BRACKET_PATTERN = re.compile(r'[\[\]{}()]')
SPECIAL_CHAR_PATTERN = re.compile(r'[^\w\s\u0B80-\u0BFF.,!?;:\-\'"।॥]')
WHITESPACE_PATTERN = re.compile(r'\s+')
SENTENCE_PATTERN = re.compile(r'[.!?]+')
SUB_PATTERN = re.compile(r'[,;]+')

# Tamil Unicode range for bilingual detection
TAMIL_RANGE = range(0x0B80, 0x0C00)

# Voice mappings for 30+ languages
VOICE_MAPPINGS = {
    'en': 'en-US-JennyNeural',
    'ta': 'ta-IN-PallaviNeural',
    'hi': 'hi-IN-SwaraNeural',
    'ml': 'ml-IN-SobhanaNeural',
    'kn': 'kn-IN-SapnaNeural',
    'te': 'te-IN-ShrutiNeural',
    'bn': 'bn-IN-TanishaaNeural',
    'mr': 'mr-IN-AarohiNeural',
    'gu': 'gu-IN-DhwaniNeural',
    'pa': 'pa-IN-SandeepNeural',
    'ur': 'ur-IN-GulNeural',
    'fr': 'fr-FR-DeniseNeural',
    'de': 'de-DE-KatjaNeural',
    'es': 'es-ES-ElviraNeural',
    'it': 'it-IT-ElsaNeural',
    'ru': 'ru-RU-SvetlanaNeural',
    'ja': 'ja-JP-NanamiNeural',
    'ko': 'ko-KR-SunHiNeural',
    'zh': 'zh-CN-XiaoxiaoNeural',
    'ar': 'ar-SA-ZariyahNeural',
    'pt': 'pt-BR-FranciscaNeural',
    'nl': 'nl-NL-ColetteNeural',
    'el': 'el-GR-AthinaNeural',
    'he': 'he-IL-HilaNeural',
    'tr': 'tr-TR-EmelNeural',
    'pl': 'pl-PL-ZofiaNeural',
    'th': 'th-TH-PremwadeeNeural',
    'vi': 'vi-VN-HoaiMyNeural',
    'sv': 'sv-SE-SofieNeural',
    'fi': 'fi-FI-NooraNeural',
    'cs': 'cs-CZ-VlastaNeural',
    'hu': 'hu-HU-NoemiNeural'
}

# Create audio output directory
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)


@lru_cache(maxsize=1024)
def clean_text(text: str) -> str:
    """
    Clean and normalize text for TTS processing.
    Cached for performance with repeated text.
    """
    # Remove URLs
    text = URL_PATTERN.sub('', text)
    
    # Remove HTML tags
    text = TAG_PATTERN.sub('', text)
    
    # Unescape HTML entities
    text = html.unescape(text)
    
    # Remove brackets
    text = BRACKET_PATTERN.sub('', text)
    
    # Normalize Unicode (NFKD)
    text = unicodedata.normalize('NFKD', text)
    
    # Remove special characters (keeping Tamil and basic punctuation)
    text = SPECIAL_CHAR_PATTERN.sub('', text)
    
    # Normalize whitespace
    text = WHITESPACE_PATTERN.sub(' ', text)
    
    return text.strip()


@lru_cache(maxsize=512)
def smart_chunk_text(text: str) -> Tuple[str, ...]:
    """
    Split text into manageable chunks at natural boundaries.
    Returns tuple for caching compatibility.
    """
    chunks = []
    
    # First, split by sentences
    sentences = SENTENCE_PATTERN.split(text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # If sentence is short enough, add it directly
        if len(sentence) <= MAX_CHUNK_LENGTH:
            chunks.append(sentence)
        else:
            # Split by commas/semicolons
            sub_parts = SUB_PATTERN.split(sentence)
            
            current_chunk = ""
            for part in sub_parts:
                part = part.strip()
                if not part:
                    continue
                    
                if len(current_chunk) + len(part) + 2 <= MAX_CHUNK_LENGTH:
                    current_chunk += (", " if current_chunk else "") + part
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    
                    # If single part is still too long, split by words
                    if len(part) > MAX_CHUNK_LENGTH:
                        words = part.split()
                        current_chunk = ""
                        for word in words:
                            if len(current_chunk) + len(word) + 1 <= MAX_CHUNK_LENGTH:
                                current_chunk += (" " if current_chunk else "") + word
                            else:
                                if current_chunk:
                                    chunks.append(current_chunk)
                                current_chunk = word
                    else:
                        current_chunk = part
            
            if current_chunk:
                chunks.append(current_chunk)
    
    return tuple(chunks)


def detect_tamil_content(text: str) -> bool:
    """Check if text contains Tamil Unicode characters."""
    return any(ord(char) in TAMIL_RANGE for char in text)


def get_voice_for_text(text: str, language: str = None, voice: str = None) -> str:
    """
    Determine the appropriate voice based on text content and parameters.
    Supports bilingual Tamil-English detection.
    """
    if voice:
        return voice
    
    # Auto-detect Tamil content
    if detect_tamil_content(text):
        return VOICE_MAPPINGS['ta']
    
    # Use specified language or default to English
    lang_code = language.lower() if language else 'en'
    return VOICE_MAPPINGS.get(lang_code, VOICE_MAPPINGS['en'])


async def generate_audio_chunk(text: str, voice: str, semaphore: asyncio.Semaphore) -> bytes:
    """
    Generate audio for a single text chunk using edge-tts.
    Rate-limited by semaphore.
    """
    async with semaphore:
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        return audio_data


async def generate_all_chunks(chunks: List[str], voice: str) -> List[bytes]:
    """
    Generate audio for all chunks concurrently with rate limiting.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TTS)
    
    tasks = [
        generate_audio_chunk(chunk, voice, semaphore)
        for chunk in chunks
    ]
    
    return await asyncio.gather(*tasks)


def process_audio_segment(audio_data: bytes) -> AudioSegment:
    """
    Process a single audio segment: normalize and strip silence.
    Designed for parallel execution.
    """
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
        temp_path = temp_file.name
        temp_file.write(audio_data)
    
    try:
        segment = AudioSegment.from_mp3(temp_path)
        
        # Normalize audio
        segment = normalize(segment)
        
        # Strip silence
        segment = segment.strip_silence(
            silence_thresh=-40,
            silence_len=50
        )
        
        return segment
    finally:
        os.unlink(temp_path)


def combine_audio_segments(audio_chunks: List[bytes]) -> str:
    """
    Process and combine all audio chunks into a single MP3 file.
    Uses parallel processing for audio segment handling.
    """
    print(f"Processing {len(audio_chunks)} audio chunks...")
    
    # Process segments in parallel
    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        segments = list(executor.map(process_audio_segment, audio_chunks))
    
    print(f"Processed {len(segments)} segments, combining...")
    
    # Add 200ms pause between segments
    pause = AudioSegment.silent(duration=200)
    
    combined = AudioSegment.empty()
    for i, segment in enumerate(segments):
        combined += segment
        if i < len(segments) - 1:  # Don't add pause after last segment
            combined += pause
    
    # Apply dynamic range compression
    combined = compress_dynamic_range(
        combined,
        threshold=-20.0,
        ratio=4.0,
        attack=5.0,
        release=50.0
    )
    
    # Export as MP3
    output_filename = f"{uuid.uuid4()}.mp3"
    output_path = os.path.join(AUDIO_OUTPUT_DIR, output_filename)
    
    combined.export(
        output_path,
        format='mp3',
        bitrate='192k',
        parameters=["-q:a", "0"]
    )
    
    print(f"Audio saved to {output_path}")
    
    # Get duration
    audio_info = MP3(output_path)
    duration = audio_info.info.length
    print(f"Audio duration: {duration:.2f} seconds")
    
    return output_path


def cleanup_old_files():
    """Remove audio files older than retention period."""
    cutoff_time = datetime.now() - timedelta(hours=AUDIO_FILE_RETENTION_HOURS)
    
    if not os.path.exists(AUDIO_OUTPUT_DIR):
        return
    
    removed_count = 0
    for filename in os.listdir(AUDIO_OUTPUT_DIR):
        filepath = os.path.join(AUDIO_OUTPUT_DIR, filename)
        
        if os.path.isfile(filepath):
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if file_time < cutoff_time:
                try:
                    os.unlink(filepath)
                    removed_count += 1
                except Exception as e:
                    print(f"Error removing {filepath}: {e}")
    
    if removed_count > 0:
        print(f"Cleaned up {removed_count} old audio files")


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with service information."""
    return jsonify({
        'status': 'online',
        'service': 'Multilingual TTS API',
        'version': '1.0.0',
        'supported_languages': list(VOICE_MAPPINGS.keys()),
        'endpoints': {
            'generate': '/generate-tts (POST)',
            'voices': '/voices (GET)',
            'health': '/health (GET)'
        }
    })


@app.route('/voices', methods=['GET'])
def get_voices():
    """Return all available voice mappings."""
    return jsonify({
        'voices': VOICE_MAPPINGS,
        'count': len(VOICE_MAPPINGS)
    })


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    audio_files = len([f for f in os.listdir(AUDIO_OUTPUT_DIR) if f.endswith('.mp3')])
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'audio_directory': AUDIO_OUTPUT_DIR,
        'cached_audio_files': audio_files
    })


@app.route('/generate-tts', methods=['POST'])
def generate_tts():
    """
    Generate TTS audio from text.
    
    Request JSON:
    {
        "text": "Text to convert to speech",
        "language": "en" (optional),
        "voice": "en-US-JennyNeural" (optional)
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({'error': 'Missing required field: text'}), 400
        
        text = data['text'].strip()
        if not text:
            return jsonify({'error': 'Text cannot be empty'}), 400
        
        language = data.get('language')
        voice = data.get('voice')
        
        print(f"Received TTS request - Length: {len(text)} chars")
        
        # Clean text
        cleaned_text = clean_text(text)
        print(f"Cleaned text - Length: {len(cleaned_text)} chars")
        
        # Determine voice
        selected_voice = get_voice_for_text(cleaned_text, language, voice)
        print(f"Selected voice: {selected_voice}")
        
        # Chunk text
        chunks = smart_chunk_text(cleaned_text)
        print(f"Split into {len(chunks)} chunks")
        
        # Generate audio chunks concurrently
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            audio_chunks = loop.run_until_complete(
                generate_all_chunks(list(chunks), selected_voice)
            )
        finally:
            loop.close()
        
        print(f"Generated {len(audio_chunks)} audio chunks")
        
        # Combine audio segments
        output_path = combine_audio_segments(audio_chunks)
        
        # Send file
        return send_file(
            output_path,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=f'tts_{uuid.uuid4().hex[:8]}.mp3'
        )
        
    except Exception as e:
        print(f"Error generating TTS: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Audio generation failed: {str(e)}'}), 500


if __name__ == '__main__':
    print("Starting Multilingual TTS API...")
    print(f"Audio output directory: {AUDIO_OUTPUT_DIR}")
    print(f"Supported languages: {len(VOICE_MAPPINGS)}")
    
    # Cleanup old files on startup
    cleanup_old_files()
    
    # Run Flask app
    port = int(os.environ.get('PORT', 7860))
    app.run(host='0.0.0.0', port=port, debug=False)
    
