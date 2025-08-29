# reddit_post_summarizer.py

import praw # For Reddit
import re
import os
import json
import nltk
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# --- Reddit Data Fetching ---
def get_reddit_post_content(post_url: str) -> tuple[str, str, str]:
    """Retrieves the title, ID, and full text content for a given Reddit post URL."""
    try:
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        username = os.getenv("REDDIT_USERNAME")
        user_agent = f"Post Summarizer v1.0 by u/{username}"
        
        reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
        submission = reddit.submission(url=post_url)
        
        title = submission.title
        post_id = submission.id
        
        # Consolidate text from title, body, and top comments
        full_text = f"Title: {title}\n"
        if submission.selftext:
            full_text += f"Body: {submission.selftext}\n"
        
        full_text += "\n--- COMMENTS ---\n"
        submission.comments.replace_more(limit=0)
        for i, comment in enumerate(submission.comments.list()):
            if i >= 10: break # Get more comments for a detailed summary
            if not comment.stickied and isinstance(comment, praw.models.Comment) and comment.author:
                full_text += f"{comment.author.name}: {comment.body.replace('#', '')}\n" # Sanitize text
        
        return title, post_id, full_text.replace('\n', ' ').replace('  ', ' ')
        
    except Exception as e:
        return None, None, f"Error: Could not fetch Reddit post. Details: {e}"

# --- All other functions from your summarizer script are reused here ---
# (I've copied them directly for a complete, runnable script)

def download_nltk_data_if_needed():
    try: nltk.sent_tokenize("test")
    except LookupError: nltk.download('punkt')

def preprocess_text_to_numbered_sentences(raw_text: str):
    sentences = nltk.sent_tokenize(raw_text)
    sentences_map = {f"S{i+1}": sentence for i, sentence in enumerate(sentences)}
    formatted_text = "\n".join([f"[{sid}] {s}" for sid, s in sentences_map.items()])
    return sentences_map, formatted_text

def determine_sentence_count(total_sentences: int):
    return max(7, min(int(total_sentences * 0.15), 40))

def extract_key_sentence_ids(formatted_text: str, client: OpenAI, model: str, sentence_count: int):
    prompt = f"""
    Analyze the following numbered text from a Reddit post. Identify the {sentence_count} most important sentences for understanding the main points.
    Your ONLY output must be a single JSON object with a key "key_sentence_ids" containing an array of the sentence IDs.

    Example: {{"key_sentence_ids": ["S5", "S12", "S25"]}}

    Numbered Text:
    ---
    {formatted_text}
    ---
    """
    try:
        print(f"\nSending request to '{model}' to identify key sentences...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful research assistant that outputs only JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("key_sentence_ids", [])
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

def generate_abstractive_summary(key_sentences: list[str], client: OpenAI, model: str):
    key_sentences_text = "\n".join(key_sentences)
    prompt = f"""
    Synthesize the following key sentences from a Reddit post into a smooth summary paragraph.
    CRITICAL: At the end of EACH new sentence you write, you MUST cite the original sentence number(s) it is based on, like `[S1]` or `[S5, S12]`.
    Base your summary ONLY on the information provided.

    Key Sentences to Rewrite:
    ---
    {key_sentences_text}
    ---
    Final Summary:
    """
    try:
        print(f"\nSending request to '{model}' to generate the final summary...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a skilled writer who follows citation rules perfectly."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return ""

# --- Main Execution Block for the Post Summarizer ---
if __name__ == "__main__":
    download_nltk_data_if_needed()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    OUTPUT_DIR = "reddit_summaries"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    reddit_url = input("Please enter the Reddit Post URL for a deep-dive summary: ")
    print("--- Step 1: Fetching Post Content from Reddit ---")
    
    post_title, post_id, long_text = get_reddit_post_content(reddit_url)
    
    if long_text.startswith("Error:"):
        print(long_text)
        exit()
    print(f"Successfully fetched content for post: \"{post_title}\"")

    print("\n--- Step 2: Pre-processing Text ---")
    sentences_map, formatted_prompt_text = preprocess_text_to_numbered_sentences(long_text)
    dynamic_count = determine_sentence_count(len(sentences_map))
    print(f"Split text into {len(sentences_map)} sentences. Aiming for a {dynamic_count}-sentence summary.")
    
    print("\n--- Step 3: Extracting Key Sentences ---")
    key_ids = extract_key_sentence_ids(formatted_prompt_text, client, model="gpt-4.1-nano", sentence_count=dynamic_count)

    if not key_ids:
        print("\nCould not extract key sentences. Exiting.")
        exit()

    print(f"\n--- Step 4: Generating Report ---")
    output_filename = os.path.join(OUTPUT_DIR, f"{post_id}_summary.md")
    
    # Part 1: Extractive Summary
    markdown_content = [
        f"# Detailed Summary for Reddit Post\n",
        f"**Source URL:** {reddit_url}\n",
        "---",
        "## Part 1: Key Sentences (Extractive Summary)\n"
    ]
    key_sentences_for_final_summary = []
    for sid in key_ids:
        if sid in sentences_map:
            sentence = sentences_map[sid]
            markdown_content.append(f"* **`{sid}`**: {sentence}")
            key_sentences_for_final_summary.append(f"[{sid}] {sentence}")
    
    # Part 2: Abstractive Summary
    final_summary = generate_abstractive_summary(key_sentences_for_final_summary, client, model="gpt-4.1-nano")
    if final_summary:
        markdown_content.append("\n\n---\n")
        markdown_content.append("## Part 2: Final Summary (with Citations)\n")
        markdown_content.append(final_summary)
    
    # Write everything to the file
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("\n".join(markdown_content))
    
    print(f"\n✅ Complete summary successfully saved to: '{output_filename}'")