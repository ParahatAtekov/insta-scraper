from scrapers.instagram import scrape_and_filter_media
import os
from dotenv import load_dotenv

load_dotenv()

# Test with different usernames
usernames = ["nasa", "invalidusername12345", "cristiano"]

for username in usernames:
    print(f"\nTesting username: {username}")
    try:
        result = scrape_and_filter_media(username=username, max_posts=1)
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")