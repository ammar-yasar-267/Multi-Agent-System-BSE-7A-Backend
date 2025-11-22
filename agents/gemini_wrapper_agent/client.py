import os
import logging
import google.generativeai as genai
import yaml
from dotenv import load_dotenv

load_dotenv()

with open("config/settings.yaml", "r") as f:
    config = yaml.safe_load(f)

_logger = logging.getLogger(__name__)

GEMINI_CONFIG = config['gemini_wrapper']
API_KEY = os.getenv("GEMINI_API_KEY")

MODE = GEMINI_CONFIG.get("mode", "auto")

def get_mode():
    if MODE == "cloud":
        return "cloud"
    if MODE == "mock":
        return "mock"
    # Auto mode
    if API_KEY:
        _logger.info("GEMINI_API_KEY found, running in 'cloud' mode.")
        genai.configure(api_key=API_KEY)
        return "cloud"
    _logger.warning("GEMINI_API_KEY not set, falling back to 'mock' mode.")
    return "mock"

async def call_gemini_or_mock(input_text: str, model_override: str = None) -> dict:
    mode = get_mode()
    if mode == "mock":
        return {
            "output": f"This is a mock response for the query: '{input_text}'. The mock response triggered because the Gemini API key is not configured.",
            "mock": True
        }

    # Cloud mode using the official package
    try:
        model_name = model_override or 'gemini-2.5-flash'
        model = genai.GenerativeModel(model_name)
        
        response = await model.generate_content_async(input_text)
        
        return {"output": response.text, "mock": False}
    
    except Exception as e:
        _logger.error(f"Error calling Google GenAI: {e}")
        return {"error": f"Google GenAI API request failed: {str(e)}"}
