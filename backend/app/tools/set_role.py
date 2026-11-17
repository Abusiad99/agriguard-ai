"""
Change an account's role from the server's command line. This is how the first admin of a
new installation is made; after that, admins can change roles in the app (Admin -> Users).

    python -m app.tools.set_role someone@example.com admin
    python -m app.tools.set_role someone@example.com farmer

With Docker (from the repository's docker folder):

    docker compose exec backend python -m app.tools.set_role someone@example.com admin

The account must exist already: register it in the app first. Roles: farmer, agronomist,
admin. No password is passed or printed. The change is written to the audit log with no
actor (server command line).
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.domain.entities.user import UserRole
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.repositories.audit_log_repository import SqlAlchemyAuditLogRepository
from app.infrastructure.repositories.user_repository import SqlAlchemyUserRepository

ROLES = [r.value for r in UserRole]


def set_role(db: Session, email: str, role: str) -> tuple[str, str]:
    """Set the role of the account with this e-mail address. Returns (old_role, new_role).
    Raises LookupError if there is no such account."""
    new_role = UserRole(role)
    users = SqlAlchemyUserRepository(db)
    user = users.get_by_email(email.strip())
    if user is None:
        raise LookupError(f"No account with the e-mail address {email.strip()!r}. Register it in the app first.")
    old_role = user.role
    if old_role != new_role:
        user.role = new_role
        users.update(user)
        SqlAlchemyAuditLogRepository(db).log(None, "set_role_cli", "user", user.id,
                                             {"old_role": old_role.value, "new_role": new_role.value})
    return old_role.value, new_role.value


def main(argv: Optional[list] = None, session_factory: Callable[[], Session] = SessionLocal) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.set_role",
                                     description="Change the role of an existing account.")
    parser.add_argument("email", help="e-mail address the account was registered with")
    parser.add_argument("role", choices=ROLES)
    args = parser.parse_args(argv)

    db = session_factory()
    try:
        old_role, new_role = set_role(db, args.email, args.role)
    except LookupError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        db.close()
    if old_role == new_role:
        print(f"No change: {args.email.strip()} already has the role {new_role}.")
    else:
        print(f"OK: {args.email.strip()} changed from {old_role} to {new_role}. The server applies it "
              "to the next request; reload the app page to see the matching menu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
