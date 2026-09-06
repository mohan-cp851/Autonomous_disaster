const chatForm = document.getElementById('copilot-form');
const chatInput = document.getElementById('copilot-input');
const chatLogs = document.getElementById('chat-logs-container');

function appendMessage(sender, text, isUser = false) {
    const avatar = isUser ? 'ME' : 'AI';
    const bgClass = isUser ? 'bg-info bg-opacity-10' : 'bg-white border';
    const alignClass = isUser ? 'justify-content-end' : '';
    const flexDir = isUser ? 'flex-row-reverse' : '';
    const margin = isUser ? 'ms-5' : 'me-5';
    
    // Convert newlines in bots markdown back to simple HTML breaks for fallbacks
    const formattedText = text.replace(/\n/g, '<br>');

    const chatHtml = `
        <div class="d-flex align-items-start mb-3 ${alignClass} ${flexDir}">
            <div class="avatar bg-info text-dark rounded-circle d-flex align-items-center justify-content-center fw-bold ${isUser ? 'ms-2' : 'me-2'}" style="width:32px; height:32px;">
                ${avatar}
            </div>
            <div class="p-3 rounded shadow-sm ${bgClass} ${margin}" style="max-width: 80%;">
                <div class="fw-bold small mb-1">${sender}</div>
                <div class="small m-0 text-dark" style="line-height:1.4;">${formattedText}</div>
            </div>
        </div>
    `;
    
    chatLogs.insertAdjacentHTML('beforeend', chatHtml);
    chatLogs.scrollTop = chatLogs.scrollHeight;
}

chatForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const val = chatInput.value.trim();
    if (!val) return;
    
    appendMessage('You', val, true);
    chatInput.value = '';
    
    // Add temporary loading indicator
    const loadingId = 'bot-loading-' + Date.now();
    const loadingHtml = `
        <div class="d-flex align-items-start mb-3" id="${loadingId}">
            <div class="avatar bg-info text-dark rounded-circle d-flex align-items-center justify-content-center fw-bold me-2" style="width:32px; height:32px;">
                AI
            </div>
            <div class="p-3 bg-white border rounded shadow-sm" style="max-width: 80%;">
                <span class="spinner-grow spinner-grow-sm text-info" role="status" aria-hidden="true"></span>
                <span class="small ms-2 text-muted">Retrieving NDMA protocol...</span>
            </div>
        </div>
    `;
    chatLogs.insertAdjacentHTML('beforeend', loadingHtml);
    chatLogs.scrollTop = chatLogs.scrollHeight;

    fetch('/api/copilot/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ query: val })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById(loadingId).remove();
        if (data.response) {
            appendMessage('Response Copilot', data.response);
        } else {
            appendMessage('Response Copilot', 'Error: Failed to fetch advisor guidelines.');
        }
    })
    .catch(() => {
        document.getElementById(loadingId).remove();
        appendMessage('Response Copilot', 'Error: Offline copilot network disconnected.');
    });
});

function sendSuggestion(text) {
    chatInput.value = text;
    chatForm.dispatchEvent(new Event('submit'));
}
