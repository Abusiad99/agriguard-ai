"""`python -m app.tools.set_role` - the command-line way to make the first admin.

Uses the test suite's in-memory SQLite session; the accounts are SYNTHETIC."""
from __future__ import annotations

from sqlalchemy import select

from app.infrastructure.db.models import AuditLogModel
from app.tools import set_role as tool

PASSWORD = "Str0ngPass!"


def _register(client, email):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Role Test"})
    assert r.status_code == 201, r.text


def _token(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_promote_to_admin_applies_on_the_next_request_and_is_audited(client, db_session, capsys):
    _register(client, "first-admin@example.com")
    headers = _token(client, "first-admin@example.com")
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403   # a new account is a farmer

    code = tool.main(["First-Admin@Example.com", "admin"], session_factory=lambda: db_session)
    assert code == 0 and "changed from farmer to admin" in capsys.readouterr().out
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 200   # same token, new role

    entry = db_session.execute(select(AuditLogModel).where(AuditLogModel.action == "set_role_cli")).scalar_one()
    assert entry.actor_user_id is None and entry.metadata_json == {"old_role": "farmer", "new_role": "admin"}

    assert tool.main(["first-admin@example.com", "farmer"], session_factory=lambda: db_session) == 0
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403   # demoted again


def test_unknown_account_and_unchanged_role(client, db_session, capsys):
    assert tool.main(["nobody@example.com", "admin"], session_factory=lambda: db_session) == 1
    assert "No account" in capsys.readouterr().out
    _register(client, "farmer@example.com")
    assert tool.main(["farmer@example.com", "farmer"], session_factory=lambda: db_session) == 0
    assert "No change" in capsys.readouterr().out
    assert db_session.execute(select(AuditLogModel).where(AuditLogModel.action == "set_role_cli")).first() is None


def test_rejects_unknown_roles(client, db_session, capsys):
    try:
        tool.main(["farmer@example.com", "superuser"], session_factory=lambda: db_session)
    except SystemExit as exc:
        assert exc.code == 2
    assert "invalid choice" in capsys.readouterr().err
