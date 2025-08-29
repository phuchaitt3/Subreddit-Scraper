# subreddit_trends.py

import praw
import os
import re
from dotenv import load_dotenv
import openai
from tqdm import tqdm
from datetime import datetime

# --- Load environment variables ---
load_dotenv()

# --- Configuration ---
CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
USER_AGENT = f"Trend Tracer v4.0 by u/{REDDIT_USERNAME}"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Function to Scrape Reddit Data (Modified for Traceability) ---
def scrape_subreddit_data(subreddit_name: str, time_filter: str = 'week', limit: int = 50):
    """
    Scrapes a subreddit and returns a structured list of post data.
    """
    if not all([CLIENT_ID, CLIENT_SECRET, REDDIT_USERNAME]):
        raise ValueError("Reddit API credentials missing in .env file.")

    print(f"Scraping top {limit} posts from r/{subreddit_name} for the last {time_filter}...")
    reddit = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, user_agent=USER_AGENT)
    subreddit = reddit.subreddit(subreddit_name)
    top_posts = subreddit.top(time_filter=time_filter, limit=limit)
    
    scraped_posts = []
    for post in top_posts:
        post_text = f"POST TITLE: {post.title}\n"
        if post.is_self:
            post_text += f"POST BODY: {post.selftext}\n"
        post.comments.replace_more(limit=0)
        for i, comment in enumerate(post.comments.list()):
            if i >= 3: break
            if not comment.stickied and isinstance(comment, praw.models.Comment):
                post_text += f"COMMENT: {comment.body}\n"
        scraped_posts.append({"title": post.title, "url": post.url, "text": post_text})
        
    print("Scraping complete.")
    return scraped_posts

# --- LLM Functions ---
def get_trends_and_summaries_openai(all_text: str, subreddit_name: str, num_trends: int = 4):
    """
    Pass 1: Identifies trends and generates summaries in a single, structured call.
    Uses a more powerful model for high-quality analysis.
    """
    if not OPENAI_API_KEY: raise ValueError("OPENAI_API_KEY not found in .env file")
    
    print("Identifying trends and summaries with OpenAI...")
    openai.api_key = OPENAI_API_KEY
    
    prompt = f"""
    You are an expert community analyst. Analyze the following text from the r/{subreddit_name} subreddit.
    Identify the top {num_trends} major trends or recurring discussion topics.
    
    For each trend, provide a concise title and a 1-2 sentence summary.
    **Format your output EXACTLY as follows for each trend, with no extra text:**
    
    Trend Title: [The title of the trend]
    Summary: [The summary of the trend]
    ---
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1-mini", # Powerful model for analysis
            messages=[
                {"role": "system", "content": f"You are an expert analyst for the r/{subreddit_name} subreddit."},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "Here are the trends based on the data provided:\n\n" + all_text}
            ],
            temperature=0.5,
        )
        response_text = response.choices[0].message.content
        
        # Use regex to parse the structured output
        trends_data = {}
        pattern = re.compile(r"Trend Title: (.*?)\nSummary: (.*?)\n---", re.DOTALL)
        matches = pattern.findall(response_text)
        
        if not matches:
            print("Warning: Could not parse trends from the LLM response. The format may have been incorrect.")
            return {}
            
        for title, summary in matches:
            trends_data[title.strip()] = summary.strip()
            
        return trends_data
    except Exception as e:
        print(f"An error occurred with the OpenAI API during trend identification: {e}")
        return {}

def map_post_to_trend_openai(post_text: str, trends_data: dict):
    """
    Pass 2: Categorizes a single post against trends, using summaries for context.
    Uses a faster, cheaper model for high-volume classification.
    """
    openai.api_key = OPENAI_API_KEY
    trend_titles = list(trends_data.keys())
    
    # Build a context-rich prompt
    trends_formatted = "\n".join(
        f"{i+1}. Trend Title: {title}\n   Summary: {trends_data[title]}" 
        for i, title in enumerate(trend_titles)
    )
    
    prompt = f"""
    Below is the text from a single Reddit post. Following that is a numbered list of discussion trends, each with a title and a summary.
    
    POST TEXT:
    ---
    {post_text}
    ---
    
    TRENDS:
    ---
    {trends_formatted}
    ---
    
    Which trend number is the MOST relevant to the post text?
    Respond with ONLY the number. If no trend is a good fit, respond with "None".
    """
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1-mini", # Fast, cheap model for classification
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        response_text = response.choices[0].message.content.strip()
        match = re.search(r'\d+', response_text)
        if match: return int(match.group(0))
    except Exception as e:
        print(f"\nWarning: Could not process a post classification. Error: {e}")
    return None

# --- Main Execution Block ---
if __name__ == "__main__":
    SUBREDDIT_TO_ANALYZE = "Rag"
    POST_LIMIT = 10
    
    posts = scrape_subreddit_data(SUBREDDIT_TO_ANALYZE, time_filter='week', limit=POST_LIMIT)
    
    if posts:
        # Pass 1: Identify trends and their summaries
        consolidated_text = "\n---\n".join([p['text'] for p in posts])
        trends_and_summaries = get_trends_and_summaries_openai(consolidated_text, SUBREDDIT_TO_ANALYZE)

        if trends_and_summaries:
            print("\nIdentified Trends and Summaries:")
            for title, summary in trends_and_summaries.items():
                print(f"- {title}: {summary}")
            
            # Pass 2: Map each post to a trend using the summaries for context
            trend_titles = list(trends_and_summaries.keys())
            trends_with_posts = {title: [] for title in trend_titles}
            
            print(f"\nCategorizing {len(posts)} posts against trends...")
            for post in tqdm(posts, desc="Classifying posts"):
                trend_number = map_post_to_trend_openai(post['text'], trends_and_summaries)
                if trend_number and 1 <= trend_number <= len(trend_titles):
                    trend_title = trend_titles[trend_number - 1]
                    trends_with_posts[trend_title].append(post)

            # Final step: Generate and save the detailed Markdown report
            OUTPUT_FILENAME = os.path.join("reddit_trends", f"{SUBREDDIT_TO_ANALYZE}_trend_report_{datetime.now().strftime('%Y-%m-%d')}.md")
            with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
                f.write(f"# Trend Report for r/{SUBREDDIT_TO_ANALYZE}\n")
                f.write(f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                for title, summary in trends_and_summaries.items():
                    f.write(f"## {title}\n\n")
                    f.write(f"**Summary:** {summary}\n\n")
                    
                    contributing_posts = trends_with_posts.get(title, [])
                    if contributing_posts:
                        f.write("**Contributing Posts:**\n")
                        for post in contributing_posts:
                            f.write(f"*   [{post['title']}]({post['url']})\n")
                    else:
                        f.write("*No posts from the sample were strongly mapped to this trend.*\n")
                    f.write("\n---\n\n")
            
            print(f"\nAnalysis complete! Report saved to {OUTPUT_FILENAME}")
        else:
            print("Could not identify any trends from the data.")
    else:
        print("No data was scraped. Cannot generate a report.")