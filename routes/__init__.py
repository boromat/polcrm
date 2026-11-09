"""Route modules. Importing this package registers every route on core.app.

Routes are attached to the single Flask app (not blueprints), so endpoint names, URLs and
`url_for()` calls in templates are the same as before the split."""

from routes import (
    analytics,  # noqa: F401
    assistant,  # noqa: F401
    audits,  # noqa: F401
    auth,  # noqa: F401
    calendar,  # noqa: F401
    companies,  # noqa: F401
    content,  # noqa: F401
    contracts,  # noqa: F401
    credentials,  # noqa: F401
    dashboard,  # noqa: F401
    emails,  # noqa: F401
    finances,  # noqa: F401
    knowledge,  # noqa: F401
    leads,  # noqa: F401
    notes,  # noqa: F401
    offers,  # noqa: F401
    projects,  # noqa: F401
    settings,  # noqa: F401
    tasks,  # noqa: F401
    team,  # noqa: F401
    whiteboard,  # noqa: F401
)
