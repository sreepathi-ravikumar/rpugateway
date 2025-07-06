from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend-backend connection

@app.route('/api/submit', methods=['POST'])
def receive_input():
    data = request.get_json()
    user_input = data.get('input', '')
    print(f"Received input: {user_input}")

    return jsonify({"message": f"Backend received: {user_input}"})


if __name__ == '__main__':
    # For local testing, use port 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
