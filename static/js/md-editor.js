/* Markdown editor + @mentions autocomplete for PolCRM */
(function () {
    'use strict';
    const escHtml = (v) => String(v ?? '').replace(/[&<>"']/g,
        (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

    // ── Toolbar insertion helpers ─────────────────────────────
    window.mdInsertInto = function (textareaId, before, after) {
        const ta = document.getElementById(textareaId);
        if (!ta) return;
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        const sel = ta.value.substring(start, end);
        ta.value = ta.value.substring(0, start) + before + sel + after + ta.value.substring(end);
        ta.focus();
        ta.selectionStart = start + before.length;
        ta.selectionEnd = start + before.length + sel.length;
    };

    window.mdInsert = function (before, after) {
        mdInsertInto('md-description', before, after);
    };

    // ── Preview toggle ─────────────────────────────────────────
    window.mdTogglePreview = function (btn) {
        const editor = btn.closest('.md-editor');
        if (!editor) return;
        const ta = editor.querySelector('.md-textarea');
        const box = editor.querySelector('.md-preview');
        if (!box) return;
        const shown = box.style.display !== 'none';
        if (shown) {
            box.style.display = 'none';
            ta.style.display = '';
        } else {
            box.innerHTML = renderMarkdownLite(ta.value);
            box.style.display = '';
        }
    };

    // ── Lightweight markdown (client-side) ─────────────────────
    function renderMarkdownLite(text) {
        if (!text) return '<em style="color: var(--text-subtle);">' + escHtml(window.t('Pusty opis')) + '</em>';
        let html = escHtml(text);  // escapes & < > " ' - text from other users is not trusted

        // Code blocks
        html = html.replace(/```([\s\S]*?)```/g, (m, code) => `<pre><code>${code.trim()}</code></pre>`);
        // Inline code
        html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
        // Headings
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
        // Blockquote
        html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
        // Bold + italic
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        // Links
        html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, href) =>
            /^(https?:|mailto:|\/)/i.test(href) ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>` : label);
        // Checkboxes
        html = html.replace(/^- \[ \] (.+)$/gm, '<div>☐ $1</div>');
        html = html.replace(/^- \[x\] (.+)$/gmi, '<div>✓ $1</div>');
        // Lists (simple)
        html = html.replace(/^(?:- (.+)(?:\n|$))+/gm, (m) => {
            const items = m.trim().split('\n').map(l => l.replace(/^- /, '')).map(i => `<li>${i}</li>`).join('');
            return `<ul>${items}</ul>`;
        });
        html = html.replace(/^(?:\d+\. (.+)(?:\n|$))+/gm, (m) => {
            const items = m.trim().split('\n').map(l => l.replace(/^\d+\. /, '')).map(i => `<li>${i}</li>`).join('');
            return `<ol>${items}</ol>`;
        });
        // @mentions
        html = html.replace(/@([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+)/g, '<span class="mention">@$1</span>');
        // Paragraph breaks (double newline)
        html = html.split(/\n\n+/).map(p => p.startsWith('<') ? p : `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
        return html;
    }

    // ── @mentions autocomplete ────────────────────────────────
    // Fetch user list from meta tag injected by layout
    function getUsers() {
        const meta = document.querySelector('meta[name="app-users"]');
        if (!meta) return [];
        try { return JSON.parse(meta.content); } catch (e) { return []; }
    }

    function attachMentionAutocomplete(textarea) {
        const users = getUsers();
        if (!users.length) return;
        let dropdown = null;
        let activeIdx = 0;
        let filter = '';

        function close() {
            if (dropdown) { dropdown.remove(); dropdown = null; }
        }

        function renderDropdown(matches, taRect, caretPos) {
            close();
            if (!matches.length) return;
            dropdown = document.createElement('div');
            dropdown.className = 'mention-dropdown';
            matches.forEach((u, i) => {
                const opt = document.createElement('div');
                opt.className = 'mention-opt' + (i === activeIdx ? ' active' : '');
                opt.innerHTML = `
                    <span class="author-avatar-xs" style="background: linear-gradient(135deg, ${escHtml(u.avatar_color)}, ${escHtml(u.avatar_color)}cc);">${escHtml(u.initials || u.name[0])}</span>
                    <span>${escHtml(u.name)}</span>
                `;
                opt.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    insertMention(textarea, u.name);
                    close();
                });
                dropdown.appendChild(opt);
            });
            dropdown.style.left = (taRect.left + window.scrollX + 14) + 'px';
            dropdown.style.top = (taRect.bottom + window.scrollY - 40) + 'px';
            document.body.appendChild(dropdown);
        }

        function insertMention(ta, name) {
            const pos = ta.selectionStart;
            const before = ta.value.substring(0, pos);
            const after = ta.value.substring(pos);
            const atIdx = before.lastIndexOf('@');
            if (atIdx < 0) return;
            const newBefore = before.substring(0, atIdx) + '@' + name + ' ';
            ta.value = newBefore + after;
            ta.focus();
            ta.selectionStart = ta.selectionEnd = newBefore.length;
        }

        textarea.addEventListener('input', (e) => {
            const pos = textarea.selectionStart;
            const before = textarea.value.substring(0, pos);
            const atIdx = before.lastIndexOf('@');
            if (atIdx < 0 || /\s/.test(before.charAt(atIdx - 1) || ' ') === false && atIdx !== 0) {
                close();
                return;
            }
            const charBefore = atIdx === 0 ? ' ' : before.charAt(atIdx - 1);
            if (!/\s|^/.test(charBefore) && atIdx !== 0) {
                close();
                return;
            }
            filter = before.substring(atIdx + 1).toLowerCase();
            if (/\s/.test(filter)) { close(); return; }
            const matches = users.filter(u => u.name.toLowerCase().startsWith(filter));
            if (!matches.length) { close(); return; }
            activeIdx = 0;
            renderDropdown(matches, textarea.getBoundingClientRect());
        });

        textarea.addEventListener('keydown', (e) => {
            if (!dropdown) return;
            const items = dropdown.querySelectorAll('.mention-opt');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activeIdx = (activeIdx + 1) % items.length;
                items.forEach((o, i) => o.classList.toggle('active', i === activeIdx));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                activeIdx = (activeIdx - 1 + items.length) % items.length;
                items.forEach((o, i) => o.classList.toggle('active', i === activeIdx));
            } else if (e.key === 'Enter' || e.key === 'Tab') {
                e.preventDefault();
                const active = dropdown.querySelector('.mention-opt.active');
                if (active) active.dispatchEvent(new MouseEvent('mousedown'));
            } else if (e.key === 'Escape') {
                close();
            }
        });

        textarea.addEventListener('blur', () => setTimeout(close, 150));
    }

    // Auto-attach to all md-editor textareas with data-mentions
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.md-editor[data-mentions="on"] .md-textarea')
            .forEach(attachMentionAutocomplete);
    });
})();
