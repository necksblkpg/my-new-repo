# main.py

from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, Response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import pandas as pd
from flask_wtf.csrf import CSRFProtect
import json
from language_config import load_language_config, save_language_config
from functools import wraps
from datetime import timedelta
import sys

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)
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
    if input_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(input_file.filename):
        return jsonify({'error': 'Only CSV files are allowed'}), 400

    input_filename = secure_filename(input_file.filename)
    input_file.save(os.path.join(app.config['UPLOAD_FOLDER'], input_filename))

    session['input_file'] = input_filename

    # Hämta promptar
    system_prompt_1 = request.form.get('system_prompt_1', '').strip()
    user_prompt_1   = request.form.get('user_prompt_1', '').strip()
    system_prompt_2 = request.form.get('system_prompt_2', '').strip()
    user_prompt_2   = request.form.get('user_prompt_2', '').strip()

    session['system_prompt_1'] = system_prompt_1
    session['user_prompt_1']   = user_prompt_1
    session['system_prompt_2'] = system_prompt_2
    session['user_prompt_2']   = user_prompt_2

    action = request.form.get('action')
    if action == 'rewrite_descriptions_two_steps':
        return jsonify({'redirect': url_for('rewrite_descriptions_two_steps')})
    else:
        return jsonify({'error': 'Invalid action'}), 400

@app.route('/rewrite_descriptions_two_steps')
@login_required
def rewrite_descriptions_two_steps():
    from translate_descriptions import rewrite_descriptions_two_steps_function

    input_file = session.get('input_file')
    if not input_file:
        return jsonify({'error': 'File is missing'}), 400

    system_prompt_1 = session.get('system_prompt_1', '')
    user_prompt_1   = session.get('user_prompt_1', '')
    system_prompt_2 = session.get('system_prompt_2', '')
    user_prompt_2   = session.get('user_prompt_2', '')

    def generate():
        for message in rewrite_descriptions_two_steps_function(
            app.config['UPLOAD_FOLDER'],
            input_file,
            system_prompt_1,
            user_prompt_1,
            system_prompt_2,
            user_prompt_2
        ):
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
