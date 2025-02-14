
from flask import Flask, request, jsonify
import requests
import time
from typing import List, Dict
import logging
import os
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TokenManager:
    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.current_index = 0
        self.rate_limits: Dict[str, float] = {key: 0 for key in api_keys}

    def get_next_available_token(self) -> str:
        start_index = self.current_index
        
        while True:
            current_key = self.api_keys[self.current_index]
            
            # Check if enough time has passed since the last rate limit
            if time.time() - self.rate_limits[current_key] > 60:  # 1 minute cooldown
                return current_key
            
            # Move to next token
            self.current_index = (self.current_index + 1) % len(self.api_keys)
            
            # If we've checked all tokens and none are available
            if self.current_index == start_index:
                # Reset the oldest rate limit
                oldest_key = min(self.rate_limits.items(), key=lambda x: x[1])[0]
                self.rate_limits[oldest_key] = 0
                return oldest_key

    def mark_rate_limited(self, token: str):
        self.rate_limits[token] = time.time()
        self.current_index = (self.current_index + 1) % len(self.api_keys)

# Initialize with your API keys
API_KEYS = os.environ.get("OPENAI_API_KEYS")
token_manager = TokenManager(API_KEYS)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

@app.route('/chat/', methods=['POST'])
def chat():
    try:
        request_data = request.get_json()
        
        while True:
            current_token = token_manager.get_next_available_token()
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {current_token}"
            }
            
            try:
                response = requests.post(
                    OPENAI_API_URL,
                    headers=headers,
                    json=request_data
                )
                
                if response.status_code == 429:  # Rate limit error
                    logger.info(f"Rate limit hit for token {current_token}")
                    token_manager.mark_rate_limited(current_token)
                    continue
                
                response.raise_for_status()
                return jsonify(response.json()), response.status_code
                
            except requests.exceptions.RequestException as e:
                if "rate_limit" in str(e).lower():
                    logger.info(f"Rate limit hit for token {current_token}")
                    token_manager.mark_rate_limited(current_token)
                    continue
                    
                logger.error(f"Error making request: {str(e)}")
                return jsonify({
                    "error": str(e),
                    "error_code": response.status_code if 'response' in locals() else 500
                }), 500

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "error_code": 500
        }), 500

if __name__ == '__main__':
    # Option 1: Run without SSL (for local development)
    app.run(host='0.0.0.0', port=5000)
    
    # Option 2: Run with SSL (uncomment and install required packages first)
    # To use SSL, first run: pip install cryptography pyOpenSSL
    # app.run(ssl_context='adhoc', host='0.0.0.0', port=5000)