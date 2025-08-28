import praw
import os
from dotenv import load_dotenv
import openai

load_dotenv()
# --- Configuration ---
# Retrieve credentials from environment variables
CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
# It's good practice to make the user agent unique and informative
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
USER_AGENT = f"My Reddit Scraper v1.0 by u/{REDDIT_USERNAME}"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def scrape_subreddit_data(subreddit_name: str, time_filter: str = 'week', limit: int = 50):
    """
    Scrapes a subreddit for top posts within a given time frame.
    
    Args:
        subreddit_name: The name of the subreddit to scrape.
        time_filter: The time filter for top posts ('day', 'week', 'month', 'year', 'all').
        limit: The number of posts to fetch.
        
    Returns:
        A single string containing the concatenated text of posts and comments.
    """
    print(f"Scraping top {limit} posts from r/{subreddit_name} for the last {time_filter}...")
    
    reddit = praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT,
    )
    
    subreddit = reddit.subreddit(subreddit_name)
    top_posts = subreddit.top(time_filter=time_filter, limit=limit)
    
    # Consolidate text data into a single string
    consolidated_text = ""
    for post in top_posts:
        consolidated_text += f"POST TITLE: {post.title}\n"
        # Include the post's body text if it's a self-post
        if post.is_self:
            consolidated_text += f"POST BODY: {post.selftext}\n"
        
        # Get the top few comments
        post.comments.replace_more(limit=0)
        comment_count = 0
        for comment in post.comments.list():
            if not comment.stickied and isinstance(comment, praw.models.Comment):
                consolidated_text += f"COMMENT: {comment.body}\n"
                comment_count += 1
            if comment_count >= 3: # Limit to top 3 comments per post
                break
        consolidated_text += "---\n\n" # Separator for posts
        
    print("Scraping complete.")
    return consolidated_text

def summarize_with_openai(text_data: str, subreddit_name: str):
    """Summarizes text using OpenAI's API."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found in .env file")
        
    print("Summarizing with OpenAI...")
    openai.api_key = OPENAI_API_KEY
    
    prompt = f"""
    You are an expert community analyst. Your task is to analyze the following text, which contains a collection of post titles, bodies, and comments from the r/{subreddit_name} subreddit.

    Identify the top 3-5 major trends, recurring discussion topics, and overall sentiment within the community based on this data.

    For each trend you identify, please provide a concise title and a brief 1-2 sentence explanation. Structure your output clearly.

    Here is the data:
    ---
    {text_data}
    ---
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a helpful community trend analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"An error occurred with the OpenAI API: {e}"

if __name__ == "__main__":
    SUBREDDIT_TO_ANALYZE = "Rag"
    OUTPUT_FILENAME = os.path.join("results", f"{SUBREDDIT_TO_ANALYZE}_trends.md")

    # 1. Scrape the data
    scraped_data = scrape_subreddit_data(SUBREDDIT_TO_ANALYZE, time_filter='week', limit=50)
    
    # Ensure we have data before proceeding
    if scraped_data:
        # 2. Summarize the data using your chosen LLM
        # --- UNCOMMENT THE ONE YOU WANT TO USE ---
        
        summary = summarize_with_openai(scraped_data, SUBREDDIT_TO_ANALYZE)
        
        # 3. Prepare content for the Markdown file
        markdown_content = f"# Trend Summary for r/{SUBREDDIT_TO_ANALYZE}\n\n"
        markdown_content += f"**Date Generated:** {os.getenv('DATE_GENERATED') if os.getenv('DATE_GENERATED') else 'N/A'}\n\n" # Optional: Add a date
        markdown_content += "--- \n\n"
        markdown_content += summary
        
        # 4. Save to a Markdown file
        try:
            with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            print(f"\nSummary successfully saved to {OUTPUT_FILENAME}")
        except Exception as e:
            print(f"Error saving summary to file: {e}")
            # Still print to console if file save fails
            print("\n" + "="*50)
            print(f"TREND SUMMARY FOR r/{SUBREDDIT_TO_ANALYZE}")
            print("="*50 + "\n")
            print(summary)
    else:
        print("No data was scraped. Cannot generate summary.")