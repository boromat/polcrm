"""Authentication helpers: auth mode, password policy, login rate limiting, session binding.

Three modes, chosen with AUTH_MODE:

* ``password`` (default) - e-mail and password, accounts managed in Settings -> Team,
* ``cloudflare`` - identity from the Cloudflare Access header (the app sits behind Access),
* ``profile`` - a profile picker without passwords, for local demos only; refused in production.

The module imports nothing from the app or the database, so it can be unit tested on its own.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque

from i18n import _

MODES = ("password", "cloudflare", "profile")
MIN_PASSWORD_LENGTH = 10


def resolve_auth_mode(env_mode: str, cf_access_enabled: bool, is_production: bool) -> str:
    """AUTH_MODE from the environment. The older CF_ACCESS_ENABLED=true still means "cloudflare"."""
    mode = (env_mode or "").strip().lower() or ("cloudflare" if cf_access_enabled else "password")
    if mode not in MODES:
        raise RuntimeError(f"AUTH_MODE={mode!r} - dozwolone: {', '.join(MODES)}")
    if mode == "profile" and is_production:
        raise RuntimeError("AUTH_MODE=profile (wybór profilu bez hasła) jest tylko do demo - nie w produkcji.")
    return mode


def password_problem(password: str, email: str = "") -> str | None:
    """Why a new password is not acceptable, or None. Length is what matters most."""
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return _("Hasło musi mieć co najmniej %(n)s znaków.", n=MIN_PASSWORD_LENGTH)
    if email and password.strip().lower() == email.strip().lower():
        return _("Hasło nie może być takie samo jak e-mail.")
    return None


def session_fingerprint(password_hash: str) -> str:
    """Bound into the session cookie: changing the password logs out every other session."""
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


class LoginRateLimiter:
    """Failed logins per (IP, e-mail) and per IP in a sliding window. Thread-safe (waitress threads).

    In memory on purpose: one process, two-digit team sizes. A restart clears it, which is fine for
    slowing down password guessing; it is not meant to survive deploys.
    """

    def __init__(self, per_account: int = 5, per_ip: int = 20, window_seconds: int = 15 * 60, clock=time.monotonic):
        self.per_account = per_account
        self.per_ip = per_ip
        self.window = window_seconds
        self.clock = clock
        self._fails: dict[tuple, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key) -> deque:
        q = self._fails[key]
        cutoff = self.clock() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, ip: str, email: str) -> bool:
        with self._lock:
            return (len(self._recent(("acct", ip, email.lower()))) >= self.per_account
                    or len(self._recent(("ip", ip))) >= self.per_ip)

    def failed(self, ip: str, email: str) -> None:
        now = self.clock()
        with self._lock:
            self._fails[("acct", ip, email.lower())].append(now)
            self._fails[("ip", ip)].append(now)

    def succeeded(self, ip: str, email: str) -> None:
        with self._lock:
            self._fails.pop(("acct", ip, email.lower()), None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
