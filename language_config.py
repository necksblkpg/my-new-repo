import json
import os
from threading import Lock
from functools import lru_cache

CONFIG_FILE = 'language_config.json'
config_lock = Lock()

@lru_cache(maxsize=None)
def load_language_config():
    with config_lock:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}  # Return an empty dictionary if no config file exists

def get_language_mapping():
    return load_language_config()

def get_reverse_mapping():
    return {v: k for k, v in get_language_mapping().items()}

def get_available_languages(df):
    language_mapping = get_language_mapping()
    available_langs = [language_mapping[col.split(' - ')[1]] 
                       for col in df.columns 
                       if ' - ' in col and col.split(' - ')[1] in language_mapping]
    print(f"Available languages found: {available_langs}")
    return available_langs

def get_language_code(language_name):
    return get_reverse_mapping().get(language_name)

def save_language_config(new_config):
    with config_lock:
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(new_config, f, indent=2)
            load_language_config.cache_clear()
            print(f"Language config saved successfully: {new_config}")
        except Exception as e:
            print(f"Error saving language config: {str(e)}")
            raise Exception(f"Failed to save language config: {str(e)}")