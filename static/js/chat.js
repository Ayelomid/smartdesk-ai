// SmartDesk AI — Chat Interface JS

const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');

function getTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function appendMessage(text, sender, extra) {
    const wrap = document.createElement('div');
    wrap.className = `chat-bubble ${sender}`;

    const avatarHTML = sender === 'bot'
        ? `<div class="bubble-avatar bot-bubble-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg></div>`
        : `<div class="bubble-avatar user-bubble-avatar">U</div>`;

    wrap.innerHTML = `
        <div class="bubble-row">
            ${avatarHTML}
            <div class="bubble-text">${escapeHTML(text)}</div>
        </div>
        <span class="bubble-time">${getTime()}</span>
    `;

    if (extra && extra.escalate) {
        const notice = document.createElement('div');
        notice.className = 'escalation-notice';
        notice.innerHTML = `⚠ This has been escalated to an IT agent${extra.ticket_id ? ` — Ticket #${extra.ticket_id}` : ''}.`;
        wrap.appendChild(notice);
    }

    if (sender === 'bot' && extra && extra.intent) {
        const analysis = document.createElement('div');
        analysis.className = 'ai-analysis';
        const confidence = Math.round((extra.confidence || 0) * 100);
        analysis.innerHTML = `
            <div><span>Intent detected</span><strong>${escapeHTML(extra.intent.replaceAll('_', ' '))}</strong></div>
            <div><span>Category</span><strong>${escapeHTML(extra.category || 'General')}</strong></div>
            <div><span>Confidence</span><strong class="confidence-value">${confidence}%</strong></div>
            <div><span>Priority</span><strong>${escapeHTML(extra.priority || 'Medium')}</strong></div>`;
        wrap.appendChild(analysis);
    }

    chatMessages.appendChild(wrap);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTyping() {
    const el = document.createElement('div');
    el.className = 'chat-bubble bot';
    el.id = 'typingIndicator';
    el.innerHTML = `
        <div class="bubble-row">
            <div class="bubble-avatar bot-bubble-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg></div>
            <div class="bubble-text"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>
        </div>`;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTyping() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

function escapeHTML(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';
    sendBtn.disabled = true;
    appendMessage(text, 'user');
    showTyping();

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content },
            body: JSON.stringify({ message: text })
        });
        const data = await res.json();
        removeTyping();
        appendMessage(data.response, 'bot', data);
    } catch (err) {
        removeTyping();
        appendMessage("Sorry, I'm having trouble connecting. Please try again.", 'bot');
    } finally {
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

function sendQuickReply(text) {
    chatInput.value = text;
    sendMessage();
}

// Send on Enter
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Bot greeting on load
window.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        appendMessage("👋 Hello! I'm SmartDesk AI, your IT support assistant. How can I help you today? You can ask about password resets, network issues, software installs, or any other IT problems.", 'bot');
    }, 300);
});
