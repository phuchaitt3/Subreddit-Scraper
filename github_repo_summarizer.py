# github_repo_summarizer.py

import requests
import re
import os
from openai import OpenAI
from dotenv import load_dotenv

# --- Import the core summarization logic ---
import summarizer_utils as su

load_dotenv()

# --- GitHub-Specific Data Fetching ---
def get_github_readme_content(repo_url: str) -> tuple[str | None, str]:
    """Retrieves the repo name and raw text content of the README.md for a given GitHub repo URL."""
    match = re.search(r"github\.com/([^/]+/[^/.]+)", repo_url)
    if not match:
        return None, "Error: Could not extract a valid 'user/repo' from the URL."
        
    user_repo = match.group(1).replace('.git', '')
    repo_name_for_file = user_repo.replace('/', '_')
    
    for branch in ['main', 'master']:
        raw_url = f"https://raw.githubusercontent.com/{user_repo}/{branch}/README.md"
        try:
            response = requests.get(raw_url)
            if response.status_code == 200:
                print(f"Successfully fetched README.md from the '{branch}' branch.")
                return repo_name_for_file, response.text
        except requests.exceptions.RequestException as e:
            return None, f"An error occurred while fetching the README: {e}"
            
    return None, f"Error: Could not find README.md in either 'main' or 'master' branch for {user_repo}."

# --- Main Execution Block ---
if __name__ == "__main__":
    # --- 1. Setup ---
    su.download_nltk_data_if_needed()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    OUTPUT_DIR = "repo_summaries"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- 2. Input and Data Fetching ---
    github_url = input("Please enter the GitHub Repository URL to summarize: ")
    print("--- Step 1: Fetching README.md from GitHub ---")
    repo_name, readme_text = get_github_readme_content(github_url)
    
    if readme_text.startswith("Error:"):
        print(readme_text)
        exit()
    print(f"Successfully fetched README for repo: \"{repo_name}\"")

    # --- 3. Pre-processing (using the utility function) ---
    print("\n--- Step 2: Pre-processing Text ---")
    sentences_map, formatted_text = su.preprocess_text_to_numbered_sentences(readme_text)
    dynamic_count = su.determine_sentence_count(len(sentences_map))
    print(f"Split text into {len(sentences_map)} sentences. Aiming for a {dynamic_count}-sentence summary.")
    
    # --- 4. Extraction (using the utility function) ---
    print("\n--- Step 3: Extracting Key Sentences ---")
    key_ids = su.extract_key_sentence_ids(formatted_text, client, model="gpt-4.1-nano", sentence_count=dynamic_count)

    if not key_ids:
        print("\nCould not extract key sentences. Exiting.")
        exit()

    # --- 5. Report Generation (using the utility function) ---
    print(f"\n--- Step 4: Generating Report ---")
    output_filename = os.path.join(OUTPUT_DIR, f"{repo_name}_summary.md")
    
    markdown_content = [
        f"# Detailed Summary for GitHub Repo: {repo_name}\n",
        f"**Source URL:** {github_url}\n", "---",
        "## Part 1: Key Sentences (Extractive Summary)\n"
    ]
    key_sentences_for_final_summary = []
    for sid in key_ids:
        if sid in sentences_map:
            sentence = sentences_map[sid]
            markdown_content.append(f"* **`{sid}`**: {sentence}")
            key_sentences_for_final_summary.append(f"[{sid}] {sentence}")
    
    final_summary = su.generate_abstractive_summary(key_sentences_for_final_summary, client, model="gpt-4.1-nano")
    if final_summary:
        markdown_content.extend(["\n\n---", "## Part 2: Final Summary (with Citations)\n", final_summary])
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("\n".join(markdown_content))
    
    print(f"\n✅ Complete summary successfully saved to: '{output_filename}'")