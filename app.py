from flask import Flask, request, jsonify, send_file
from gtts import gTTS
import io
import os
import tempfile
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/')
def home():
    return jsonify({
        "message": "Text to Speech API is running!",
        "usage": "Send a POST request to /speak with JSON containing 'text' field",
        "endpoints": {
            "/speak": "Convert text to speech (returns audio file)",
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
    """New endpoint that converts text to speech"""
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Please provide 'text' in JSON body"}), 400
        
        text = data['text']
        
        # Validate text length
        if len(text.strip()) == 0:
            return jsonify({"error": "Text cannot be empty"}), 400
        
        if len(text) > 1000:
            return jsonify({"error": "Text too long. Maximum 1000 characters."}), 400
        
        # Create gTTS object
        tts = gTTS(text=text, lang='en', slow=False)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tts.save(tmp_file.name)
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

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
