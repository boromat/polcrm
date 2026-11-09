"""Google OAuth + GSC + GA4 sync. On-demand (no cron)."""

from datetime import date, timedelta

from i18n import _
from models import db, Settings, Company, GscSnapshot, GaSnapshot


SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]


def _load_oauth_flow(redirect_uri):
    """Build a google_auth_oauthlib Flow. Lazy import to avoid hard dep."""
    from google_auth_oauthlib.flow import Flow
    s = Settings.get()
    if not s.google_oauth_client_id or not s.google_oauth_client_secret:
        return None
    client_config = {
        "web": {
            "client_id": s.google_oauth_client_id,
            "client_secret": s.google_oauth_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = redirect_uri
    return flow


def get_authorization_url(redirect_uri):
    flow = _load_oauth_flow(redirect_uri)
    if not flow:
        return None, None
    url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return url, state


def exchange_code(redirect_uri, code):
    flow = _load_oauth_flow(redirect_uri)
    if not flow:
        return None
    flow.fetch_token(code=code)
    creds = flow.credentials
    s = Settings.get()
    if creds.refresh_token:
        s.gsc_refresh_token = creds.refresh_token
        s.ga_refresh_token = creds.refresh_token
        db.session.commit()
    return creds


def _build_credentials():
    from google.oauth2.credentials import Credentials
    s = Settings.get()
    if not s.gsc_refresh_token or not s.google_oauth_client_id:
        return None
    return Credentials(
        token=None,
        refresh_token=s.gsc_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=s.google_oauth_client_id,
        client_secret=s.google_oauth_client_secret,
        scopes=SCOPES,
    )


def sync_gsc(company_id, days=28):
    """Pull last N days from Search Console into a snapshot. Returns snapshot or None."""
    from googleapiclient.discovery import build

    company = db.session.get(Company, company_id)
    if not company or not company.gsc_site_url:
        return None, _("Firma nie ma ustawionego gsc_site_url.")

    creds = _build_credentials()
    if not creds:
        return None, _("Brak konfiguracji OAuth (zautoryzuj w Ustawieniach).")

    end = date.today() - timedelta(days=2)  # GSC has 2-day lag
    start = end - timedelta(days=days)

    try:
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        # Totals
        totals_req = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": [],
            "rowLimit": 1,
        }
        totals = service.searchanalytics().query(siteUrl=company.gsc_site_url, body=totals_req).execute()
        row0 = (totals.get("rows") or [{}])[0]
        clicks = int(row0.get("clicks", 0))
        impressions = int(row0.get("impressions", 0))
        ctr = float(row0.get("ctr", 0))
        position = float(row0.get("position", 0))

        # Top queries
        q_req = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 20,
        }
        q_resp = service.searchanalytics().query(siteUrl=company.gsc_site_url, body=q_req).execute()
        top_queries = [
            {
                "query": r["keys"][0],
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "ctr": round(float(r.get("ctr", 0)) * 100, 2),
                "position": round(float(r.get("position", 0)), 1),
            }
            for r in q_resp.get("rows", [])
        ]

        # Top pages
        p_req = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["page"],
            "rowLimit": 20,
        }
        p_resp = service.searchanalytics().query(siteUrl=company.gsc_site_url, body=p_req).execute()
        top_pages = [
            {
                "page": r["keys"][0],
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
            }
            for r in p_resp.get("rows", [])
        ]

    except Exception as exc:
        return None, _("Błąd GSC API: %(error)s", error=exc)

    snap = GscSnapshot(
        company_id=company.id,
        date_range_start=start,
        date_range_end=end,
        total_clicks=clicks,
        total_impressions=impressions,
        avg_ctr=round(ctr * 100, 2),
        avg_position=round(position, 1),
    )
    snap.top_queries = top_queries
    snap.top_pages = top_pages
    db.session.add(snap)
    db.session.commit()
    return snap, None


def sync_ga(company_id, days=28):
    """Pull last N days from GA4 into a snapshot."""
    from googleapiclient.discovery import build

    company = db.session.get(Company, company_id)
    if not company or not company.ga_property_id:
        return None, _("Firma nie ma ustawionego ga_property_id.")

    creds = _build_credentials()
    if not creds:
        return None, _("Brak konfiguracji OAuth.")

    end = date.today()
    start = end - timedelta(days=days)

    try:
        service = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)
        property_name = f"properties/{company.ga_property_id}"

        totals_body = {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "metrics": [
                {"name": "activeUsers"},
                {"name": "sessions"},
                {"name": "engagedSessions"},
                {"name": "conversions"},
                {"name": "averageSessionDuration"},
            ],
        }
        resp = service.properties().runReport(property=property_name, body=totals_body).execute()
        row = resp.get("rows", [{}])[0] if resp.get("rows") else {}
        vals = row.get("metricValues", [])
        def _g(i):
            try:
                return vals[i].get("value", "0")
            except IndexError:
                return "0"
        users = int(float(_g(0)))
        sessions = int(float(_g(1)))
        engaged = int(float(_g(2)))
        conversions = int(float(_g(3)))
        avg_time = float(_g(4))

        # Top sources
        src_body = {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "sessions"}],
            "limit": 10,
        }
        src_resp = service.properties().runReport(property=property_name, body=src_body).execute()
        top_sources = [
            {
                "source": (r.get("dimensionValues") or [{}])[0].get("value", ""),
                "sessions": int(float((r.get("metricValues") or [{}])[0].get("value", "0"))),
            }
            for r in src_resp.get("rows", [])
        ]

        # Top pages
        page_body = {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "sessions"}],
            "limit": 20,
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        }
        page_resp = service.properties().runReport(property=property_name, body=page_body).execute()
        top_pages = [
            {
                "page": (r.get("dimensionValues") or [{}])[0].get("value", ""),
                "sessions": int(float((r.get("metricValues") or [{}])[0].get("value", "0"))),
            }
            for r in page_resp.get("rows", [])
        ]

    except Exception as exc:
        return None, _("Błąd GA4 API: %(error)s", error=exc)

    snap = GaSnapshot(
        company_id=company.id,
        date_range_start=start,
        date_range_end=end,
        users=users,
        sessions=sessions,
        engaged_sessions=engaged,
        conversions=conversions,
        avg_engagement_time=round(avg_time, 1),
    )
    snap.top_sources = top_sources
    snap.top_pages = top_pages
    db.session.add(snap)
    db.session.commit()
    return snap, None
