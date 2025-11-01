from flask import Flask, request, jsonify, send_file
import edge_tts
import asyncio
import io
import os
import tempfile
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/')
def home():
    return jsonify({
        "message": "Text to Speech API with Edge TTS is running!",
        "usage": "Send a POST request to /speak with JSON containing 'text' field",
        "endpoints": {
            "/speak": "Convert text to speech using Edge TTS (returns audio file)",
            "/process": "Original text processing endpoint"
        }
    })

@app.route('/process', methods=['POST'])
def process_text():
    """Original endpoint that returns 'good' as text"""
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Please provide 'text' in JSON body"}), 400
        
        text = data['text']
        
        response = {
            "input_text": text,
            "output": "good",
            "status": "success"
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/speak', methods=['POST'])
def text_to_speech():
    """New endpoint that converts text to speech using Edge TTS"""
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Please provide 'text' in JSON body"}), 400
        
        text = data['text']
        
        # Validate text length
        if len(text.strip()) == 0:
            return jsonify({"error": "Text cannot be empty"}), 400
        
        if len(text) > 3000:
            return jsonify({"error": "Text too long. Maximum 3000 characters."}), 400
        
        # Run the async function
        audio_data = asyncio.run(generate_speech(text))
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tmp_file.write(audio_data)
            temp_filename = tmp_file.name
        
        # Return the audio file
        return send_file(
            temp_filename,
            as_attachment=True,
            download_name='speech.mp3',
            mimetype='audio/mpeg'
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def generate_speech(text, voice="en-US-AriaNeural"):
    """
    Generate speech using Edge TTS
    Available voices: en-US-AriaNeural, en-US-JennyNeural, en-GB-SoniaNeural, etc.
    """
    try:
        communicate = edge_tts.Communicate(text, voice)
        
        # Collect audio data
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        
        # Combine all audio chunks
        return b''.join(audio_chunks)
        
    except Exception as e:
        raise Exception(f"Edge TTS error: {str(e)}")

@app.route('/voices', methods=['GET'])
def get_voices():
    """Get available Edge TTS voices"""
    try:
        # This would typically require an async function
        # For simplicity, returning some common voices
        common_voices = [
            "en-US-AriaNeural",
            "en-US-JennyNeural", 
            "en-US-GuyNeural",
            "en-GB-SoniaNeural",
            "en-GB-RyanNeural",
            "en-AU-NatashaNeural",
            "en-AU-WilliamNeural"
        ]
        return jsonify({"voices": common_voices})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
