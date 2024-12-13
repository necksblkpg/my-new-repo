# translate_descriptions.py

from language_config import get_language_mapping, get_reverse_mapping, get_language_code
from flask import session
import pandas as pd
from openai import OpenAI
import os
import json
import sys
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
from time import sleep
import re

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    stream=sys.stdout)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def load_translation_examples(examples_df, target_language):
    target_code = get_language_code(target_language)
    target_column = f'Display name - {target_code}'

    if target_column in examples_df.columns:
        examples = examples_df[['Display Name',
                                target_column]].dropna().head(21)
        if not examples.empty:
            example_text = "\n".join([
                f"Original: {row['Display Name']} -> Translated: {row[target_column]}"
                for _, row in examples.iterrows()
            ])
            return example_text, True
    return "", False


def load_dictionary(upload_folder, dictionary_file):
    if not dictionary_file:
        logging.warning("No dictionary file provided")
        return {}

    try:
        file_path = os.path.join(upload_folder, dictionary_file)
        logging.info(f"Loading dictionary from: {file_path}")

        df = pd.read_csv(file_path)
        logging.info(f"Dictionary DataFrame columns: {df.columns.tolist()}")
        logging.info(f"Dictionary DataFrame content:\n{df.to_string()}")

        dictionary = {}

        for _, row in df.iterrows():
            if 'Original' in df.columns:
                original = row['Original'].strip().lower()
                translations = {}
                for col in df.columns:
                    if col != 'Original' and pd.notna(row[col]):
                        translations[col] = row[col].strip()
                dictionary[original] = translations
                logging.info(
                    f"Added dictionary entry: {original} -> {translations}")

        logging.info(f"Final dictionary content: {dictionary}")
        return dictionary
    except Exception as e:
        logging.error(f"Error loading dictionary: {e}")
        return {}


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=4, max=10))
def translate_display_name(text, target_language, dictionary=None):
    if pd.isna(text) or not text.strip():
        return ""

    try:
        logging.info(f"\n=== Starting translation ===")
        logging.info(f"Input text: {text}")
        logging.info(f"Target language: {target_language}")

        # Steg 1: Gör en högkvalitativ översättning med GPT-4
        prompt = f"""You are a professional product description translator.
                    Translate this text to {target_language}, maintaining a natural and professional tone:

                    {text}

                    Important:
                    - Keep product terminology consistent and accurate
                    - Maintain the same level of detail as the original
                    - Ensure proper grammar and natural flow in {target_language}
                    - Preserve the exact meaning of technical terms"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": "You are an expert product translator with deep knowledge of technical terminology."
            }, {
                "role": "user",
                "content": prompt
            }],
            temperature=0.1)

        translated_text = response.choices[0].message.content.strip()
        logging.info(f"Initial AI Translation: {translated_text}")

        # Steg 2: Applicera ordlistan om den finns - men endast för exakta termer
        final_text = translated_text
        if dictionary:
            lang_code = get_language_code(target_language).lower()
            replacements_made = []

            # Hitta alla termer i originaltexten först
            for orig_term, translations in dictionary.items():
                if translations.get(lang_code):
                    # Kontrollera om den exakta termen finns i originaltexten
                    if orig_term.lower() in text.lower():
                        required_translation = translations[lang_code]

                        # Identifiera den exakta delen som ska ersättas
                        term_check_prompt = f"""In the following {target_language} translation, what EXACT word or phrase corresponds to the English term '{orig_term}'?

                                             Original English: {text}
                                             Translation: {translated_text}

                                             Important: Only return the exact corresponding word/phrase if it's a direct translation of '{orig_term}'. 
                                             If the term appears in a different context or form, return 'NONE'."""

                        term_check_response = client.chat.completions.create(
                            model="gpt-4",
                            messages=[{
                                "role": "system",
                                "content": "You are a precise term matcher. Only identify exact term matches."
                            }, {
                                "role": "user",
                                "content": term_check_prompt
                            }],
                            temperature=0)

                        current_translation = term_check_response.choices[0].message.content.strip()

                        if current_translation and current_translation.upper() != 'NONE':
                            # Ersätt endast om vi har en exakt match
                            final_text = final_text.replace(current_translation, required_translation)
                            replacements_made.append(f"Replaced '{current_translation}' with '{required_translation}'")
                            logging.info(f"Term replacement: {current_translation} -> {required_translation}")

            if replacements_made:
                logging.info(f"Applied dictionary replacements: {replacements_made}")

        # Steg 3: Korrigera versalisering i början av meningar
        # Denna regex letar efter meningens start (början av text eller efter .?!),
        # följt av mellanslag och en bokstav. Den bokstaven görs versal.
        final_text = re.sub(r'(^|[.?!]\s+)([a-zåäöéèóúìùü]+)', 
                            lambda m: m.group(1) + m.group(2).capitalize(), 
                            final_text)

        return final_text

    except Exception as e:
        logging.error(f"Error during translation of '{text}' to {target_language}: {e}")
        raise


def translate_descriptions_function(upload_folder, input_file,
                                    dictionary_file, selected_languages):
    logging.info(
        f"Starting translation with dictionary file: {dictionary_file}")
    dictionary = load_dictionary(upload_folder, dictionary_file)
    logging.info(f"Loaded dictionary content: {dictionary}")
    BATCH_SIZE = 50
    completed_languages = set()
    completed_files = []

    try:
        logging.info(
            f"Starting translation process for languages: {selected_languages}"
        )
        input_csv = os.path.join(upload_folder, input_file)

        input_df = pd.read_csv(input_csv, sep=',', dtype={'SKU': str})
        total_rows = len(input_df)

        # Create columns for all selected languages
        for language in selected_languages:
            lang_code = get_language_code(language)
            column_name = f'Description - {lang_code}'
            if column_name not in input_df.columns:
                input_df[column_name] = ''

        for target_language in selected_languages:
            if target_language in completed_languages:
                logging.info(
                    f"Skipping already completed language: {target_language}")
                continue

            try:
                logging.info(f"Processing language: {target_language}")
                lang_code = get_language_code(target_language)
                column_name = f'Description - {lang_code}'

                batch_start = 0
                while batch_start < total_rows:
                    batch_end = min(batch_start + BATCH_SIZE, total_rows)
                    logging.info(
                        f"Processing batch {batch_start}-{batch_end} for {target_language}"
                    )

                    for index in range(batch_start, batch_end):
                        try:
                            if pd.isna(
                                    input_df.iloc[index][column_name]
                            ) or input_df.iloc[index][column_name] == "":
                                translated = translate_display_name(
                                    input_df.iloc[index]['Description'],
                                    target_language,
                                    dictionary=dictionary)
                                input_df.loc[index, column_name] = translated

                            progress = int((index + 1) / total_rows * 100)

                            yield json.dumps(
                                {
                                    "language": target_language,
                                    "progress": progress,
                                    "batch": f"{batch_start}-{batch_end}"
                                }) + "\n\n"

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

                # Save individual language file
                lang_filename = f"translated_descriptions_{target_language}.csv"
                lang_output_path = os.path.join(upload_folder, lang_filename)
                selected_columns = [
                    'Product ID', 'SKU', 'Description', column_name
                ]
                input_df[selected_columns].to_csv(lang_output_path,
                                                  index=False)

                completed_languages.add(target_language)
                completed_files.append({
                    "language": target_language,
                    "file": lang_filename
                })

                yield json.dumps({
                    "language": target_language,
                    "progress": 100,
                    "status": "complete",
                    "file": lang_filename
                }) + "\n\n"

            except Exception as e:
                error_msg = f"Error processing language {target_language}: {str(e)}"
                logging.error(error_msg)
                yield json.dumps({
                    "error": error_msg,
                    "language": target_language
                }) + "\n\n"
                continue

        # Save final combined file
        output_filename = "translated_descriptions_all.csv"
        output_file = os.path.join(upload_folder, output_filename)
        selected_columns = ['Product ID', 'SKU', 'Description'] + [
            f'Description - {get_language_code(lang)}'
            for lang in completed_languages
        ]

        input_df[selected_columns].to_csv(output_file, index=False)
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
