const BASE = 'https://cccp-chatbot.agreeablecliff-8b7135c2.northeurope.azurecontainerapps.io';
marked.setOptions({ breaks: true, gfm: true });

let _userName = 'Guest';
let _userEmail = '';
let _accessToken = null; // Microsoft Graph token for SharePoint
let SID = localStorage.getItem('cccp_session') || crypto.randomUUID();
localStorage.setItem('cccp_session', SID);

// --- Microsoft Login (MSAL) ---
const MSAL_CONFIG = {
    clientId: 'ecbb8f92-f38d-480c-a400-40f3804e54ba',
    authority: 'https://login.microsoftonline.com/common',
    redirectUri: window.location.origin + '/',
    scopes: ['User.Read', 'Files.Read.All', 'Sites.Read.All'],
};

async function microsoftLogin() {
    if (!MSAL_CONFIG.clientId) {
        // No client ID configured — simulate login
        _userName = 'Demo Agent';
        _userEmail = 'agent@callcentre.com';
        SID = 'user-demo-agent';
        localStorage.setItem('cccp_session', SID);
        showApp();
        return;
    }
    // Real MSAL login would go here
    // For now, redirect to Microsoft login
    const authUrl = `${MSAL_CONFIG.authority}/oauth2/v2.0/authorize?` +
        `client_id=${MSAL_CONFIG.clientId}` +
        `&response_type=token` +
        `&redirect_uri=${encodeURIComponent(MSAL_CONFIG.redirectUri)}` +
        `&scope=${encodeURIComponent(MSAL_CONFIG.scopes.join(' '))}` +
        `&response_mode=fragment`;
    window.location.href = authUrl;
}

function guestLogin() {
    _userName = 'Guest Agent';
    _userEmail = '';
    showApp();
}

function showApp() {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('mainApp').style.display = 'flex';
    document.getElementById('userName').textContent = _userName;
    const avatar = document.getElementById('userAvatar');
    avatar.style.display = 'none';

    if (_accessToken) {
        document.getElementById('sharepointSection').style.display = 'block';
        loadSharePointFiles();
    }
}

// Check for token in URL hash (after Microsoft redirect)
function checkAuthRedirect() {
    const hash = window.location.hash;
    if (hash.includes('access_token=')) {
        const params = new URLSearchParams(hash.substring(1));
        _accessToken = params.get('access_token');
        // Get user info from Graph
        fetch('https://graph.microsoft.com/v1.0/me', {
            headers: { 'Authorization': `Bearer ${_accessToken}` }
        }).then(r => r.json()).then(user => {
            _userName = user.displayName || 'Agent';
            _userEmail = user.mail || user.userPrincipalName || '';
            SID = 'user-' + _userEmail.replace(/[^a-zA-Z0-9]/g, '-');
            localStorage.setItem('cccp_session', SID);
            showApp();
        }).catch(() => { showApp(); });
        window.location.hash = '';
    }
}

// --- SharePoint Files ---
async function loadSharePointFiles() {
    if (!_accessToken) return;
    const container = document.getElementById('sharepointFiles');
    try {
        const res = await fetch('https://graph.microsoft.com/v1.0/me/drive/root/children', {
            headers: { 'Authorization': `Bearer ${_accessToken}` }
        });
        const data = await res.json();
        if (data.value && data.value.length > 0) {
            container.innerHTML = data.value.slice(0, 8).map(f =>
                `<div class="sp-file">📄 ${f.name}</div>`
            ).join('');
        } else {
            container.innerHTML = '<span class="sp-loading">No files found</span>';
        }
    } catch (e) {
        container.innerHTML = '<span class="sp-loading">Access denied</span>';
    }
}

// --- Chat ---
const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('input');

function askQuestion(q) {
    inputEl.value = q;
    send();
}

function hl(agents) {
    document.querySelectorAll('.agent-item').forEach(e => e.classList.remove('active', 'generating'));
    if (!agents) return;
    const list = Array.isArray(agents) ? agents : [agents];
    list.forEach(n => {
        const e = document.querySelector(`.agent-item[data-agent="${n}"]`);
        if (e) { e.classList.add('active', 'generating'); }
    });
}

