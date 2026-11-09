/* ═══════════════════════════════════════════════════════════════
   PolCRM - Global UI layer
   Toast, Command Palette, Keyboard shortcuts, Skeleton, Mobile tables
   ═══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ─── TOAST SYSTEM ──────────────────────────────────────────────
    const toastContainer = (() => {
        let c = document.getElementById('toast-container');
        if (!c) {
            c = document.createElement('div');
            c.id = 'toast-container';
            c.className = 'toast-container';
            c.setAttribute('aria-live', 'polite');
            c.setAttribute('aria-atomic', 'true');
            document.body.appendChild(c);
        }
        return c;
    })();

    const ICONS = {
        success: 'bi-check-circle-fill',
        danger: 'bi-exclamation-triangle-fill',
        warning: 'bi-exclamation-circle-fill',
        info: 'bi-info-circle-fill',
    };

    function showToast(msg, type = 'info', opts = {}) {
        const duration = opts.duration ?? 4500;
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.setAttribute('role', 'status');
        el.innerHTML = `
            <i class="bi ${ICONS[type] || ICONS.info} toast-icon"></i>
            <div class="toast-body">${escapeHtml(msg)}</div>
            <button class="toast-close" aria-label="${escapeHtml(t('Zamknij'))}"><i class="bi bi-x-lg"></i></button>
            <div class="toast-progress"><div class="toast-progress-bar" style="animation-duration: ${duration}ms;"></div></div>
        `;
        toastContainer.appendChild(el);
        requestAnimationFrame(() => el.classList.add('show'));

        const dismiss = () => {
            el.classList.remove('show');
            el.classList.add('hide');
            setTimeout(() => el.remove(), 300);
        };
        el.querySelector('.toast-close').onclick = dismiss;
        if (duration > 0) setTimeout(dismiss, duration);
        return { dismiss };
    }

    function escapeHtml(str) {
        return String(str).replace(/[&<>"']/g, s => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[s]));
    }

    window.toast = {
        success: (m, o) => showToast(m, 'success', o),
        error: (m, o) => showToast(m, 'danger', o),
        danger: (m, o) => showToast(m, 'danger', o),
        warning: (m, o) => showToast(m, 'warning', o),
        info: (m, o) => showToast(m, 'info', o),
    };

    // Auto-promocja flash messages → toasts (trzyma istniejące flash dla no-JS, ale pokazuje jako toast)
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.flash-msg').forEach(el => {
            const text = el.childNodes[0]?.textContent?.trim() ||
                el.textContent.replace(/×|✕/g, '').trim();
            if (!text) return;
            let type = 'info';
            if (el.classList.contains('bg-emerald-900/30') || /success/i.test(el.className)) type = 'success';
            else if (el.classList.contains('bg-red-900/30') || /danger|error/i.test(el.className)) type = 'danger';
            else if (el.classList.contains('bg-amber-900/30') || /warning/i.test(el.className)) type = 'warning';
            showToast(text, type);
            el.remove();
        });
    });

    // ─── KEYBOARD SHORTCUTS + COMMAND PALETTE ──────────────────────
    const COMMANDS = [
        { label: t('Nowe zadanie'), icon: 'bi-check2-square', href: '/tasks/new', keywords: 'nowe zadanie task todo' },
        { label: t('Nowa firma'), icon: 'bi-building', href: '/companies/new', keywords: 'nowa firma klient' },
        { label: t('Nowa płatność'), icon: 'bi-cash-coin', href: '/finances/payments/new', keywords: 'nowa płatność faktura' },
        { label: t('Nowy koszt'), icon: 'bi-receipt', href: '/finances/expenses/new', keywords: 'nowy koszt wydatek' },
        { label: t('Nowa notatka'), icon: 'bi-journal-plus', href: '/notes/new', keywords: 'nowa notatka note' },
        { label: t('Nowy projekt'), icon: 'bi-diagram-3', href: '/projects/new', keywords: 'nowy projekt' },
        { label: t('Nowy subskrybent / subskrypcja'), icon: 'bi-arrow-repeat', href: '/finances/subscriptions/new', keywords: 'subskrypcja subscription' },
        { label: t('Nowy szablon email'), icon: 'bi-envelope-plus', href: '/emails/templates/new', keywords: 'email template' },
        { type: 'sep', label: t('Nawigacja') },
        { label: 'Dashboard', icon: 'bi-grid-1x2-fill', href: '/', keywords: 'dashboard home strona głowna' },
        { label: t('Firmy'), icon: 'bi-building', href: '/companies', keywords: 'firmy klienci' },
        { label: 'Pipeline', icon: 'bi-kanban', href: '/pipeline', keywords: 'pipeline sprzedaz' },
        { label: t('Kalendarz'), icon: 'bi-calendar3', href: '/calendar', keywords: 'kalendarz calendar' },
        { label: t('Zadania'), icon: 'bi-check2-square', href: '/tasks', keywords: 'zadania produkcja' },
        { label: t('Projekty'), icon: 'bi-diagram-3', href: '/projects', keywords: 'projekty' },
        { label: t('Finanse'), icon: 'bi-pie-chart-fill', href: '/finances', keywords: 'finanse' },
        { label: t('Przychody'), icon: 'bi-arrow-up-right-circle', href: '/finances/payments', keywords: 'przychody płatności' },
        { label: t('Koszty'), icon: 'bi-receipt', href: '/finances/expenses', keywords: 'koszty wydatki' },
        { label: t('Subskrypcje'), icon: 'bi-arrow-repeat', href: '/finances/subscriptions', keywords: 'subskrypcje' },
        { label: t('Raport finansowy'), icon: 'bi-graph-up', href: '/finances/report/internal', keywords: 'raport finansowy' },
        { label: t('Tablica'), icon: 'bi-easel-fill', href: '/tablica', keywords: 'tablica whiteboard' },
        { label: t('Notatnik'), icon: 'bi-journal-text', href: '/notes', keywords: 'notatnik notes' },
        { label: t('Szablony email'), icon: 'bi-envelope-paper', href: '/emails/templates', keywords: 'szablony email templates' },
        { label: t('Inbox / Skrzynka'), icon: 'bi-inbox-fill', href: '/inbox', keywords: 'inbox skrzynka' },
        { label: t('Aktywności'), icon: 'bi-activity', href: '/aktywnosci', keywords: 'aktywności activity' },
        { label: t('Ustawienia'), icon: 'bi-gear-fill', href: '/settings', keywords: 'ustawienia settings' },
        { type: 'sep', label: t('Skróty') },
        { label: t('Otwórz asystenta AI'), icon: 'bi-stars', action: () => window.assistant?.open(), keywords: 'asystent ai chat pomoc' },
        { label: t('Przełącz motyw (kolorowy / minimal)'), icon: 'bi-palette-fill', action: () => toggleTheme(), keywords: 'motyw theme' },
        { label: t('Pokaż skróty klawiszowe'), icon: 'bi-keyboard', action: () => showShortcuts(), keywords: 'skróty klawiszowe shortcuts keyboard' },
        { label: t('Wyloguj się'), icon: 'bi-box-arrow-right', action: () => logout(), keywords: 'wyloguj logout' },
    ];

    function toggleTheme() {
        const f = document.createElement('form');
        f.method = 'POST';
        f.action = '/toggle-theme';
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (csrf) {
            const inp = document.createElement('input');
            inp.type = 'hidden'; inp.name = 'csrf_token'; inp.value = csrf;
            f.appendChild(inp);
        }
        document.body.appendChild(f); f.submit();
    }

    function logout() {
        const f = document.createElement('form');
        f.method = 'POST'; f.action = '/wyloguj';
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (csrf) {
            const inp = document.createElement('input');
            inp.type = 'hidden'; inp.name = 'csrf_token'; inp.value = csrf;
            f.appendChild(inp);
        }
        document.body.appendChild(f); f.submit();
    }

    // Palette rendering
    let paletteEl = null;
    let paletteOpen = false;
    let paletteFocus = 0;
    let paletteItems = [];

    function buildPalette() {
        if (paletteEl) return paletteEl;
        paletteEl = document.createElement('div');
        paletteEl.className = 'cmd-palette';
        paletteEl.innerHTML = `
            <div class="cmd-palette-backdrop"></div>
            <div class="cmd-palette-dialog" role="dialog" aria-label="${escapeHtml(t('Paleta komend'))}">
                <div class="cmd-palette-input-wrap">
                    <i class="bi bi-search"></i>
                    <input type="text" class="cmd-palette-input" placeholder="${escapeHtml(t('Wpisz komendę, stronę lub skrót: ⌘K...'))}" aria-label="${escapeHtml(t('Wyszukaj komendę'))}">
                    <kbd class="cmd-palette-esc">ESC</kbd>
                </div>
                <div class="cmd-palette-list" role="listbox"></div>
                <div class="cmd-palette-footer">
                    <span><kbd>↑</kbd><kbd>↓</kbd> ${escapeHtml(t('nawigacja'))}</span>
                    <span><kbd>↵</kbd> ${escapeHtml(t('wybierz'))}</span>
                    <span><kbd>ESC</kbd> ${escapeHtml(t('zamknij'))}</span>
                </div>
            </div>
        `;
        document.body.appendChild(paletteEl);

        paletteEl.querySelector('.cmd-palette-backdrop').onclick = closePalette;
        const input = paletteEl.querySelector('.cmd-palette-input');
        input.addEventListener('input', () => renderPaletteList(input.value));
        input.addEventListener('keydown', onPaletteKeydown);
        return paletteEl;
    }

    function renderPaletteList(query) {
        const list = paletteEl.querySelector('.cmd-palette-list');
        const q = (query || '').toLowerCase().trim();
        const filtered = [];
        let hasGlobalSearch = false;
        COMMANDS.forEach(cmd => {
            if (cmd.type === 'sep') {
                if (!q) filtered.push(cmd);
                return;
            }
            if (!q) { filtered.push(cmd); return; }
            const hay = (cmd.label + ' ' + (cmd.keywords || '')).toLowerCase();
            if (hay.includes(q)) filtered.push(cmd);
        });
        if (q && q.length >= 2) {
            filtered.unshift({
                label: t('Szukaj globalnie: "%(query)s"').replace('%(query)s', () => query),
                icon: 'bi-search',
                href: '/szukaj-globalnie?q=' + encodeURIComponent(query),
                keywords: ''
            });
            hasGlobalSearch = true;
        }

        paletteItems = filtered.filter(c => c.type !== 'sep');
        paletteFocus = 0;

        list.innerHTML = '';
        if (!filtered.length) {
            list.innerHTML = `<div class="cmd-palette-empty"><i class="bi bi-inboxes"></i> ${escapeHtml(t('Brak wyników dla "%(query)s"').replace('%(query)s', () => query))}</div>`;
            return;
        }
        filtered.forEach((cmd) => {
            if (cmd.type === 'sep') {
                const s = document.createElement('div');
                s.className = 'cmd-palette-sep';
                s.textContent = cmd.label;
                list.appendChild(s);
                return;
            }
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'cmd-palette-item';
            item.innerHTML = `<i class="bi ${cmd.icon || 'bi-arrow-right-short'}"></i><span>${escapeHtml(cmd.label)}</span>`;
            item.onclick = () => executeCommand(cmd);
            item.onmouseenter = () => {
                const idx = paletteItems.indexOf(cmd);
                if (idx >= 0) { paletteFocus = idx; updatePaletteFocus(); }
            };
            list.appendChild(item);
        });
        updatePaletteFocus();
    }

    function updatePaletteFocus() {
        const buttons = paletteEl.querySelectorAll('.cmd-palette-item');
        buttons.forEach(b => b.classList.remove('focused'));
        const target = paletteItems[paletteFocus];
        if (!target) return;
        for (const b of buttons) {
            if (b.textContent.trim().startsWith(target.label)) {
                b.classList.add('focused');
                b.scrollIntoView({ block: 'nearest' });
                break;
            }
        }
    }

    function onPaletteKeydown(e) {
        if (e.key === 'Escape') { e.preventDefault(); closePalette(); }
        else if (e.key === 'ArrowDown') {
            e.preventDefault();
            paletteFocus = Math.min(paletteItems.length - 1, paletteFocus + 1);
            updatePaletteFocus();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            paletteFocus = Math.max(0, paletteFocus - 1);
            updatePaletteFocus();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const cmd = paletteItems[paletteFocus];
            if (cmd) executeCommand(cmd);
        }
    }

    function executeCommand(cmd) {
        closePalette();
        if (cmd.action) cmd.action();
        else if (cmd.href) window.location.href = cmd.href;
    }

    function openPalette() {
        buildPalette();
        paletteEl.classList.add('open');
        paletteOpen = true;
        document.body.style.overflow = 'hidden';
        const input = paletteEl.querySelector('.cmd-palette-input');
        input.value = '';
        renderPaletteList('');
        setTimeout(() => input.focus(), 10);
    }

    function closePalette() {
        if (!paletteEl) return;
        paletteEl.classList.remove('open');
        paletteOpen = false;
        document.body.style.overflow = '';
    }

    window.cmdPalette = { open: openPalette, close: closePalette };

    // ─── KEYBOARD SHORTCUTS ────────────────────────────────────────
    const SHORTCUTS = [
        { keys: '⌘/Ctrl + K', desc: t('Paleta komend / szukaj wszędzie') },
        { keys: 'G + D', desc: t('Przejdź do Dashboard') },
        { keys: 'G + F', desc: t('Przejdź do Firmy') },
        { keys: 'G + T', desc: t('Przejdź do Zadania') },
        { keys: 'G + P', desc: t('Przejdź do Pipeline') },
        { keys: 'G + C', desc: t('Przejdź do Kalendarz') },
        { keys: 'G + $', desc: t('Przejdź do Finanse') },
        { keys: 'G + I', desc: t('Przejdź do Inbox') },
        { keys: 'N + T', desc: t('Nowe zadanie') },
        { keys: 'N + F', desc: t('Nowa firma') },
        { keys: 'N + P', desc: t('Nowa płatność') },
        { keys: 'N + N', desc: t('Nowa notatka') },
        { keys: '⌘/Ctrl + J', desc: t('Otwórz asystenta AI') },
        { keys: 'Shift + ?', desc: t('Pokaż tę pomoc') },
        { keys: 'ESC', desc: t('Zamknij okno/paletę') },
    ];

    function showShortcuts() {
        const existing = document.getElementById('shortcuts-modal');
        if (existing) existing.remove();
        const el = document.createElement('div');
        el.id = 'shortcuts-modal';
        el.className = 'cmd-palette open';
        el.innerHTML = `
            <div class="cmd-palette-backdrop"></div>
            <div class="cmd-palette-dialog" role="dialog" aria-label="${escapeHtml(t('Skróty klawiszowe'))}" style="max-width: 520px;">
                <div class="cmd-palette-input-wrap" style="cursor: default;">
                    <i class="bi bi-keyboard"></i>
                    <div style="flex: 1; font-weight: 600; color: white; padding: 8px 0;">${escapeHtml(t('Skróty klawiszowe'))}</div>
                    <button class="toast-close" aria-label="${escapeHtml(t('Zamknij'))}"><i class="bi bi-x-lg"></i></button>
                </div>
                <div class="shortcuts-grid">
                    ${SHORTCUTS.map(s => `
                        <div class="shortcut-row">
                            <span class="shortcut-desc">${escapeHtml(s.desc)}</span>
                            <span class="shortcut-keys">${s.keys.split(' + ').map(k => `<kbd>${escapeHtml(k)}</kbd>`).join(' + ')}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        document.body.appendChild(el);
        el.querySelector('.cmd-palette-backdrop').onclick = () => el.remove();
        el.querySelector('.toast-close').onclick = () => el.remove();
        document.addEventListener('keydown', function handler(e) {
            if (e.key === 'Escape') { el.remove(); document.removeEventListener('keydown', handler); }
        });
    }

    window.showShortcuts = showShortcuts;

    // ─── NAVIGATION CHORDS (G + letter, N + letter) ────────────────
    let chordBuffer = null;
    let chordTimeout = null;

    const CHORD_MAP = {
        'g': {
            'd': '/', 'f': '/companies', 't': '/tasks', 'p': '/pipeline',
            'c': '/calendar', 'i': '/inbox', 's': '/settings',
            '$': '/finances', '4': '/finances',
        },
        'n': {
            't': '/tasks/new', 'f': '/companies/new', 'p': '/finances/payments/new',
            'n': '/notes/new', 'k': '/finances/expenses/new', 's': '/projects/new',
        },
    };

    function inInput(el) {
        if (!el) return false;
        const tag = el.tagName;
        return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
    }

    document.addEventListener('keydown', (e) => {
        // Cmd+K / Ctrl+K → palette
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            openPalette();
            return;
        }
        // Shift + ? → shortcuts help
        if (e.shiftKey && e.key === '?') {
            if (inInput(e.target)) return;
            e.preventDefault();
            showShortcuts();
            return;
        }
        // Escape → close palette
        if (e.key === 'Escape' && paletteOpen) {
            closePalette();
            return;
        }
        // Chord navigation
        if (inInput(e.target)) return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;
        const k = e.key.toLowerCase();
        if (chordBuffer) {
            const map = CHORD_MAP[chordBuffer];
            if (map && map[k]) {
                e.preventDefault();
                window.location.href = map[k];
            }
            chordBuffer = null;
            clearTimeout(chordTimeout);
        } else if (CHORD_MAP[k]) {
            chordBuffer = k;
            chordTimeout = setTimeout(() => { chordBuffer = null; }, 1200);
            // Small hint
            showChordHint(k);
        }
    });

    function showChordHint(prefix) {
        const existing = document.getElementById('chord-hint');
        if (existing) existing.remove();
        const el = document.createElement('div');
        el.id = 'chord-hint';
        el.className = 'chord-hint';
        const suggestions = Object.keys(CHORD_MAP[prefix] || {}).slice(0, 6);
        el.innerHTML = `<kbd>${prefix.toUpperCase()}</kbd> + <span class="chord-hint-letters">${suggestions.map(s => `<kbd>${s.toUpperCase()}</kbd>`).join('')}</span>`;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 1200);
    }

    // ─── SKELETON LOADER API ───────────────────────────────────────
    window.skeleton = {
        show(target, config = {}) {
            const el = typeof target === 'string' ? document.querySelector(target) : target;
            if (!el) return;
            const rows = config.rows || 3;
            const type = config.type || 'list'; // list | card | stat
            el.dataset.skeletonActive = '1';
            let html = '';
            if (type === 'stat') {
                html = `<div class="skel-stat"><div class="skel-bar" style="width: 40%; height: 12px;"></div><div class="skel-bar" style="width: 70%; height: 28px; margin-top: 8px;"></div><div class="skel-bar" style="width: 50%; height: 10px; margin-top: 8px;"></div></div>`;
            } else if (type === 'card') {
                html = Array.from({ length: rows }, () => `
                    <div class="skel-card">
                        <div class="skel-bar" style="width: 60%; height: 14px;"></div>
                        <div class="skel-bar" style="width: 90%; height: 10px; margin-top: 10px;"></div>
                        <div class="skel-bar" style="width: 40%; height: 10px; margin-top: 6px;"></div>
                    </div>
                `).join('');
            } else {
                html = Array.from({ length: rows }, () => `
                    <div class="skel-row">
                        <div class="skel-circle"></div>
                        <div style="flex: 1;">
                            <div class="skel-bar" style="width: 70%; height: 12px;"></div>
                            <div class="skel-bar" style="width: 40%; height: 10px; margin-top: 6px;"></div>
                        </div>
                    </div>
                `).join('');
            }
            el.innerHTML = `<div class="skel-wrap">${html}</div>`;
        },
        hide(target) {
            const el = typeof target === 'string' ? document.querySelector(target) : target;
            if (!el) return;
            delete el.dataset.skeletonActive;
            const w = el.querySelector('.skel-wrap');
            if (w) w.remove();
        }
    };

    // ─── MOBILE TABLES ─────────────────────────────────────────────
    // Automatycznie dorzuca data-label do komórek na podstawie thead
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('table.data-table').forEach(tbl => {
            const headers = [...tbl.querySelectorAll('thead th')].map(th => th.textContent.trim());
            if (!headers.length) return;
            tbl.querySelectorAll('tbody tr').forEach(tr => {
                [...tr.children].forEach((td, i) => {
                    if (headers[i] && !td.hasAttribute('data-label')) {
                        td.setAttribute('data-label', headers[i]);
                    }
                });
            });
            tbl.classList.add('data-table-responsive');
        });
    });

    // ─── MICRO-INTERACTIONS: button loading state ───────────────────
    document.addEventListener('submit', (e) => {
        const f = e.target;
        if (!(f instanceof HTMLFormElement)) return;
        // A form handled in JS (assistant, fetch forms) or a cancelled confirm() does not navigate,
        // so no spinner: it would stay on the button until the 8 s reset below.
        if (e.defaultPrevented) return;
        const btn = f.querySelector('button[type="submit"]:not([data-no-loading]), button:not([type]):not([data-no-loading])');
        if (!btn) return;
        if (btn.dataset.loading === '1') return;
        btn.dataset.loading = '1';
        btn.dataset.originalHtml = btn.innerHTML;
        btn.innerHTML = `<span class="btn-spinner"></span> ${btn.textContent.trim() || ''}`;
        btn.disabled = true;
        // Auto-reset po 8s jeśli submit się nie powiódł
        setTimeout(() => {
            if (btn.dataset.loading === '1') {
                btn.innerHTML = btn.dataset.originalHtml || btn.innerHTML;
                btn.disabled = false;
                delete btn.dataset.loading;
            }
        }, 8000);
    });

    // ─── GLOBAL SEARCH: open palette on click / Enter ──────────────
    const gs = document.getElementById('global-search');
    if (gs) {
        gs.addEventListener('focus', (e) => {
            if (window.innerWidth > 720) {
                e.target.blur();
                openPalette();
            }
        });
    }

    // ─── PWA: register service worker (z auto-update przy kazdej wizycie) ─
    if ('serviceWorker' in navigator && location.protocol !== 'file:') {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/sw.js').then((reg) => {
                // Force check for new SW na kazdej wizycie (omija 24h browser cache)
                reg.update().catch(() => {});
                // Gdy nowa wersja sie aktywuje - przeladuj strone
                reg.addEventListener('updatefound', () => {
                    const newSW = reg.installing;
                    if (!newSW) return;
                    newSW.addEventListener('statechange', () => {
                        if (newSW.state === 'activated' && navigator.serviceWorker.controller) {
                            // Mozna pokazac toast "nowa wersja" - na razie auto-reload jednorazowy
                            if (!sessionStorage.getItem('polcrm_sw_reloaded')) {
                                sessionStorage.setItem('polcrm_sw_reloaded', '1');
                                location.reload();
                            }
                        }
                    });
                });
            }).catch(err => {
                console.warn('SW registration failed:', err);
            });
        });
    }

})();
