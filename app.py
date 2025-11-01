from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import edge_tts
import asyncio
import os
import tempfile
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Create temp directory for audio files
TEMP_DIR = tempfile.gettempdir()

# Available voices (some popular English voices)
VOICES = {
    "male_us": "en-US-GuyNeural",
    "female_us": "en-US-JennyNeural",
    "male_uk": "en-GB-RyanNeural",
    "female_uk": "en-GB-SoniaNeural",
    "male_au": "en-AU-WilliamNeural",
    "female_au": "en-AU-NatashaNeural",
}

async def generate_speech(text, voice, rate, pitch):
    """Generate speech using edge-tts"""
    filename = f"{uuid.uuid4()}.mp3"
    filepath = os.path.join(TEMP_DIR, filename)
    
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch
    )
    
    await communicate.save(filepath)
    return filepath

@app.route('/')
def home():
    return jsonify({
        "message": "Edge-TTS API",
        "endpoints": {
            "/synthesize": "POST - Convert text to speech",
            "/voices": "GET - List available voices"
        }
    })

@app.route('/voices', methods=['GET'])
def get_voices():
    """Return available voices"""
    return jsonify(VOICES)

@app.route('/synthesize', methods=['POST'])
def synthesize():
    """Convert text to speech"""
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "No text provided"}), 400
        
        text = data['text']
        voice_key = data.get('voice', 'female_us')
        rate = data.get('rate', '+0%')
        pitch = data.get('pitch', '+0Hz')
        
        # Get voice from key
        voice = VOICES.get(voice_key, VOICES['female_us'])
        
        # Generate speech
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        filepath = loop.run_until_complete(generate_speech(text, voice, rate, pitch))
        loop.close()
        
        # Send file and delete after
        response = send_file(
            filepath,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=f'speech_{datetime.now().strftime("%Y%m%d_%H%M%S")}.mp3'
        )
        
        # Schedule file deletion after sending
        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                print(f"Error deleting file: {e}")
        
        return response
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
