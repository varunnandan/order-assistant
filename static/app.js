document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const newChatBtn = document.getElementById('new-chat-btn');
    const chatWindow = document.getElementById('chat-window');
    const messagesList = document.getElementById('messages-list');
    const emptyState = document.getElementById('empty-state');
    const loadingIndicator = document.getElementById('loading-indicator');
    const errorBanner = document.getElementById('error-banner');
    const errorMessage = document.getElementById('error-message');
    const retryBtn = document.getElementById('retry-btn');
    const dismissErrorBtn = document.getElementById('dismiss-error-btn');
    const charCounter = document.getElementById('char-counter');

    let conversationHistory = [];
    let lastUserMessage = '';

    // Auto-adjust textarea height
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
        updateCharCounter();
    });

    // Enter to submit, Shift+Enter for newline
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (userInput.value.trim() && !sendBtn.disabled) {
                chatForm.dispatchEvent(new Event('submit'));
            }
        }
    });

    function updateCharCounter() {
        const len = userInput.value.length;
        charCounter.textContent = `${len} / 1000`;
        charCounter.classList.remove('warning', 'exceeded');
        if (len > 1000) {
            charCounter.classList.add('exceeded');
            sendBtn.disabled = true;
        } else if (len > 900) {
            charCounter.classList.add('warning');
            sendBtn.disabled = false;
        } else {
            sendBtn.disabled = false;
        }
    }

    // Handle Example Chips
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const question = chip.getAttribute('data-question');
            if (question) {
                userInput.value = question;
                userInput.style.height = 'auto';
                updateCharCounter();
                sendMessage(question);
            }
        });
    });

    // Handle Form Submit
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = userInput.value.trim();
        if (!text || text.length > 1000) return;
        sendMessage(text);
    });

    // Retry Button
    retryBtn.addEventListener('click', () => {
        hideError();
        if (lastUserMessage) {
            sendApiRequest(lastUserMessage);
        }
    });

    dismissErrorBtn.addEventListener('click', hideError);

    // New Chat Button
    newChatBtn.addEventListener('click', () => {
        conversationHistory = [];
        messagesList.innerHTML = '';
        emptyState.style.display = 'flex';
        hideError();
        userInput.value = '';
        userInput.style.height = 'auto';
        updateCharCounter();
    });

    async function sendMessage(text) {
        lastUserMessage = text;
        hideError();
        
        // Hide empty state
        emptyState.style.display = 'none';

        // Render User Message
        appendMessage('user', text);
        userInput.value = '';
        userInput.style.height = 'auto';
        updateCharCounter();

        await sendApiRequest(text);
    }

    async function sendApiRequest(text) {
        setLoading(true);

        try {
            const payload = {
                message: text,
                history: conversationHistory.slice(-10) // send recent 10 turns
            };

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok) {
                const errMsg = data.error || `Server returned error (${response.status})`;
                showError(errMsg, response.status);
                setLoading(false);
                return;
            }

            // Success response
            const reply = data.reply || 'No response received.';
            const toolCalls = data.tool_calls || [];

            // Add to conversation history
            conversationHistory.push({ role: 'user', content: text });
            conversationHistory.push({ role: 'assistant', content: reply });

            // Render Assistant Message with Tool Steps
            appendMessage('assistant', reply, toolCalls);

        } catch (err) {
            console.error('Fetch error:', err);
            showError('Network error: Unable to connect to the server. Please check your network connection and retry.');
        } finally {
            setLoading(false);
        }
    }

    function appendMessage(role, text, toolCalls = []) {
        const row = document.createElement('div');
        row.className = `message-row ${role}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.innerHTML = formatMarkdown(text);

        row.appendChild(bubble);

        // Render Tool Steps Panel for assistant
        if (role === 'assistant' && toolCalls && toolCalls.length > 0) {
            const stepsContainer = document.createElement('div');
            stepsContainer.className = 'tool-steps-container';

            const header = document.createElement('div');
            header.className = 'tool-steps-header';
            header.innerHTML = `
                <span>🛠️ Tool Execution Steps (${toolCalls.length})</span>
                <span class="toggle-icon">▼</span>
            `;

            const body = document.createElement('div');
            body.className = 'tool-steps-body hidden';

            toolCalls.forEach(tc => {
                const item = document.createElement('div');
                item.className = `tool-step-item ${tc.ok ? 'success' : 'failure'}`;

                const statusSymbol = tc.ok ? '✅' : '❌';
                item.innerHTML = `
                    <div class="tool-step-title">
                        <span>${statusSymbol} <code>${escapeHtml(tc.name)}</code></span>
                        <span>${tc.ok ? 'OK' : 'Failed'}</span>
                    </div>
                    <div class="tool-step-summary">${escapeHtml(tc.summary)}</div>
                    <pre class="tool-args-pre">${escapeHtml(JSON.stringify(tc.arguments, null, 2))}</pre>
                `;
                body.appendChild(item);
            });

            header.addEventListener('click', () => {
                const isHidden = body.classList.toggle('hidden');
                header.querySelector('.toggle-icon').textContent = isHidden ? '▼' : '▲';
            });

            stepsContainer.appendChild(header);
            stepsContainer.appendChild(body);
            row.appendChild(stepsContainer);
        }

        messagesList.appendChild(row);
        scrollToBottom();
    }

    function setLoading(isLoading) {
        if (isLoading) {
            loadingIndicator.classList.remove('hidden');
            sendBtn.disabled = true;
            userInput.disabled = true;
        } else {
            loadingIndicator.classList.add('hidden');
            sendBtn.disabled = false;
            userInput.disabled = false;
            userInput.focus();
        }
        scrollToBottom();
    }

    function showError(message, statusCode) {
        let displayMsg = message;
        if (statusCode === 429) {
            displayMsg = `Rate Limited (429): ${message}`;
        } else if (statusCode === 503) {
            displayMsg = `Service Unavailable (503): ${message}`;
        }
        errorMessage.textContent = displayMsg;
        errorBanner.classList.remove('hidden');
    }

    function hideError() {
        errorBanner.classList.add('hidden');
    }

    function scrollToBottom() {
        setTimeout(() => {
            chatWindow.scrollTop = chatWindow.scrollHeight;
        }, 50);
    }

    function formatMarkdown(text) {
        if (!text) return '';
        let escaped = escapeHtml(text);
        
        // Bold: **text**
        escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Code: `code`
        escaped = escaped.replace(/`(.*?)`/g, '<code>$1</code>');
        
        // Lines into paragraphs / lists
        const lines = escaped.split('\n');
        let html = '';
        let inList = false;

        lines.forEach(line => {
            const trimmed = line.trim();
            if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                if (!inList) {
                    html += '<ul>';
                    inList = true;
                }
                html += `<li>${trimmed.substring(2)}</li>`;
            } else {
                if (inList) {
                    html += '</ul>';
                    inList = false;
                }
                if (trimmed) {
                    html += `<p>${line}</p>`;
                }
            }
        });

        if (inList) html += '</ul>';
        return html;
    }

    function escapeHtml(str) {
        if (typeof str !== 'string') return '';
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});
