
import os
import sys
from dotenv import load_dotenv

# Ensure the backend app directory is in the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

from app.utils.llm_client import LLMClient
from app.config import Config

def test_groq_country_boosting():
    print("Testing Groq Country Boosting Strategy...")
    
    # We use LLMClient which we just updated
    client = LLMClient(
        api_key=os.getenv("GROQ_API_KEY"), 
        base_url="https://api.groq.com/openai/v1",
        model="groq/compound"
    )
    
    messages = [
        {"role": "user", "content": "What is the latest status of the US-Iran diplomatic relations regarding the JCPOA in 2026? Give me specific details that would only appear in regional or specialized news."}
    ]
    
    # Strategy: Include 'Iran' boosting (Tavily format: Full Name)
    search_settings = {
        "country": "Iran",
        "exclude_domains": ["wikipedia.org", "*.social"]
    }
    
    print(f"Sending request with search_settings: {search_settings}")
    
    try:
        response = client.chat(
            messages=messages,
            search_settings=search_settings,
            max_tokens=2048
        )
        print("\n--- Response ---")
        print(response)
        print("----------------\n")
        
        if "<execute_tool>" in response:
            print("SUCCESS: Native tool call detected.")
            if '"country": "Iran"' in response or 'iran' in response.lower():
                print("SUCCESS: Search output mentions 'Iran' context.")
        else:
            print("WARNING: No native tool call in response. Groq might have answered from internal knowledge.")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_groq_country_boosting()
