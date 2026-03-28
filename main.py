from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
from urllib.parse import urlparse
import os
from dotenv import load_dotenv
import pandas as pd
import httpx
import google.generativeai as genai

# 1. Load the variables from the .env file
load_dotenv()

# 2. Securely fetch the secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# 3. Configure your AI with the hidden key
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # This is the line Pylance was looking for:
    model = genai.GenerativeModel('gemini-2.5-flash') 
else:
    model = None
    print("WARNING: Gemini API Key not found in .env!")

app = FastAPI()

# A global variable to track scraping status
scraping_status = {"status": "idle", "products_scraped": 0}

@app.get("/check-env")
async def check_env():
    """A quick test to make sure your .env is loading properly."""
    if DATABASE_URL:
        return {"message": "Database URL loaded successfully!"}
    return {"error": "Failed to load environment variables."}

async def fetch_shopify_products(pasted_url: str):
    """Takes ANY url, extracts the base domain, and safely checks for Shopify products."""
    
    # 1. The Smart Cleaner: Extract just the base website (e.g., "https://store.com")
    try:
        parsed_uri = urlparse(pasted_url)
        # If the user just typed "store.com" without https://, fix it
        if not parsed_uri.scheme:
            pasted_url = "https://" + pasted_url
            parsed_uri = urlparse(pasted_url)
            
        base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
    except Exception:
        print("⚠️ Invalid URL format provided.")
        return []

    # 2. Build the correct Shopify link
    json_url = f"{base_url}/products.json?limit=50"
    
    # 3. Disguise the bot as a real web browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"🔍 Attempting to scrape: {json_url}")
            response = await client.get(json_url, headers=headers, follow_redirects=True)
            
            if response.status_code == 200:
                data = response.json()
                # Double-check that this is actually a Shopify JSON response
                if 'products' in data:
                    print(f"✅ Success! Found {len(data['products'])} products.")
                    return data['products']
                else:
                    print(f"⚠️ {base_url} returned JSON, but it doesn't look like Shopify data.")
                    return []
            else:
                print(f"⚠️ {base_url} returned status {response.status_code}. Might not be a Shopify store.")
                return []
                
        # Catch the exact error you got before, plus any connection errors
        except ValueError:
            print(f"❌ Error: {base_url} returned HTML, not JSON. It is likely NOT a Shopify store, or it has bot-protection.")
            return []
        except Exception as e:
            print(f"❌ Connection error with {base_url}: {e}")
            return []

def enhance_with_ai(product_title: str):
    """Uses AI to categorize the product based on its title."""
    try:
        if model:
            prompt = f"Categorize this product in one word: {product_title}"
            response = model.generate_content(prompt)
            return response.text.strip()
        
        # Mock AI response if model is not configured
        return "Categorized by AI (Mock)" 
    except Exception as e:
        print(f"AI Error: {e}")
        return "Unknown"

async def scrape_and_process_task(store_url: str):
    """The background task that does the heavy lifting."""
    global scraping_status
    scraping_status["status"] = "scraping"
    scraping_status["products_scraped"] = 0
    
    # 1. Scrape the data using the improved fetcher
    raw_products = await fetch_shopify_products(store_url)
    
    processed_data = []
    for item in raw_products:
        title = item.get('title', 'No Title')
        
        # 2. Enhance with AI
        ai_category = enhance_with_ai(title)
        
        processed_data.append({
            "id": item.get('id'),
            "title": title,
            "ai_category": ai_category,
            "price": item.get('variants', [{}])[0].get('price', '0.00'),
            "updated_at": item.get('updated_at')
        })
        scraping_status["products_scraped"] += 1

    # 3. Save to CSV using Pandas
    df = pd.DataFrame(processed_data)
    df.to_csv("shopify_data.csv", index=False)
    
    scraping_status["status"] = "completed"

# --- API ENDPOINTS ---

@app.post("/start-scraper")
async def start_scraper(store_url: str, background_tasks: BackgroundTasks):
    """Endpoint for React to trigger the scraper."""
    global scraping_status
    if scraping_status["status"] == "scraping":
        return {"message": "Scraping is already running!"}
    
    # Run the heavy scraping task in the background
    background_tasks.add_task(scrape_and_process_task, store_url)
    return {"message": "Scraping started in the background!"}

@app.get("/status")
async def get_status():
    """React can poll this endpoint to show a progress bar."""
    return scraping_status

@app.get("/download-csv")
async def download_csv():
    """Endpoint for React to download the finished CSV."""
    file_path = "shopify_data.csv"
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename="enhanced_products.csv", media_type='text/csv')
    return {"error": "CSV file not found. Run the scraper first."}