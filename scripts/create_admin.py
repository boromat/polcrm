"""Create (or promote) an administrator account from the command line.

    python scripts/create_admin.py --name "Anna Nowak" --email anna@example.com

The password is read with a hidden prompt (never from the command line, so it does not land in
shell history). Use it on a server instead of the /setup page, or to regain access.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth  # noqa: E402
from app import app  # noqa: E402
from models import User, db  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Create or promote a PolCRM administrator.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()

    password = getpass.getpass("Hasło: ")
    if password != getpass.getpass("Powtórz hasło: "):
        sys.exit("Hasła nie są takie same.")
    problem = auth.password_problem(password, email)
    if problem:
        sys.exit(problem)

    with app.app_context():
        user = User.query.filter(db.func.lower(User.email) == email).first() or User(email=email)
        user.name = args.name.strip()
        user.initials = "".join(p[0] for p in user.name.split()[:2]).upper()
        user.role = "admin"
        user.is_active = True
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Administrator gotowy: {user.name} <{user.email}>")


if __name__ == "__main__":
    main()
