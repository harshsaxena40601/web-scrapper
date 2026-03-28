from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
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
    # model = genai.GenerativeModel('gemini-2.5-flash')

app = FastAPI()

# A global variable to track scraping status
scraping_status = {"status": "idle", "products_scraped": 0}

@app.get("/check-env")
async def check_env():
    """A quick test to make sure your .env is loading properly."""
    # Never return the actual password in a real app, this is just for testing!
    if DATABASE_URL:
        return {"message": "Database URL loaded successfully!"}
    return {"error": "Failed to load environment variables."}

async def fetch_shopify_products(store_url: str):
    """Scrapes the products.json endpoint of a Shopify store."""
    url = f"{store_url}/products.json?limit=50"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            return response.json().get('products', [])
        return []

def enhance_with_ai(product_title: str):
    """Uses AI to categorize the product based on its title."""
    try:
        # NOTE: Uncomment the AI code once you add your API key
        # prompt = f"Categorize this product in one word: {product_title}"
        # response = model.generate_content(prompt)
        # return response.text.strip()
        
        # Mock AI response for testing
        return "Categorized by AI" 
    except Exception as e:
        return "Unknown"

async def scrape_and_process_task(store_url: str):
    """The background task that does the heavy lifting."""
    global scraping_status
    scraping_status["status"] = "scraping"
    
    # 1. Scrape the data
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
    
    # Run the heavy scraping task in the background so the API doesn't freeze
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