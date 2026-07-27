"""Tests for ``DELETE /api/data/`` — nuke-orbit data reset.

Validates that the endpoint:
1. Returns 200 with correct deletion counts
2. Preserves the user profile (no user row deleted)
3. Deletes in FK-safe order (no IntegrityError)
4. Is idempotent (second call returns all zeros)
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models import Account, Budget, Category, FamilyMember, Goal, ImportBatch, Institution, Transaction, User
from app.auth import require_user

import pytest

# ---------------------------------------------------------------------------
# Fixtures — lightweight SQLite test DB with seeded data
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///./test_delete_all_data.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables, seed data, tear down after each test."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client():
    """TestClient with DB + auth overrides."""
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_user] = lambda: "alex"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_data():
    """Seed a user, institution, account, transactions, batches, goals,
    budgets, and categories — the full FK graph."""
    db = TestSession()
    user = User(
        local_user_sub="alex",
        email="alex@test.com",
        hashed_password="x",
        full_name="Alex Test",
    )
    db.add(user)
    db.flush()

    inst = Institution(name="Test Bank")
    db.add(inst)
    db.flush()

    # Phase 16 — Account.family_member_id is NOT NULL FK; seed the
    # local user's Self row first so the Account INSERT satisfies
    # the constraint. Mirrors the route layer's default-to-Self
    # bootstrap in ``app.routes.shared.get_or_create_family_member_self``.
    self_row = FamilyMember(
        user_id=user.id,
        name="Test Self",
        color="#10b981",
        is_self=True,
        is_archived=False,
    )
    db.add(self_row)
    db.flush()

    account = Account(
        user_id=user.id,
        institution_id=inst.id,
        family_member_id=self_row.id,
        account_name="Checking",
        account_type="checking",
        current_balance=1000.0,
        is_active=True,
    )
    db.add(account)
    db.flush()

    cat = Category(name="Groceries")
    db.add(cat)
    db.flush()

    batch = ImportBatch(
        user_id=user.id,
        account_id=account.id,
        filename="test.csv",
        file_type="csv",
        record_count=3,
    )
    db.add(batch)
    db.flush()

    for i in range(3):
        txn = Transaction(
            account_id=account.id,
            import_batch_id=batch.id,
            category_id=cat.id,
            description=f"Transaction {i}",
            amount=100.0 * (i + 1),
            transaction_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
        )
        db.add(txn)

    goal = Goal(
        user_id=user.id,
        name="Emergency Fund",
        target_amount=10000.0,
        priority=1,
    )
    db.add(goal)

    budget = Budget(
        user_id=user.id,
        category_id=cat.id,
        amount=500.0,
        period="monthly",
    )
    db.add(budget)

    db.commit()

    # Snapshot ids BEFORE closing the session — ORM instances detach on
    # close() and accessing .id on a detached instance raises
    # DetachedInstanceError (SQLAlchemy tries to lazy-load from a dead session).
    ids = {
        "user_id": user.id,
        "account_id": account.id,
        "batch_id": batch.id,
        "goal_id": goal.id,
    }
    db.close()
    return ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_delete_all_data_returns_correct_counts(client, seeded_data):
    """Happy path — returns the exact number of deleted rows."""
    r = client.delete("/api/data/")
    assert r.status_code == 200
    body = r.json()
    assert body["deleted_transactions"] == 3
    assert body["deleted_import_batches"] == 1
    assert body["deleted_goals"] == 1
    assert body["deleted_accounts"] == 1
    assert body["deleted_budgets"] == 1


def test_delete_all_data_preserves_user_profile(client, seeded_data):
    """The user row must survive the nuke."""
    client.delete("/api/data/")
    db = TestSession()
    user = db.query(User).filter(User.local_user_sub == "alex").first()
    assert user is not None
    assert user.full_name == "Alex Test"
    db.close()


def test_delete_all_data_idempotent(client, seeded_data):
    """Second call returns all zeros (nothing left to delete)."""
    client.delete("/api/data/")
    r = client.delete("/api/data/")
    assert r.status_code == 200
    body = r.json()
    assert all(v == 0 for v in body.values())


def test_delete_all_data_empty_database(client):
    """No data to delete — still returns 200 with all zeros."""
    db = TestSession()
    user = User(
        local_user_sub="alex",
        email="alex@test.com",
        hashed_password="x",
    )
    db.add(user)
    db.commit()
    db.close()

    r = client.delete("/api/data/")
    assert r.status_code == 200
    body = r.json()
    assert all(v == 0 for v in body.values())
