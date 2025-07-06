from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(_name_)
CORS(app)  # Enable CORS for frontend-backend connection

prompt = None  # Global variable

@app.route('/api/submit', methods=['POST'])
def receive_input():
    global prompt
    data = request.get_json()
    user_input = data.get('input', '')
    prompt = user_input
    return jsonify({"message": "Prompt saved successfully"})  # ✅ must return something

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

if _name_ == '_main_':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
