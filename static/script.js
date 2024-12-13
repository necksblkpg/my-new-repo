function setAction(action) {
    document.getElementById('action').value = action;
}

// Håll koll på färdiga språk
let completedLanguages = new Set();

function showToast(message, isDownloadLink = false) {
    const toast = document.getElementById('toast');
    if (isDownloadLink) {
        toast.classList.add('download-toast');
    }
    toast.innerHTML = message + '<button class="close-btn">&times;</button>';
    toast.classList.add('show');
}

function hideToast() {
    const toast = document.getElementById('toast');
    toast.classList.remove('show');
    toast.classList.remove('download-toast');
}

function showLoading() {
    document.getElementById('loading-overlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loading-overlay').style.display = 'none';
}

function updateButtonStates() {
    const inputFile = document.querySelector('input[name="input_file"]').files[0];
    const examplesFile = document.querySelector('input[name="examples_file"]').files[0];
    const selectedLanguages = Array.from(document.querySelectorAll('input[name="languages"]:checked')).map(el => el.value);

    const displayNameBtn = document.getElementById('translateDisplayNames');

    if (inputFile && examplesFile && selectedLanguages.length > 0) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const content = e.target.result;
            const hasDisplayName = content.includes('Display Name');

            displayNameBtn.classList.toggle('disabled', !hasDisplayName);
            displayNameBtn.disabled = !hasDisplayName;
        };
        reader.readAsText(inputFile);
    } else {
        displayNameBtn.classList.add('disabled');
        displayNameBtn.disabled = true;
    }
}

function createDownloadList() {
    if (!$('#download-list').length) {
        $('#progress-container').append(`
            <div id="download-list" class="download-list">
                <h3>Completed Translations</h3>
                <ul></ul>
            </div>
        `);
    }
}

function addToDownloadList(language, filename) {
    if (!completedLanguages.has(language)) {
        createDownloadList();
        $('#download-list ul').append(`
            <li>
                <span>${language}</span>
                <a href="/download/${filename}" download class="download-link">Download ${language} translations</a>
            </li>
        `);
        completedLanguages.add(language);
    }
}

function previewFile(file, previewElementId) {
    const reader = new FileReader();
    reader.onload = function(e) {
        const content = e.target.result;
        const lines = content.split('\n');
        const preview = lines.slice(0, 5).join('\n');
        document.getElementById(previewElementId).textContent = preview;
    };
    reader.readAsText(file);
}

function startSSE(url) {
    $('#progress-container').show();

    // Behåll bara progress bars för icke-färdiga språk
    const existingBars = $('#progress-bars .progress-group').filter(function() {
        const language = $(this).find('label').text();
        return !completedLanguages.has(language);
    });

    $('#progress-bars').html('').append(existingBars);
    createDownloadList();

    var eventSource = new EventSource(url);
    var reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 3;

    eventSource.onmessage = function(event) {
        try {
            var data = JSON.parse(event.data);

            if (data.error) {
                console.error('Translation error:', data.error);
                showToast('Error: ' + data.error);

                if (data.language) {
                    $('#progress-bar-' + sanitizeLanguage(data.language))
                        .css('width', '100%')
                        .addClass('bg-danger')
                        .text('Error');
                }
                return;
            }

            if (data.language && data.progress !== undefined) {
                // Skip if language is already completed
                if (completedLanguages.has(data.language)) {
                    return;
                }

                if (!$('#progress-bar-' + sanitizeLanguage(data.language)).length) {
                    $('#progress-bars').append(`
                        <div class="progress-group">
                            <label>${data.language}</label>
                            <div class="progress">
                                <div id="progress-bar-${sanitizeLanguage(data.language)}" 
                                     class="progress-bar" 
                                     role="progressbar" 
                                     style="width: 0%;" 
                                     aria-valuenow="0" 
                                     aria-valuemin="0" 
                                     aria-valuemax="100">0%</div>
                            </div>
                        </div>
                    `);
                }

                const progressBar = $('#progress-bar-' + sanitizeLanguage(data.language));

                if (data.progress === "skipped") {
                    progressBar.css('width', '100%')
                               .addClass('bg-warning')
                               .text('Skipped');
                    completedLanguages.add(data.language);
                } else if (data.progress === "no_examples") {
                    progressBar.css('width', '100%')
                               .addClass('bg-danger')
                               .text('No Examples');
                    completedLanguages.add(data.language);
                } else if (data.status === "complete" && data.file) {
                    progressBar.css('width', '100%')
                               .addClass('bg-success')
                               .text('Complete');

                    // Add to download list and mark as completed
                    addToDownloadList(data.language, data.file);
                } else {
                    progressBar.css('width', data.progress + '%')
                               .attr('aria-valuenow', data.progress)
                               .text(data.progress + '%');
                }
            }

            if (data.complete && data.file) {
                // Show final success message with all download links
                let message = 'All translations complete!';
                message += `<br><a href="/download/${data.file}" download>Download combined translations</a>`;
                showToast(message, true);

                // Automatically trigger the download of the combined file
                window.location.href = '/download/' + data.file;
                eventSource.close();
            }
        } catch (e) {
            console.error('Error parsing message:', e);
        }
    };

    eventSource.onerror = function(err) {
        console.error('SSE error:', err);
        reconnectAttempts++;

        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            eventSource.close();
            $('#progress-bars').append('<p class="error-message">Connection lost. Please refresh the page to continue from where you left off.</p>');
            showToast('Connection lost. Your progress has been saved.');
        }
    };
}