function scrollBottom() { chatEl.scrollTop = chatEl.scrollHeight; }

async function send() {
    const q = inputEl.value.trim();
    if (!q) return;
    inputEl.value = '';

    // User message
    const userMsg = document.createElement('div');
    userMsg.className = 'message user';
    userMsg.innerHTML = `<div class="msg-avatar">${_userName[0]}</div><div class="bubble">${q}</div>`;
    chatEl.appendChild(userMsg);
    scrollBottom();

    // AI response bubble
    const msg = document.createElement('div');
    msg.className = 'message assistant';
    const bub = document.createElement('div');
    bub.className = 'bubble';
    bub.innerHTML = '<span class="typing">Thinking...</span>';
    msg.innerHTML = '<div class="msg-avatar">AI</div>';
    msg.appendChild(bub);
    chatEl.appendChild(msg);
    scrollBottom();

    hl('router');

    try {
        const res = await fetch(BASE + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q, session_id: SID, user_name: _userName }),
        });

        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        let routes = [];
        let responseText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop();
            let ev = '';

            for (const ln of lines) {
                if (ln.startsWith('event: ')) { ev = ln.slice(7).trim(); }
                else if (ln.startsWith('data: ') && ev) {
                    try {
                        const d = JSON.parse(ln.slice(6));

                        if (ev === 'routing') {
                            routes = d.agents || [];
                            hl(routes);
                            const badges = routes.map(r => `<span class="routing-badge">🤖 ${r}</span>`).join('');
                            bub.innerHTML = badges + '<br><span class="typing">Processing...</span>';
                            scrollBottom();
                        }
                        else if (ev === 'agent_response') {
                            const agentEl = document.querySelector(`.agent-item[data-agent="${d.agent}"]`);
                            if (agentEl) agentEl.classList.remove('generating');
                            responseText = d.text;
                        }
                        else if (ev === 'response') {
                            responseText = d.text || responseText;
                            const badges = routes.map(r => `<span class="routing-badge">🤖 ${r}</span>`).join('');
                            bub.innerHTML = badges + '<br>' + marked.parse(responseText);
                            scrollBottom();
                        }
                        else if (ev === 'quality') {
                            const q = d.quality || {};
                            const stars = (n) => '★'.repeat(Math.min(n, 5)) + '☆'.repeat(5 - Math.min(n, 5));
                            bub.innerHTML += `<div class="quality-bar">Quality: ${stars(q.overall || 3)} (${q.overall || 3}/5)</div>`;
                        }
                        else if (ev === 'done') {
                            hl(null);
                        }
                        else if (ev === 'error') {
                            bub.innerHTML = `<em>❌ ${d.message}</em>`;
                        }
                    } catch (e) {}
                }
            }
        }
    } catch (e) {
        bub.innerHTML = `<em>❌ Connection error: ${e.message}</em>`;
        hl(null);
    }
}

// --- Init ---
mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });
checkAuthRedirect();
loadRecordings();
loadDocuments();


// --- Architecture Diagram ---
let _archZoom = 1;

async function showArchitecture() {
    try {
        const res = await fetch(BASE + '/api/architecture');
        const data = await res.json();
        _archZoom = 1;

        const modal = document.createElement('div');
        modal.className = 'arch-modal';
        modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
        modal.innerHTML = `
            <div class="arch-content">
                <div class="arch-header">
                    <h2>CCCP Platform Architecture</h2>
                    <div class="arch-controls">
                        <button onclick="archZoom(-0.15)" title="Zoom Out">➖</button>
                        <button onclick="archZoom(0)" title="Fit">⬜</button>
                        <button onclick="archZoom(0.15)" title="Zoom In">➕</button>
                        <button class="arch-close" onclick="this.closest('.arch-modal').remove()" title="Close">✕</button>
                    </div>
                </div>
                <div class="arch-body">
                    <div class="mermaid" id="archDiagram">${data.diagram}</div>
                </div>
            </div>`;
        document.body.appendChild(modal);
        await mermaid.run({ nodes: modal.querySelectorAll('.mermaid') });

        // Force SVG to fill container
        const svg = document.querySelector('#archDiagram svg');
        if (svg) {
            svg.removeAttribute('height');
            svg.style.width = '100%';
            svg.style.height = '100%';
            svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
        }
    } catch (e) {
        alert('Failed to load architecture: ' + e.message);
    }
}

