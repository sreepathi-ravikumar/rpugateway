from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend-backend connection

prompt=None

@app.route('/api/submit', methods=['POST'])
def receive_input():
    global prompt
    data = request.get_json()
    user_input = data.get('input', '')
    prompt=user_input

@app.route('/api/get-string', methods=['GET'])
def get_string():
    global prompt
    return jsonify({"data": prompt})

@app.route('/api/receive', methods=['POST'])
def receive():
    data = request.get_json()
    final_string = data.get("final")
    print("Received from frontend:", final_string)
    return jsonify({"message": f"Python received final string: {final_string}"})


if __name__ == '__main__':
    # For local testing, use port 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)








