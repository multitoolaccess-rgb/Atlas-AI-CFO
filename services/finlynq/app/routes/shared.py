"""Phase-F5 lift — Finlynq's local-user lookup helper.

Verbatim lift of ``services/rules-service/app/routes/shared.py::get_or_create_local_user``
ONLY — no ``forward_detail`` (Finlynq is not a forwarder) and no
``get_or_create_institution`` (Finlynq has no account-create route
that names an institution today).

The mirror ``app/auth.py`` ensures the ``fc_session`` cookie
rules-service mints is accepted by Finlynq's ``Depends(require_user)``
dep on the same JWT secret + iss + sub. This mirror of
``get_or_create_local_user`` ensures the JWT's ``sub`` claim maps to
a real ``User.id`` row on first request — without it, the F5
aggregator at ``/state/summary`` cannot scope queries by FK
(``Account.user_id``, ``Goal.user_id``, ``Transaction.account_id``
joins, ``ImportBatch.user_id``).

Cross-DB invariant: this helper writes to the SAME ``users`` table
rules-service's mirror writes. Two writes on one row would race the
UNIQUE index on ``local_user_sub`` — conftest fixtures isolate each
test's bind before any route call, so the race is bounded by the
test-isolation contract.

Phase F5 follow-up (deferred): Finlynq may eventually own the local
user's creation (per Phase-F5+ master-plan); today both services share
the responsibility because they share the table.
"""
from sqlalchemy.orm import Session

from app.models import User


def get_or_create_local_user(db: Session, sub: str) -> User:
    """Look up the per-request local user by JWT ``sub``; create on first request.

    Mirror of rules-service/app/routes/shared.py::get_or_create_local_user.
    Both services share ``local_user_sub`` columns on the SAME
    ``users`` table — first writer wins, subsequent reads find the row.
    """
    user = db.query(User).filter(User.local_user_sub == sub).first()
    if not user:
        user = User(
            local_user_sub=sub,
            email=sub,
            hashed_password="auth-via-jwt-cookie-no-password",
            full_name=sub.split("@", 1)[0].title() or sub,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
