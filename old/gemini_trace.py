import praw
import os
import re
from dotenv import load_dotenv
import google.generativeai as genai
from tqdm import tqdm # For the progress bar
from datetime import datetime

# --- Load environment variables ---
load_dotenv()

# --- Configuration ---
# Reddit API Credentials
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_USER_AGENT = f"Trend Tracer v2.0 by u/{REDDIT_USERNAME}"

# Google Gemini API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Function to Scrape Reddit Data (Modified) ---
def scrape_subreddit_data(subreddit_name: str, time_filter: str = 'week', limit: int = 50):
    """
    Scrapes a subreddit for top posts and returns a structured list of post data.
    
    Returns:
        A list of dictionaries, each containing 'title', 'url', and 'text' for a post.
    """
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME]):
        raise ValueError("Reddit API credentials missing in .env file.")

    print(f"Scraping top {limit} posts from r/{subreddit_name} for the last {time_filter}...")
    
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )
    
    subreddit = reddit.subreddit(subreddit_name)
    top_posts = subreddit.top(time_filter=time_filter, limit=limit)
    
    scraped_posts = []
    for post in top_posts:
        post_text = post.title + "\n"
        if post.is_self:
            post_text += post.selftext + "\n"
        
        post.comments.replace_more(limit=0)
        comment_count = 0
        for comment in post.comments.list():
            if not comment.stickied and isinstance(comment, praw.models.Comment):
                post_text += comment.body + "\n"
                comment_count += 1
            if comment_count >= 3:
                break
        
        scraped_posts.append({
            "title": post.title,
            "url": post.url,
            "text": post_text
        })
        
    print("Scraping complete.")
    return scraped_posts

# --- LLM Functions ---
def get_trends_from_gemini(all_text: str, subreddit_name: str, num_trends: int = 5):
    """
    First pass: Identifies high-level trends from a bulk text dump.
    """
    print("Identifying high-level trends with Gemini...")
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

    prompt = f"""
    Analyze the following collection of posts and comments from the r/{subreddit_name} subreddit.
    Identify the top {num_trends} most significant trends or recurring discussion topics.
    List each trend on a new line, starting with a number. Be concise. Do not add any extra explanation.

    Example:
    1. Discussion on new AI model releases
    2. Debates about Python vs. Rust
    3. Job market and salary concerns

    Data for analysis:
    ---
    {all_text}
    """
    try:
        response = model.generate_content(prompt)
        # Clean up the output to get a simple list of trends
        trends = [line.strip() for line in response.text.split('\n') if re.match(r'^\d+\.', line)]
        return trends
    except Exception as e:
        print(f"An error occurred with the Gemini API during trend identification: {e}")
        return []

def map_post_to_trends_gemini(post_text: str, trends: list):
    """
    Second pass: Categorizes a single post against the identified trends.
    """
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Create a numbered list of trends for the prompt
    trends_formatted = "\n".join(f"{i+1}. {trend}" for i, trend in enumerate(trends))

    prompt = f"""
    Given the following post content:
    ---
    {post_text}
    ---

    And the following list of identified trends:
    ---
    {trends_formatted}
    ---

    Which of these trends (by number) is MOST relevant to the post?
    Respond with ONLY the number of the most relevant trend. If no trend is relevant, respond with "None".
    """
    try:
        response = model.generate_content(prompt)
        # Extract just the number from the response
        match = re.search(r'\d+', response.text)
        if match:
            return int(match.group(0))
    except Exception as e:
        # Don't halt the whole process for one failed API call
        print(f"\nWarning: Could not process a post. Error: {e}")
    return None

# --- Main Execution Block ---
if __name__ == "__main__":
    SUBREDDIT_TO_ANALYZE = "Rag"
    POST_LIMIT = 10 # How many top posts to analyze

    # 1. Scrape data in a structured way
    posts = scrape_subreddit_data(SUBREDDIT_TO_ANALYZE, time_filter='month', limit=POST_LIMIT)
    
    if posts:
        # 2. First Pass: Identify overall trends
        consolidated_text_for_trends = " ".join([p['text'] for p in posts])
        identified_trends = get_trends_from_gemini(consolidated_text_for_trends, SUBREDDIT_TO_ANALYZE)

        if identified_trends:
            print(f"\nIdentified Trends:\n" + "\n".join(identified_trends))
            
            # 3. Second Pass: Map each post to a trend
            # Initialize a dictionary to hold the results
            trends_with_posts = {trend: [] for trend in identified_trends}

            print(f"\nCategorizing {len(posts)} posts against trends (this may take a moment)...")
            for post in tqdm(posts, desc="Analyzing posts"):
                trend_number = map_post_to_trends_gemini(post['text'], identified_trends)
                if trend_number and 1 <= trend_number <= len(identified_trends):
                    # Match the number back to the trend text (adjusting for 0-based index)
                    trend_text = identified_trends[trend_number - 1]
                    trends_with_posts[trend_text].append(post)

            # 4. Generate and save the Markdown report
            OUTPUT_FILENAME = os.path.join("results", f"{SUBREDDIT_TO_ANALYZE}_trend_report_{datetime.now().strftime('%Y-%m-%d')}.md")
            
            with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
                f.write(f"# Trend Report for r/{SUBREDDIT_TO_ANALYZE}\n")
                f.write(f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                for trend, contributing_posts in trends_with_posts.items():
                    f.write(f"## {trend}\n\n")
                    if contributing_posts:
                        f.write("**Contributing Posts:**\n")
                        for post in contributing_posts:
                            # Format for Markdown: * [Title](URL)
                            f.write(f"*   [{post['title']}]({post['url']})\n")
                    else:
                        f.write("*No specific posts were strongly mapped to this trend in the sample.*\n")
                    f.write("\n---\n\n")
            
            print(f"\nAnalysis complete! Report saved to {OUTPUT_FILENAME}")
        else:
            print("Could not identify any trends from the data.")
    else:
        print("No data was scraped. Cannot generate a report.")