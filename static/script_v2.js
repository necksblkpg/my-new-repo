function setAction(action) {
    document.getElementById('action').value = action;
}

function updateButtonStates() {
    const inputFile = document.querySelector('input[name="input_file"]').files[0];
    const rewriteBtn = document.getElementById('rewriteDescriptions');

    if (inputFile) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const content = e.target.result;
            const hasDescription = content.includes('Description');
            rewriteBtn.classList.toggle('disabled', !hasDescription);
            rewriteBtn.disabled = !hasDescription;
        };
        reader.readAsText(inputFile);
    } else {
        rewriteBtn.classList.add('disabled');
        rewriteBtn.disabled = true;
    }
}

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

    const eventSource = new EventSource('/rewrite_descriptions_two_steps');

    eventSource.onmessage = function(event) {
        try {
            var data = JSON.parse(event.data);

            if (data.error) {
                console.error('Error:', data.error);
                showToast('Error: ' + data.error);
                return;
            }

            if (data.progress !== undefined) {
                let progressBar = $('#progress-bar-english');
                if (!progressBar.length) {
                    $('#progress-bars').html(`
                        <div class="progress-group">
                            <label>English (Rewritten)</label>
                            <div class="progress">
                                <div id="progress-bar-english" class="progress-bar" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">0%</div>
                            </div>
                        </div>
                    `);
                    progressBar = $('#progress-bar-english');
                }
                progressBar.css('width', data.progress + '%')
                           .attr('aria-valuenow', data.progress)
                           .text(data.progress + '%');
            }

            if (data.complete && data.file) {
                showToast('All rewriting complete!<br><a href="/download/' + data.file + '" download>Download rewritten descriptions</a>', true);
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

$(document).ready(function() {
    $('input[name="input_file"]').change(function() {
        updateButtonStates();
        if (this.files[0]) {
            previewFile(this.files[0], 'input-file-preview');
        }
    });

    $('#uploadForm').submit(function(e) {
        e.preventDefault();
        setAction('rewrite_descriptions_two_steps');
        var formData = new FormData(this);

        const systemPrompt1 = document.getElementById('system_prompt_1').value;
        const userPrompt1   = document.getElementById('user_prompt_1').value;
        const systemPrompt2 = document.getElementById('system_prompt_2').value;
        const userPrompt2   = document.getElementById('user_prompt_2').value;

        formData.append('system_prompt_1', systemPrompt1);
        formData.append('user_prompt_1', userPrompt1);
        formData.append('system_prompt_2', systemPrompt2);
        formData.append('user_prompt_2', userPrompt2);

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
});