function archZoom(delta) {
    const el = document.getElementById('archDiagram');
    if (!el) return;
    if (delta === 0) { _archZoom = 1; }
    else { _archZoom = Math.max(0.5, Math.min(3, _archZoom + delta)); }
    el.style.transform = `scale(${_archZoom})`;
}

// --- Recordings ---
async function loadRecordings() {
    const container = document.getElementById('recordingsList');
    if (!container) return;
    try {
        const res = await fetch(BASE + '/api/recordings');
        const data = await res.json();
        if (!data.recordings || data.recordings.length === 0) {
            container.innerHTML = '<span class="sp-loading">No recordings</span>';
            return;
        }
        container.innerHTML = data.recordings.map(r => {
            const status = r.processed ? 'processed' : 'pending';
            const dot = r.processed ? 'done' : 'wait';
            const icon = r.processed ? '✅' : '⏳';
            const sentiment = r.sentiment != null ? ` | Sent: ${r.sentiment > 0 ? '😊' : r.sentiment < -0.3 ? '😠' : '😐'}` : '';
            const nps = r.estimated_nps != null ? ` | NPS: ${r.estimated_nps}` : '';
            return `<div class="rec-item ${status}">
                <span class="rec-status ${dot}"></span>
                <div class="rec-info">
                    <div class="rec-id">${icon} ${r.call_id}</div>
                    <div class="rec-meta">${r.call_centre || ''} | ${r.call_date?.split(' ')[0] || ''}${sentiment}${nps}</div>
                </div>
            </div>`;
        }).join('');
    } catch (e) {
        container.innerHTML = '<span class="sp-loading">Error loading</span>';
    }
}


// --- MLflow Dashboard ---
function showMLflow() {
    const MLFLOW_URL = 'https://cccp-mlflow.agreeablecliff-8b7135c2.northeurope.azurecontainerapps.io/';
    const modal = document.createElement('div');
    modal.className = 'arch-modal';
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    modal.innerHTML = `
        <div class="arch-content" style="width:95vw;height:85vh;padding:0;overflow:hidden">
            <button class="arch-close" onclick="this.parentElement.parentElement.remove()" style="z-index:10;background:white;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center">✕</button>
            <iframe src="${MLFLOW_URL}" style="width:100%;height:100%;border:none;border-radius:12px"></iframe>
        </div>`;
    document.body.appendChild(modal);
}


// --- Live Call Simulation (Real-time STT + Sentiment) ---
let _liveCallActive = false;
let _recognition = null;
let _sentimentHistory = [];

function toggleLiveCall() {
    if (_liveCallActive) {
        stopLiveCall();
    } else {
        startLiveCall();
    }
}

function startLiveCall() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        alert('Speech Recognition not supported. Use Chrome or Edge.');
        return;
    }

    _liveCallActive = true;
    _sentimentHistory = [];
    const btn = document.getElementById('liveCallBtn');
    btn.textContent = '⏹️ Stop Call';
    btn.classList.add('active');
    document.getElementById('liveCallPanel').style.display = 'block';
    document.getElementById('liveTranscript').innerHTML = '';
    document.getElementById('currentSentiment').textContent = '—';
    document.getElementById('overallSentiment').textContent = '—';

    _recognition = new SR();
    _recognition.lang = 'en-US';
    _recognition.continuous = true;
    _recognition.interimResults = false;

    _recognition.onresult = async (e) => {
        for (let i = e.resultIndex; i < e.results.length; i++) {
            if (e.results[i].isFinal) {
                const text = e.results[i][0].transcript.trim();
                if (text) {
                    await processUtterance(text);
                }
            }
        }
    };

    _recognition.onerror = (e) => {
        if (e.error !== 'no-speech') {
            console.warn('STT error:', e.error);
        }
    };

    _recognition.onend = () => {
        if (_liveCallActive) {
            _recognition.start(); // Keep listening
        }
    };

    _recognition.start();
}

