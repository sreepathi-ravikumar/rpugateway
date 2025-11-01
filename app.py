from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/')
def home():
    return jsonify({
        "message": "Text processing API is running!",
        "usage": "Send a POST request to /process with JSON containing 'text' field"
    })

@app.route('/process', methods=['POST'])
def process_text():
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Please provide 'text' in JSON body"}), 400
        
        text = data['text']
        
        # Always return "good" as the output
        response = {
            "input_text": text,
            "output": "good",
            "status": "success"
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
