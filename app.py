from flask import Flask, request, send_file
from flask_cors import CORS
import edge_tts
import asyncio
import uuid

app = Flask(__name__)
CORS(app)

@app.route('/tts', methods=['POST'])
def tts():
    text = request.json.get('text', '').strip()
    if not text:
        return {'error': 'No text'}, 400
    
    filename = f"{uuid.uuid4()}.mp3"
    asyncio.run(edge_tts.Communicate(text, 'en-US-JennyNeural').save(filename))
    return send_file(filename, mimetype='audio/mpeg')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)
