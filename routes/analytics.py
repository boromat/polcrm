"""Search Console / GA4 snapshots (on demand)."""

from flask import flash, redirect, url_for

from core import (
    app,
)
from i18n import _

# ═══════════════════════════════════════════════════════════════
#  GSC / GA SYNC
# ═══════════════════════════════════════════════════════════════

@app.route("/api/gsc/sync/<int:company_id>", methods=["POST"])
def api_gsc_sync(company_id):
    import google_sync
    snap, err = google_sync.sync_gsc(company_id)
    if err:
        flash(_("Błąd synchronizacji GSC: %(error)s", error=err), "danger")
    else:
        flash(_("GSC zsynchronizowane (%(clicks)s kliknięć, %(impressions)s wyświetleń).",
                clicks=snap.total_clicks, impressions=snap.total_impressions), "success")
    return redirect(url_for("company_detail", id=company_id) + "#analytics")


@app.route("/api/ga/sync/<int:company_id>", methods=["POST"])
def api_ga_sync(company_id):
    import google_sync
    snap, err = google_sync.sync_ga(company_id)
    if err:
        flash(_("Błąd synchronizacji GA4: %(error)s", error=err), "danger")
    else:
        flash(_("GA4 zsynchronizowane (%(users)s użytkowników, %(sessions)s sesji).",
                users=snap.users, sessions=snap.sessions), "success")
    return redirect(url_for("company_detail", id=company_id) + "#analytics")