function sanitizeLanguage(lang) {
    return lang.replace(/\s+/g, '_').toLowerCase();
}

function showExample(type) {
    document.getElementById('overlay').style.display = 'block';
    document.getElementById(`${type}-example`).style.display = 'block';
}

function hideExample(type) {
    document.getElementById('overlay').style.display = 'none';
    document.getElementById(`${type}-example`).style.display = 'none';
}

// Stäng popup när man klickar utanför
document.getElementById('overlay').addEventListener('click', function() {
    document.querySelectorAll('.example-popup').forEach(popup => {
        popup.style.display = 'none';
    });
    this.style.display = 'none';
});

$(document).ready(function() {
    // Reset completed languages on page load
    completedLanguages.clear();

    $('input[name="input_file"]').change(function() {
        updateButtonStates();
        if (this.files[0]) {
            previewFile(this.files[0], 'input-file-preview');
        }
    });

    $('#examples_file').change(function() {
        if (this.files[0]) {
            previewFile(this.files[0], 'examples-file-preview');
        }

        var formData = new FormData();
        formData.append('examples_file', this.files[0]);
        formData.append('csrf_token', $('input[name=csrf_token]').val());

        $.ajax({
            url: '/upload_examples',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(response) {
                var languageCheckboxes = $('#language-checkboxes');
                languageCheckboxes.empty();
                if (response.available_languages && response.available_languages.length > 0) {
                    response.available_languages.forEach(function(lang) {
                        languageCheckboxes.append(`
                            <div class="checkbox-item">
                                <input type="checkbox" id="${lang}" name="languages" value="${lang}">
                                <label for="${lang}">${lang}</label>
                            </div>
                        `);
                    });
                    $('#language-options').show();
                    showToast('Examples file uploaded successfully');
                } else {
                    $('#language-options').hide();
                    showToast('No languages with examples found in the uploaded file');
                }
                updateButtonStates();
            },
            error: function(xhr, status, error) {
                showToast('Error uploading examples file: ' + error);
            }
        });
    });

    $('#language-checkboxes').on('change', 'input[type="checkbox"]', updateButtonStates);

    $('#uploadForm').submit(function(e) {
        e.preventDefault();
        var formData = new FormData(this);
        formData.append('action', 'translate_titles');

        const selectedLanguages = Array.from(document.querySelectorAll('input[name="languages"]:checked'))
            .map(el => el.value);
        formData.append('languages', JSON.stringify(selectedLanguages));

        $.ajax({
            url: '/upload',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            beforeSend: function() {
                showLoading();
            },
            success: function(response) {
                hideLoading();
                if (response.redirect) {
                    startSSE(response.redirect);
                } else if (response.error) {
                    showToast('Error: ' + response.error);
                }
            },
            error: function(xhr, status, error) {
                hideLoading();
                showToast('Error during processing: ' + error);
            }
        });
    });

    $('#toast').on('click', '.close-btn', function() {
        hideToast();
    });
});