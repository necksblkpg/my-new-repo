# translate_descriptions.py

from language_config import get_language_code
from flask import session
import pandas as pd
import os
import json
import sys
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
from time import sleep
import re
import openai

# Sätt din OpenAI-nyckel på ett säkert sätt i miljövariabler
openai.api_key = os.getenv('OPENAI_API_KEY')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    stream=sys.stdout)

@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
def translate_single_description(text, target_language, user_prompt):
    if pd.isna(text) or not text.strip():
        return ""

    prompt = f"""You are a professional product description translator.
Translate this text to {target_language}, maintaining a natural and professional tone:

{text}

Custom user instructions:
{user_prompt}

Important:
- Keep product terminology consistent and accurate
- Maintain the same level of detail as the original
- Ensure proper grammar and natural flow in {target_language}
- Preserve the exact meaning of technical terms
"""

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an expert product translator."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    translated_text = response.choices[0].message.content.strip()

    # Korrigera versalisering i början av meningar
    translated_text = re.sub(r'(^|[.?!]\s+)([a-zåäöéèóúìùü]+)', 
                             lambda m: m.group(1) + m.group(2).capitalize(), 
                             translated_text)

    return translated_text

def translate_descriptions_function(upload_folder, input_file, dictionary_file, selected_languages):
    # dictionary_file ignoreras nu
    BATCH_SIZE = 50
    completed_languages = set()
    completed_files = []

    try:
        user_prompt = session.get('user_prompt', '').strip()

        input_csv = os.path.join(upload_folder, input_file)
        input_df = pd.read_csv(input_csv, sep=',', dtype={'SKU': str})
        total_rows = len(input_df)

        # Skapa kolumner för valda språk
        for language in selected_languages:
            lang_code = get_language_code(language)
            column_name = f'Description - {lang_code}'
            if column_name not in input_df.columns:
                input_df[column_name] = ''

        for target_language in selected_languages:
            if target_language in completed_languages:
                continue

            lang_code = get_language_code(target_language)
            column_name = f'Description - {lang_code}'

            batch_start = 0
            while batch_start < total_rows:
                batch_end = min(batch_start + BATCH_SIZE, total_rows)

                for index in range(batch_start, batch_end):
                    try:
                        text = input_df.iloc[index]['Description']
                        translated = translate_single_description(text, target_language, user_prompt)
                        input_df.loc[index, column_name] = translated
                        progress = int((index + 1) / total_rows * 100)
                        yield json.dumps({"language": target_language, "progress": progress}) + "\n\n"
                        sleep(0.3)

                    except Exception as e:
                        error_msg = f"Error at index {index}: {str(e)}"
                        logging.error(error_msg)
                        yield json.dumps({
                            "error": error_msg,
                            "language": target_language
                        }) + "\n\n"
                        continue

                batch_start += BATCH_SIZE

            # Spara fil per språk
            lang_filename = f"translated_descriptions_{target_language}.csv"
            lang_output_path = os.path.join(upload_folder, lang_filename)
            selected_columns = ['Product ID', 'SKU', 'Description', column_name]
            input_df[selected_columns].to_csv(lang_output_path, index=False)

            completed_languages.add(target_language)
            completed_files.append({"language": target_language, "file": lang_filename})
            yield json.dumps({"language": target_language, "progress": 100, "status": "complete", "file": lang_filename}) + "\n\n"

        # Spara sammanställd fil
        output_filename = "translated_descriptions_all.csv"
        selected_columns = ['Product ID', 'SKU', 'Description'] + [
            f'Description - {get_language_code(lang)}'
            for lang in completed_languages
        ]
        input_df[selected_columns].to_csv(os.path.join(upload_folder, output_filename), index=False)
        yield json.dumps({
            "complete": True,
            "file": output_filename,
            "completed_files": completed_files,
            "completed_languages": list(completed_languages)
        }) + "\n\n"

    except Exception as e:
        error_msg = f"Fatal error in translation process: {str(e)}"
        logging.error(error_msg)
        yield json.dumps({"error": error_msg}) + "\n\n"
