# translate_display_names.py

from language_config import get_language_mapping, get_reverse_mapping, get_language_code
import pandas as pd
from openai import OpenAI
import os
import json
import sys
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
from time import sleep

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def load_translation_examples(examples_df, target_language):
    target_code = get_language_code(target_language)
    target_column = f'Display name - {target_code}'

    if target_column in examples_df.columns:
        examples = examples_df[['Display Name', target_column]].dropna().head(21)
        if not examples.empty:
            example_text = "\n".join([
                f"Original: {row['Display Name']} -> Translated: {row[target_column]}"
                for _, row in examples.iterrows()
            ])
            return example_text, True
    return "", False

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def translate_display_name(text, target_language, examples, has_language_examples):
    if pd.isna(text) or not text.strip():
        return ""

    if has_language_examples:
        prompt = (
            f"Here are examples of how display names have been translated to {target_language}:\n{examples}\n\n"
            f"Original display name: '{text}'. Translate the display name to {target_language} according to the examples above. "
            f"Only the translation, without extra information."
        )
    else:
        return "No examples available"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {
                    "role": "system",
                    "content": f"You are a translator for an e-commerce store specializing in men's accessories like ties. Use the examples to translate the display names correctly to {target_language}."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            timeout=1200
        )

        translated_text = response.choices[0].message.content.strip().strip('"').strip("'")
        return translated_text
    except Exception as e:
        logging.error(f"Error during translation of '{text}' to {target_language}: {e}")
        raise

def translate_display_names_function(upload_folder, input_file, examples_file, selected_languages):
    BATCH_SIZE = 50
    completed_languages = set()
    completed_files = []  # Track completed files for download

    try:
        logging.info(f"Starting translation process for languages: {selected_languages}")
        input_csv = os.path.join(upload_folder, input_file)
        examples_csv = os.path.join(upload_folder, examples_file)

        input_df = pd.read_csv(input_csv, sep=',', dtype={'SKU': str})
        examples_df = pd.read_csv(examples_csv, sep=',', dtype={'Display Name': str})
        total_rows = len(input_df)

        # Create columns for all selected languages
        for language in selected_languages:
            lang_code = get_language_code(language)
            column_name = f'Display name - {lang_code}'
            if column_name not in input_df.columns:
                input_df[column_name] = ''

        for target_language in selected_languages:
            if target_language in completed_languages:
                logging.info(f"Skipping already completed language: {target_language}")
                continue

            try:
                logging.info(f"Processing language: {target_language}")
                examples, has_examples = load_translation_examples(examples_df, target_language)

                if not has_examples:
                    logging.warning(f"No examples found for language: {target_language}")
                    yield json.dumps({"language": target_language, "progress": "no_examples"}) + "\n\n"
                    continue

                lang_code = get_language_code(target_language)
                column_name = f'Display name - {lang_code}'

                batch_start = 0
                while batch_start < total_rows:
                    batch_end = min(batch_start + BATCH_SIZE, total_rows)
                    logging.info(f"Processing batch {batch_start}-{batch_end} for {target_language}")

                    for index in range(batch_start, batch_end):
                        try:
                            if pd.isna(input_df.iloc[index][column_name]) or input_df.iloc[index][column_name] == "":
                                translated = translate_display_name(
                                    input_df.iloc[index]['Display Name'],
                                    target_language,
                                    examples,
                                    has_examples
                                )
                                input_df.loc[index, column_name] = translated

                            progress = int((index + 1) / total_rows * 100)

                            yield json.dumps({
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
                lang_filename = f"translated_display_names_{target_language}.csv"
                lang_output_path = os.path.join(upload_folder, lang_filename)
                selected_columns = ['Product ID', 'SKU', 'Display Name', column_name]
                input_df[selected_columns].to_csv(lang_output_path, index=False)

                completed_languages.add(target_language)
                completed_files.append({
                    "language": target_language,
                    "file": lang_filename
                })

                yield json.dumps({
                    "language": target_language, 
                    "progress": 100,
                    "status": "complete",
                    "file": lang_filename,
                    "completed_files": completed_files  # Include list of completed files
                }) + "\n\n"

            except Exception as e:
                error_msg = f"Error processing language {target_language}: {str(e)}"
                logging.error(error_msg)
                yield json.dumps({"error": error_msg, "language": target_language}) + "\n\n"
                continue

        # Save final combined file
        output_filename = "translated_display_names_all.csv"
        output_file = os.path.join(upload_folder, output_filename)
        selected_columns = ['Product ID', 'SKU', 'Display Name'] + [
            f'Display name - {get_language_code(lang)}' 
            for lang in completed_languages
        ]

        input_df[selected_columns].to_csv(output_file, index=False)
        yield json.dumps({
            "complete": True,
            "file": output_filename,
            "completed_files": completed_files,  # Include all completed files
            "completed_languages": list(completed_languages)
        }) + "\n\n"

    except Exception as e:
        error_msg = f"Fatal error in translation process: {str(e)}"
        logging.error(error_msg)
        yield json.dumps({"error": error_msg}) + "\n\n"