function stopLiveCall() {
    _liveCallActive = false;
    if (_recognition) {
        _recognition.stop();
        _recognition = null;
    }
    const btn = document.getElementById('liveCallBtn');
    btn.textContent = '🎤 Start Live Call';
    btn.classList.remove('active');
}

async function processUtterance(text) {
    // Send to backend for sentiment analysis
    try {
        const res = await fetch(BASE + '/api/sentiment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, call_id: 'live-' + SID }),
        });
        const data = await res.json();

        // Update current sentiment
        const sentiment = data.sentiment || 'neutral';
        const score = data.score || 0;
        _sentimentHistory.push(score);

        const currentEl = document.getElementById('currentSentiment');
        currentEl.textContent = `${sentimentEmoji(sentiment)} ${sentiment} (${score.toFixed(2)})`;
        currentEl.className = `sentiment-value ${sentiment}`;

        // Update overall sentiment (rolling average)
        const avg = _sentimentHistory.reduce((a, b) => a + b, 0) / _sentimentHistory.length;
        const overallSent = avg < -0.2 ? 'negative' : avg > 0.2 ? 'positive' : 'neutral';
        const overallEl = document.getElementById('overallSentiment');
        overallEl.textContent = `${sentimentEmoji(overallSent)} ${overallSent} (${avg.toFixed(2)})`;
        overallEl.className = `sentiment-value ${overallSent}`;

        // Add to transcript
        const transcript = document.getElementById('liveTranscript');
        const badgeClass = sentiment === 'positive' ? 'pos' : sentiment === 'negative' ? 'neg' : 'neu';
        transcript.innerHTML += `<div class="utterance">"${text}" <span class="sent-badge ${badgeClass}">${sentiment} ${score.toFixed(1)}</span></div>`;
        transcript.scrollTop = transcript.scrollHeight;

    } catch (e) {
        console.warn('Sentiment analysis failed:', e);
        // Still show transcript
        const transcript = document.getElementById('liveTranscript');
        transcript.innerHTML += `<div class="utterance">"${text}" <span class="sent-badge neu">?</span></div>`;
    }
}

function sentimentEmoji(s) {
    if (s === 'positive') return '😊';
    if (s === 'negative') return '😠';
    return '😐';
}


// --- Documents (Knowledge Base) ---
async function loadDocuments() {
    const container = document.getElementById('documentsList');
    if (!container) return;
    try {
        const res = await fetch(BASE + '/api/documents');
        const data = await res.json();
        if (!data.documents || data.documents.length === 0) {
            container.innerHTML = '<span class="sp-loading">No documents yet</span>';
            return;
        }
        container.innerHTML = data.documents.map(d => {
            const sizeMB = (d.size / 1024 / 1024).toFixed(1);
            return `<a href="${d.url}" target="_blank" class="doc-item">
                <span class="doc-icon">📕</span>
                <div class="doc-info">
                    <div class="doc-name">${d.name}</div>
                    <div class="doc-meta">${sizeMB} MB • ${d.indexed ? '✅ Indexed' : '⏳ Processing'}</div>
                </div>
                <span class="doc-download">⬇️</span>
            </a>`;
        }).join('');
    } catch (e) {
        container.innerHTML = '<span class="sp-loading">Error loading</span>';
    }
}

async function uploadDocument(input) {
    const file = input.files[0];
    if (!file) return;
    if (!file.name.endsWith('.pdf')) {
        alert('Only PDF files are supported');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const container = document.getElementById('documentsList');
    container.innerHTML += `<div class="doc-item"><span class="doc-icon">⏳</span><div class="doc-info"><div class="doc-name">${file.name}</div><div class="doc-meta">Uploading & indexing...</div></div></div>`;

    try {
        const res = await fetch(BASE + '/api/documents/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (data.error) {
            alert(data.error);
        } else {
            // Reload documents list after a delay (indexing is async)
            setTimeout(loadDocuments, 3000);
        }
    } catch (e) {
        alert('Upload failed: ' + e.message);
    }
    input.value = '';
}
