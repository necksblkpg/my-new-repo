# translate_descriptions.py

import pandas as pd
import os
import json
import sys
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
from time import sleep
import re
import openai

# Sätt client till openai för att använda ny anropsmetod
client = openai
client.api_key = os.getenv('OPENAI_API_KEY')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    stream=sys.stdout)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def rewrite_single_description(text, system_prompt, user_prompt):
    if pd.isna(text) or not text.strip():
        return ""

    combined_prompt = f"""
System prompt:
{system_prompt}

User prompt:
{user_prompt}

Original text:
{text}

Rewrite this English product description according to the system and user instructions above. The final output should be in English.
"""

    # Anropa den nya metoden
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an expert product copywriter."},
            {"role": "user", "content": combined_prompt}
        ],
        temperature=0.1
    )

    rewritten_text = response.choices[0].message.content.strip()

    # Korrigera versalisering i början av meningar
    rewritten_text = re.sub(
        r'(^|[.?!]\s+)([a-zåäöéèóúìùü]+)',
        lambda m: m.group(1) + m.group(2).capitalize(),
        rewritten_text
    )

    return rewritten_text

def rewrite_descriptions_two_steps_function(upload_folder, input_file, system_prompt_1, user_prompt_1, system_prompt_2, user_prompt_2):
    try:
        input_csv = os.path.join(upload_folder, input_file)
        input_df = pd.read_csv(input_csv, sep=None, engine='python', dtype={'SKU': str})
        total_rows = len(input_df)

        if 'Description (Rewrite Step 1)' not in input_df.columns:
            input_df['Description (Rewrite Step 1)'] = ''

        # Steg 1
        for i in range(total_rows):
            text = input_df.iloc[i]['Description']
            try:
                rewritten = rewrite_single_description(text, system_prompt_1, user_prompt_1)
                input_df.loc[i, 'Description (Rewrite Step 1)'] = rewritten
                progress = int(((i + 1) / (2 * total_rows)) * 100)
                yield json.dumps({"progress": progress}) + "\n\n"
                sleep(0.3)
            except Exception as e:
                error_msg = f"Error at step 1, index {i}: {str(e)}"
                logging.error(error_msg)
                yield json.dumps({"error": error_msg}) + "\n\n"

        if 'Description (Rewritten)' not in input_df.columns:
            input_df['Description (Rewritten)'] = ''

        # Steg 2
        for j in range(total_rows):
            text_step_1 = input_df.iloc[j]['Description (Rewrite Step 1)']
            try:
                rewritten_step_2 = rewrite_single_description(text_step_1, system_prompt_2, user_prompt_2)
                input_df.loc[j, 'Description (Rewritten)'] = rewritten_step_2
                progress = int(((total_rows + j + 1) / (2 * total_rows)) * 100)
                yield json.dumps({"progress": progress}) + "\n\n"
                sleep(0.3)
            except Exception as e:
                error_msg = f"Error at step 2, index {j}: {str(e)}"
                logging.error(error_msg)
                yield json.dumps({"error": error_msg}) + "\n\n"

        # Spara slutlig fil
        output_filename = "rewritten_descriptions_all.csv"
        selected_columns = ['Product ID', 'SKU', 'Description', 'Description (Rewrite Step 1)', 'Description (Rewritten)']
        input_df[selected_columns].to_csv(os.path.join(upload_folder, output_filename), index=False)
        yield json.dumps({"complete": True, "file": output_filename}) + "\n\n"

    except Exception as e:
        error_msg = f"Fatal error in rewriting process: {str(e)}"
        logging.error(error_msg)
        yield json.dumps({"error": error_msg}) + "\n\n"
