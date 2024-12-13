# main.py

from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, Response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from translate_display_names import translate_display_names_function
from translate_descriptions import translate_descriptions_function
import os
import pandas as pd
from flask_wtf.csrf import CSRFProtect
import json
from language_config import load_language_config, save_language_config
from functools import wraps
from datetime import timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max filstorlek
app.secret_key = os.urandom(24)  # För sessionshantering
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)  # 4 timmar
app.config['SESSION_PERMANENT'] = True
csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {'csv'}

users = {
    "admin": generate_password_hash("@admin!123@")
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username in users and check_password_hash(users[username], password):
            session['user'] = username
            session.permanent = True
            return redirect(url_for('index'))
        return render_template('login.html', error="Ogiltiga inloggningsuppgifter")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('dashboard.html')

@app.route('/translate_v1')
@login_required
def translate_v1():
    languages = load_language_config()
    return render_template('index.html', version=1, languages=languages)

@app.route('/translate_descriptions_page')
@login_required
def translate_descriptions_page():
    languages = load_language_config()
    return render_template('product_descriptions.html', version=2, languages=languages)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'input_file' not in request.files:
        return jsonify({'error': 'Input file must be uploaded'}), 400

    input_file = request.files['input_file']
    examples_file = request.files.get('examples_file')
    # dictionary_file tas ej längre i bruk
    dictionary_file = request.files.get('dictionary_file')  # Finns kvar men används ej
    selected_languages = request.form.getlist('languages')
    version = request.form.get('version', '1')
    user_prompt = request.form.get('user_prompt', '')

    if input_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(input_file.filename):
        return jsonify({'error': 'Only CSV files are allowed'}), 400

    # För version 1 krävs examples_file
    if version == '1' and (not examples_file or examples_file.filename == ''):
        return jsonify({'error': 'Examples file must be uploaded for version 1'}), 400

    if input_file and selected_languages:
        input_filename = secure_filename(input_file.filename)
        input_file.save(os.path.join(app.config['UPLOAD_FOLDER'], input_filename))

        session['input_file'] = input_filename
        session['languages'] = selected_languages
        session['version'] = version
        session['user_prompt'] = user_prompt.strip()

        if examples_file:
            examples_filename = secure_filename(examples_file.filename)
            examples_file.save(os.path.join(app.config['UPLOAD_FOLDER'], examples_filename))
            session['examples_file'] = examples_filename

        # dictionary_file ignoreras men vi sparar ändå om du vill återanvända kod
        if dictionary_file:
            dictionary_filename = secure_filename(dictionary_file.filename)
            dictionary_file.save(os.path.join(app.config['UPLOAD_FOLDER'], dictionary_filename))
            session['dictionary_file'] = dictionary_filename
        else:
            session.pop('dictionary_file', None)

        action = request.form.get('action')
        if action == 'translate_descriptions':
            if version == '2':
                return jsonify({'redirect': url_for('translate_descriptions')})
            return jsonify({'redirect': url_for('translate_display_names')})
        elif action == 'translate_titles':
            return jsonify({'redirect': url_for('translate_display_names')})
        else:
            return jsonify({'error': 'Invalid action'}), 400

    return jsonify({'error': 'Invalid request'}), 400

@app.route('/translate_display_names')
@login_required
def translate_display_names():
    input_file = session.get('input_file')
    examples_file = session.get('examples_file')
    selected_languages = session.get('languages')

    if not input_file or not examples_file or not selected_languages:
        return jsonify({'error': 'Filer eller språk saknas'}), 400

    def generate():
        for message in translate_display_names_function(app.config['UPLOAD_FOLDER'], 
                                                        input_file, 
                                                        examples_file, 
                                                        selected_languages):
            yield f"data: {message}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/translate_descriptions')
@login_required
def translate_descriptions():
    input_file = session.get('input_file')
    selected_languages = session.get('languages')
    # dictionary_file ignoreras men lämnas kvar i signaturen
    dictionary_file = session.get('dictionary_file', None)

    if not input_file or not selected_languages:
        return jsonify({'error': 'Fil eller språk saknas'}), 400

    def generate():
        for message in translate_descriptions_function(app.config['UPLOAD_FOLDER'], 
                                                       input_file,
                                                       dictionary_file,
                                                       selected_languages):
            yield f"data: {message}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    safe_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(safe_path) and os.path.isfile(safe_path):
        return send_file(safe_path, as_attachment=True)
    else:
        return jsonify({'error': 'Fil hittades inte'}), 404

@app.route('/upload_examples', methods=['POST'])
@login_required
def upload_examples():
    if 'examples_file' not in request.files:
        return jsonify({'error': 'Ingen fil vald'}), 400
    file = request.files['examples_file']
    if file.filename == '':
        return jsonify({'error': 'Ingen fil vald'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        try:
            df = pd.read_csv(file_path)
            # get_available_languages används ej längre, men kan finnas kvar om så önskas
            # Du kan behålla logik här om du vill fortsätta använda denna funktionalitet
            language_mapping = load_language_config()
            available_langs = []
            for col in df.columns:
                if ' - ' in col:
                    code = col.split(' - ')[1]
                    if code in language_mapping:
                        available_langs.append(language_mapping[code])

        except Exception as e:
            return jsonify({'error': f'Fel vid bearbetning av fil: {str(e)}'}), 500
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

        return jsonify({'available_languages': available_langs})
    return jsonify({'error': 'Filuppladdning misslyckades'}), 500

@app.route('/language_config')
@login_required
def show_language_config():
    languages = load_language_config()
    return render_template('language_config.html', languages=languages)

@app.route('/update_language_config', methods=['POST'])
@login_required
def update_language_config():
    try:
        new_config = request.json
        save_language_config(new_config)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/instructions')
@login_required
def instructions():
    return render_template('instructions.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
