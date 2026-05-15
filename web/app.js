const BASE = 'https://cccp-chatbot.agreeablecliff-8b7135c2.northeurope.azurecontainerapps.io';
marked.setOptions({ breaks: true, gfm: true });

let _userName = 'Guest';
let _userEmail = '';
let _accessToken = null; // Microsoft Graph token for SharePoint
let SID = localStorage.getItem('cccp_session') || crypto.randomUUID();
localStorage.setItem('cccp_session', SID);

// --- Microsoft Login (MSAL) ---
const MSAL_CONFIG = {
    clientId: '', // Set your Azure AD App Client ID here
    authority: 'https://login.microsoftonline.com/common',
    redirectUri: window.location.origin,
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
checkAuthRedirect();
