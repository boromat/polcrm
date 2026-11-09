/* ═══════════════════════════════════════════════════════════════
   PolCRM - AI Assistant widget
   ═══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    let configured = null;
    let open = false;
    let sending = false;

    // Build UI lazily
    let widget = null;
    let toggleBtn = null;

    function buildToggle() {
        toggleBtn = document.createElement('button');
        toggleBtn.id = 'assistant-toggle';
        toggleBtn.className = 'assistant-toggle';
        toggleBtn.setAttribute('aria-label', t('Otwórz asystenta AI'));
        toggleBtn.innerHTML = `<i class="bi bi-stars"></i><span class="assistant-toggle-label">${escapeHtml(t('Asystent'))}</span>`;
        toggleBtn.onclick = toggleWidget;
        document.body.appendChild(toggleBtn);
    }

    const QUICK_ACTIONS = [
        { icon: 'bi-check2-square', color: 'var(--accent-light)', title: t('Zadania na dziś'), query: t('Pokaż moje zadania na dziś') },
        { icon: 'bi-cash-coin', color: 'var(--warning-light)', title: t('Zaległe faktury'), query: t('Ile mam zaległych faktur i na jaką kwotę?') },
        { icon: 'bi-pie-chart-fill', color: 'var(--success-light)', title: t('Bilans miesiąca'), query: t('Podsumuj finanse tego miesiąca') },
        { icon: 'bi-calendar3', color: 'var(--cyan-light)', title: t('Kalendarz'), query: t('Co mam w kalendarzu w najbliższym tygodniu?') },
        { icon: 'bi-kanban', color: 'var(--pink-light)', title: 'Pipeline', query: t('Ile firm jest w każdym etapie pipeline\'u?') },
        { icon: 'bi-plus-lg', color: 'var(--info-light)', title: t('Nowe zadanie'), query: t('Utwórz dla mnie nowe zadanie') },
    ];

    const CHIPS = [
        t('Zaległe faktury'),
        t('Zadania na dziś'),
        t('Bilans miesiąca'),
        t('Kalendarz'),
        t('Klienci bez kontaktu 30 dni'),
        t('Top klienci po przychodzie'),
    ];

    function buildWidget() {
        widget = document.createElement('div');
        widget.id = 'assistant-widget';
        widget.className = 'assistant-widget';

        const quickActionsHtml = QUICK_ACTIONS.map(a => `
            <button class="assistant-quick-action" data-q="${escapeHtml(a.query)}">
                <div class="assistant-quick-icon" style="color: ${a.color};"><i class="bi ${a.icon}"></i></div>
                <div class="assistant-quick-label">${escapeHtml(a.title)}</div>
            </button>
        `).join('');

        const chipsHtml = CHIPS.map(c => `<button class="assistant-chip" data-q="${escapeHtml(c)}">${escapeHtml(c)}</button>`).join('');

        widget.innerHTML = `
            <div class="assistant-header">
                <div class="assistant-title">
                    <div class="assistant-avatar"><i class="bi bi-stars"></i></div>
                    <div class="assistant-title-text">
                        <div class="assistant-name">${escapeHtml(t('Asystent PolCRM'))}</div>
                        <div class="assistant-sub" id="assistant-model-info"><span class="assistant-dot"></span>${escapeHtml(t('Łączę...'))}</div>
                    </div>
                </div>
                <div class="assistant-actions">
                    <button class="assistant-icon-btn" id="assistant-reset" title="${escapeHtml(t('Wyczyść rozmowę'))}"><i class="bi bi-arrow-counterclockwise"></i></button>
                    <button class="assistant-icon-btn" id="assistant-close" title="${escapeHtml(t('Zamknij'))}"><i class="bi bi-x-lg"></i></button>
                </div>
            </div>
            <div class="assistant-messages" id="assistant-messages">
                <div class="assistant-welcome">
                    <div class="assistant-welcome-hero">
                        <div class="assistant-welcome-icon"><i class="bi bi-stars"></i></div>
                        <h3 class="assistant-welcome-title">${escapeHtml(t('W czym mogę pomóc?'))}</h3>
                        <p class="assistant-welcome-sub">${escapeHtml(t('Pytaj po polsku - sprawdzę bazę i odpowiem natychmiast.'))}</p>
                    </div>
                    <div class="assistant-quick-grid">${quickActionsHtml}</div>
                </div>
            </div>
            <div class="assistant-suggestions" id="assistant-suggestions">${chipsHtml}</div>
            <form class="assistant-input-wrap" id="assistant-form">
                <textarea id="assistant-input" class="assistant-input" placeholder="${escapeHtml(t('Napisz pytanie...'))}" rows="1" maxlength="4000"></textarea>
                <button type="submit" class="assistant-send" title="${escapeHtml(t('Wyślij (Enter)'))}"><i class="bi bi-arrow-up"></i></button>
            </form>
            <div class="assistant-hint">${escapeHtml(t('Enter = wyślij · Shift+Enter = nowa linia · ⌘J = otwórz/zamknij'))}</div>
        `;
        document.body.appendChild(widget);

        widget.querySelector('#assistant-close').onclick = closeWidget;
        widget.querySelector('#assistant-reset').onclick = resetConversation;
        widget.querySelector('#assistant-form').onsubmit = onSubmit;

        const input = widget.querySelector('#assistant-input');
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                widget.querySelector('#assistant-form').requestSubmit();
            }
        });
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });

        widget.querySelectorAll('.assistant-quick-action, .assistant-chip').forEach(btn => {
            btn.onclick = () => { input.value = btn.dataset.q; sendMessage(); };
        });

        checkStatus();
    }

    function shortModel(model) {
        if (!model) return 'online';
        // 'google/gemini-3.1-flash-lite-preview' → 'gemini-3.1-flash-lite'
        let name = model.includes('/') ? model.split('/').pop() : model;
        name = name.replace(/-preview(-\d+)?$/i, '');
        return name;
    }

    async function checkStatus() {
        try {
            const r = await fetch('/api/assistant/status');
            const j = await r.json();
            configured = j.configured;
            const info = widget.querySelector('#assistant-model-info');
            if (!j.configured) {
                const reason = !j.has_key ? t('brak klucza API') : (!j.enabled ? t('wyłączony') : t('nieskonfigurowany'));
                info.innerHTML = `<span class="assistant-dot assistant-dot-warn"></span>${escapeHtml(reason)}`;
                const welcome = widget.querySelector('.assistant-welcome');
                if (welcome) {
                    welcome.innerHTML = `
                        <div class="assistant-welcome-hero">
                            <div class="assistant-welcome-icon" style="background: linear-gradient(135deg, var(--warning), var(--warning-light));"><i class="bi bi-exclamation-triangle-fill"></i></div>
                            <h3 class="assistant-welcome-title">${escapeHtml(t('Wymagana konfiguracja'))}</h3>
                            <p class="assistant-welcome-sub">${escapeHtml(t('Wpisz klucz OpenRouter API i włącz asystenta:'))}</p>
                            <a href="/settings#ai" class="btn btn-primary" style="margin-top: 14px;"><i class="bi bi-gear-fill"></i>${escapeHtml(t('Otwórz Ustawienia → AI Asystent'))}</a>
                        </div>`;
                }
            } else {
                info.innerHTML = `<span class="assistant-dot assistant-dot-ok"></span>${escapeHtml(shortModel(j.model))}`;
            }
        } catch (e) {
            configured = false;
            const info = widget.querySelector('#assistant-model-info');
            info.innerHTML = `<span class="assistant-dot assistant-dot-err"></span>offline`;
        }
    }

    function toggleWidget() {
        if (!widget) buildWidget();
        if (open) closeWidget();
        else openWidget();
    }

    function openWidget() {
        if (!widget) buildWidget();
        widget.classList.add('open');
        toggleBtn.classList.add('hidden');
        open = true;
        setTimeout(() => widget.querySelector('#assistant-input')?.focus(), 150);
    }

    function closeWidget() {
        widget.classList.remove('open');
        toggleBtn.classList.remove('hidden');
        open = false;
    }

    function onSubmit(e) {
        e.preventDefault();
        sendMessage();
    }

    async function sendMessage() {
        if (sending) return;
        const input = widget.querySelector('#assistant-input');
        const msg = input.value.trim();
        if (!msg) return;
        if (configured === false) {
            window.toast?.warning(t('Asystent nie jest skonfigurowany. Wpisz klucz OpenRouter i włącz asystenta w Ustawienia → AI Asystent.'));
            return;
        }

        addUserMessage(msg);
        input.value = '';
        input.style.height = 'auto';
        hideSuggestions();
        const thinkingEl = addThinkingMessage();
        sending = true;

        try {
            const r = await fetch('/api/assistant/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg }),
            });
            const j = await r.json();
            thinkingEl.remove();
            if (!r.ok) {
                addBotMessage(`<span style="color: var(--danger-light);">${escapeHtml(t('Błąd: %(error)s').replace('%(error)s', () => j.error || t('nieznany')))}</span>`, true);
            } else {
                addBotMessage(formatMarkdown(j.reply || ''));
                if (j.tools_called?.length) {
                    const toolsEl = widget.querySelector('.assistant-msg-bot:last-child .assistant-msg-body');
                    if (toolsEl) {
                        const tags = document.createElement('div');
                        tags.className = 'assistant-tools';
                        tags.innerHTML = j.tools_called.map(t => `<span class="assistant-tool-tag"><i class="bi bi-lightning-charge-fill"></i> ${escapeHtml(t)}</span>`).join('');
                        toolsEl.appendChild(tags);
                    }
                }
            }
        } catch (err) {
            thinkingEl.remove();
            addBotMessage(`<span style="color: var(--danger-light);">${escapeHtml(t('Błąd sieci: %(error)s').replace('%(error)s', () => err.message))}</span>`, true);
        } finally {
            sending = false;
        }
    }

    function addUserMessage(text) {
        const msgs = widget.querySelector('#assistant-messages');
        const el = document.createElement('div');
        el.className = 'assistant-msg assistant-msg-user';
        el.innerHTML = `<div class="assistant-msg-body">${escapeHtml(text).replace(/\n/g, '<br>')}</div>`;
        msgs.appendChild(el);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function addBotMessage(html, isHtml = false) {
        const msgs = widget.querySelector('#assistant-messages');
        const el = document.createElement('div');
        el.className = 'assistant-msg assistant-msg-bot';
        el.innerHTML = `<div class="assistant-msg-body">${html}</div>`;
        msgs.appendChild(el);
        msgs.scrollTop = msgs.scrollHeight;
        return el;
    }

    function addThinkingMessage() {
        const msgs = widget.querySelector('#assistant-messages');
        const el = document.createElement('div');
        el.className = 'assistant-msg assistant-msg-bot assistant-msg-thinking';
        el.innerHTML = `<div class="assistant-msg-body"><div class="thinking-dots"><span></span><span></span><span></span></div></div>`;
        msgs.appendChild(el);
        msgs.scrollTop = msgs.scrollHeight;
        return el;
    }

    function hideSuggestions() {
        const s = widget.querySelector('#assistant-suggestions');
        if (s) s.style.display = 'none';
        const w = widget.querySelector('.assistant-welcome');
        if (w) w.style.display = 'none';
    }

    async function resetConversation() {
        try {
            await fetch('/api/assistant/reset', { method: 'POST' });
            // Odbuduj widget aby przywrócić welcome screen
            widget.remove();
            widget = null;
            buildWidget();
            widget.classList.add('open');
            window.toast?.success(t('Rozmowa wyczyszczona'));
        } catch (e) {
            window.toast?.error(t('Nie udało się wyczyścić'));
        }
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function formatMarkdown(text) {
        // Lekki markdown: **bold**, *italic*, `code`, linki, listy, newline
        let html = escapeHtml(text);
        html = html.replace(/```([\s\S]*?)```/g, (_, c) => `<pre><code>${c.trim()}</code></pre>`);
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        // Linki - pola /tasks/123 , /companies/5 itp. + pełne http
        html = html.replace(/\b(\/[a-z0-9\-_\/]+(?:\?[^\s<]*)?)/gi, '<a href="$1">$1</a>');
        html = html.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    // ─── Init ──────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        buildToggle();
        // Keyboard shortcut: Ctrl/Cmd+J otwiera asystenta
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
                e.preventDefault();
                toggleWidget();
            }
        });
    });

    window.assistant = { open: openWidget, close: closeWidget, toggle: toggleWidget };
})();
