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
    const selectedLanguages = Array.from(document.querySelectorAll('input[name="languages"]:checked')).map(el => el.value);

    const translateBtn = document.getElementById('translateDisplayNames');

    if (inputFile && selectedLanguages.length > 0) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const content = e.target.result;
            const hasDescription = content.includes('Description');

            translateBtn.classList.toggle('disabled', !hasDescription);
            translateBtn.disabled = !hasDescription;
        };
        reader.readAsText(inputFile);
    } else {
        translateBtn.classList.add('disabled');
        translateBtn.disabled = true;
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

function initializeEventSource() {
    $('#progress-container').show();

    // Behåll bara progress bars för icke-färdiga språk
    const existingBars = $('#progress-bars .progress-group').filter(function() {
        const language = $(this).find('label').text();
        return !completedLanguages.has(language);
    });

    $('#progress-bars').html('').append(existingBars);
    createDownloadList();

    const eventSource = new EventSource('/translate_descriptions');

    eventSource.onmessage = function(event) {
        try {
            var data = JSON.parse(event.data);

            if (data.error) {
                console.error('Translation error:', data.error);
                showToast('Error: ' + data.error);
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

                if (data.status === "complete" && data.file) {
                    progressBar.css('width', '100%')
                             .addClass('bg-success')
                             .text('Complete');

                    // Add to download list and mark as completed
                    addToDownloadList(data.language, data.file);
                } else if (typeof data.progress === 'number') {
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
        eventSource.close();
        showToast('Connection lost. Please try again.');
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

    $('#language-checkboxes').on('change', 'input[type="checkbox"]', updateButtonStates);

    $('#uploadForm').submit(function(e) {
        e.preventDefault();
        setAction('translate_descriptions');
        var formData = new FormData(this);

        // Hämta custom prompt från textarea
        const userPrompt = document.getElementById('user_prompt').value;
        formData.append('user_prompt', userPrompt);

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
                    initializeEventSource();
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

    // Input file preview
    document.getElementById('input_file').addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const preview = document.getElementById('input-file-preview');
                const lines = e.target.result.split('\n').slice(0, 5);
                preview.innerHTML = '<strong>Preview:</strong><br>' + lines.join('<br>');
            };
            reader.readAsText(file);
        }
    });
});
