from flask import Flask, request, jsonify, send_file
import asyncio
import tempfile
import subprocess
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/speak', methods=['POST'])
def text_to_speech_subprocess():
    """Alternative using edge-tts CLI command"""
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Please provide 'text' in JSON body"}), 400
        
        text = data['text']
        voice = data.get('voice', 'en-US-AriaNeural')
        
        if len(text.strip()) == 0:
            return jsonify({"error": "Text cannot be empty"}), 400
        
        # Create temporary file for output
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            output_file = tmp_file.name
        
        # Use edge-tts command line
        cmd = [
            'edge-tts',
            '--text', text,
            '--voice', voice,
            '--write-media', output_file
        ]
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise Exception(f"edge-tts failed: {result.stderr}")
        
        # Check if file was created
        if not os.path.exists(output_file):
            raise Exception("Output file was not created")
        
        return send_file(
            output_file,
            as_attachment=True,
            download_name='speech.mp3',
            mimetype='audio/mpeg'
        )
        
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Speech generation timeout"}), 500
    except Exception as e:
        return jsonify({"error": f"Speech generation failed: {str(e)}"}), 500
