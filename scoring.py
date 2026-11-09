"""
Auto-scoring engine for marketing audits.

Uses Google Places data (already stored on Company) and
Google PageSpeed Insights API (free, requires same API key as Maps).
"""

import logging

import requests

log = logging.getLogger(__name__)


PAGESPEED_TIMEOUT = 15  # seconds


def calculate_all_scores(company, api_key=None):
    """Calculate all 5 scores for a company. Returns dict with scores and pagespeed data."""
    pagespeed = {}
    if company.website and api_key:
        pagespeed = fetch_pagespeed(company.website, api_key)

    scores = {
        "visibility": score_visibility(company),
        "offer": score_offer(company, pagespeed),
        "trust": score_trust(company),
        "conversion": score_conversion(company, pagespeed),
        "analytics": score_analytics(company, pagespeed),
    }

    vals = [v for v in scores.values() if v is not None]
    scores["overall"] = round(sum(vals) / len(vals), 1) if vals else None
    scores["pagespeed"] = pagespeed

    return scores


# ── Individual score functions ────────────────────────────────

def score_visibility(company):
    """Widoczność online (1-5)."""
    pts = 0
    if company.place_id:
        pts += 1
    if company.website:
        pts += 1
    if company.rating and company.rating >= 4.0:
        pts += 1
    if company.user_ratings_total and company.user_ratings_total >= 10:
        pts += 1
    if company.business_status == "OPERATIONAL":
        pts += 1
    return max(1, min(5, pts))


def score_offer(company, pagespeed=None):
    """Oferta i komunikacja wartości (1-5)."""
    pts = 0
    if company.phone or company.intl_phone:
        pts += 1
    if company.address:
        pts += 1
    if company.primary_type:
        pts += 1
    # opening_hours info is in the Places data but we check phone/address as proxy
    if company.google_maps_url:
        pts += 1
    if pagespeed and pagespeed.get("seo_score", 0) >= 70:
        pts += 1
    return max(1, min(5, pts))


def score_trust(company):
    """Zaufanie i społeczny dowód słuszności (1-5)."""
    total = company.user_ratings_total or 0
    if total >= 50:
        base = 4
    elif total >= 20:
        base = 3
    elif total >= 10:
        base = 2
    else:
        base = 1

    if company.rating and company.rating >= 4.5:
        base += 1

    return max(1, min(5, base))


def score_conversion(company, pagespeed=None):
    """Konwersja (1-5)."""
    if not company.website:
        return 1

    mobile = pagespeed.get("mobile_score") if pagespeed else None
    if mobile is None:
        return 2  # fallback - has site but can't measure

    if mobile >= 90:
        return 5
    if mobile >= 70:
        return 4
    if mobile >= 50:
        return 3
    if mobile >= 30:
        return 2
    return 1


def score_analytics(company, pagespeed=None):
    """Analityka i mierzenie (1-5)."""
    if not company.website:
        return 1
    # Without scraping the page, we can't detect GA/GTM reliably
    # Fallback: if they have a site, assume basic (2)
    return 2


# ── PageSpeed Insights ────────────────────────────────────────

def fetch_pagespeed(url, api_key):
    """
    Call Google PageSpeed Insights API v5.
    Returns dict with mobile_score, desktop_score, seo_score, and raw metrics.
    Returns empty dict on failure.
    """
    if not url or not api_key:
        return {}

    # Ensure URL has protocol
    if not url.startswith("http"):
        url = "https://" + url

    result = {}

    for strategy in ("mobile", "desktop"):
        try:
            resp = requests.get(
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params={
                    "url": url,
                    "key": api_key,
                    "strategy": strategy,
                    "category": ["performance", "seo"],
                },
                timeout=PAGESPEED_TIMEOUT,
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            lighthouse = data.get("lighthouseResult", {})
            categories = lighthouse.get("categories", {})

            perf = categories.get("performance", {})
            seo = categories.get("seo", {})

            score_key = f"{strategy}_score"
            result[score_key] = int(perf.get("score", 0) * 100)

            if strategy == "mobile":
                result["seo_score"] = int(seo.get("score", 0) * 100)

                # Extract core web vitals
                audits = lighthouse.get("audits", {})
                result["fcp"] = audits.get("first-contentful-paint", {}).get("displayValue", "")
                result["lcp"] = audits.get("largest-contentful-paint", {}).get("displayValue", "")
                result["cls"] = audits.get("cumulative-layout-shift", {}).get("displayValue", "")

        except requests.exceptions.Timeout:
            log.warning("PageSpeed timeout for %s (%s)", url, strategy)
        except Exception as exc:
            log.warning("PageSpeed error for %s (%s): %s", url, strategy, exc)

    return result


# ── Competitor scoring ────────────────────────────────────────

def score_competitor(competitor):
    """Quick score for a competitor (visibility + trust only)."""
    # Visibility
    vis = 0
    if competitor.place_id:
        vis += 1
    if competitor.website:
        vis += 1
    if competitor.rating and competitor.rating >= 4.0:
        vis += 1
    if competitor.user_ratings_total and competitor.user_ratings_total >= 10:
        vis += 1
    vis = max(1, min(5, vis))

    # Trust
    total = competitor.user_ratings_total or 0
    trust = 1
    if total >= 50:
        trust = 4
    elif total >= 20:
        trust = 3
    elif total >= 10:
        trust = 2
    if competitor.rating and competitor.rating >= 4.5:
        trust = min(5, trust + 1)

    return vis, trust
