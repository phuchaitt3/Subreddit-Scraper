# summarizer_utils.py
"""
Reusable core functions for the traceable summarization workflow.
This module contains the logic for text processing, LLM interaction for
extractive and abstractive summarization.
"""

import json
import nltk
from openai import OpenAI
import markdown                  # <-- ADDED IMPORT
from bs4 import BeautifulSoup    # <-- ADDED IMPORT

# --- NEW FUNCTION TO CLEAN MARKUP ---
def clean_text_from_markup(raw_text: str) -> str:
    """
    Cleans raw text by stripping HTML and Markdown tags.
    1. Converts Markdown to HTML.
    2. Parses the HTML and extracts only the text content.
    """
    # Step 1: Convert Markdown to HTML
    html = markdown.markdown(raw_text)
    
    # Step 2: Use BeautifulSoup to parse the HTML and extract text
    soup = BeautifulSoup(html, "html.parser")
    
    # Get all the text, using a space as a separator and stripping whitespace
    clean_text = soup.get_text(separator=' ', strip=True)
    
    return clean_text

def download_nltk_data_if_needed():
    """Checks for and downloads the NLTK 'punkt' tokenizer if not present."""
    try:
        nltk.sent_tokenize("test sentence")
    except LookupError:
        print("NLTK 'punkt' tokenizer not found. Downloading...")
        nltk.download('punkt')
        print("Download complete.")

# --- MODIFIED FUNCTION ---
def preprocess_text_to_numbered_sentences(raw_text: str) -> tuple[dict, str]:
    """
    Cleans markup and then splits the clean text into uniquely identified sentences.
    """
    # Step 1: Clean the raw text to remove HTML/Markdown (the new logic)
    cleaned_text = clean_text_from_markup(raw_text)
    
    # Step 2: Tokenize the *cleaned* text into sentences
    sentences = nltk.sent_tokenize(cleaned_text)
    
    # The rest of the function remains the same
    sentences_map = {f"S{i+1}": sentence for i, sentence in enumerate(sentences)}
    formatted_text = "\n".join([f"[{sid}] {s}" for sid, s in sentences_map.items()])
    return sentences_map, formatted_text

def determine_sentence_count(total_sentences: int) -> int:
    """Dynamically determines the ideal number of sentences for a summary."""
    return max(7, min(int(total_sentences * 0.15), 40))

def extract_key_sentence_ids(formatted_text: str, client: OpenAI, model: str, sentence_count: int) -> list:
    """Uses an LLM to identify the most important sentence IDs from a numbered text."""
    prompt = f"""
    Analyze the following numbered text from a document. Identify the {sentence_count} most important sentences for understanding its purpose, features, and usage.
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
        print(f"An unexpected error occurred during key sentence extraction: {e}")
        return []

def generate_abstractive_summary(key_sentences: list[str], client: OpenAI, model: str) -> str:
    """Generates a final, cited summary from a list of key sentences."""
    key_sentences_text = "\n".join(key_sentences)
    prompt = f"""
    Synthesize the following key sentences from a document into a smooth summary paragraph.
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
        print(f"An unexpected error occurred during final summary generation: {e}")
        return ""