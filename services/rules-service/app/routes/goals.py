"""Phase 8 — ``/api/goals/`` CRUD (auth-enforced).

Mirrors the ``Account`` route shape (Phase 6 auth + Phase 7 partial-update
+ soft-delete) but with one twist: the LOCAL USER may own multiple
goals, so DELETE is a soft-archive (``is_archived=True``) instead of a
hard delete. Soft-delete preserves the row for historical
``DashboardSummary`` snapshots — if a future dashboard renderer pins
the goal by id, archiving keeps the row readable.

Endpoints:

- ``GET    /api/goals/``         — list the local user's **non-archived** goals.
- ``POST   /api/goals/``         — create a goal (whitelisted fields).
- ``GET    /api/goals/{goal_id}`` — fetch a single goal (404 if missing).
- ``PUT    /api/goals/{goal_id}`` — partial update (whitelisted fields).
- ``DELETE /api/goals/{goal_id}`` — soft-archive (flips ``is_archived=True``).

All endpoints require a valid JWT cookie (``Depends(require_user)``).
The local-user identity comes from ``settings.local_user`` via
``get_or_create_local_user``.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_user
from app.database import get_db
from app.models import Goal
from app.routes.shared import get_or_create_local_user
from app.schemas import GoalCreate, GoalResponse, GoalUpdate

router = APIRouter(prefix="/api/goals", tags=["goals"])


def _get_user_goal(db: Session, goal_id: int, user_id: int) -> Goal:
    """Fetch a single Goal owned by the local user. Raises 404 if missing.

    Centralized 404 helper — the ``GET / PUT / DELETE`` endpoints all
    need the same query-by-id-and-user lookup, and duplicating it
    three times would let a future refactor diverge (e.g. one path
    forgetting the ``user_id`` filter and leaking rows from other
    users). Centralizing keeps the scope-invariants in one place.
    """
    goal = (
        db.query(Goal)
        .filter(Goal.id == goal_id, Goal.user_id == user_id)
        .first()
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.get("/", response_model=List[GoalResponse])
async def list_goals(
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """List the local user's non-archived goals, ordered by priority DESC
    (highest first), then by ``created_at`` ASC.

    **Phase 15 — auto-seed ``Default $15M Goal``**

    If the user has *never* had any goal — checked across
    ``is_archived=True`` rows too, so a user who archived the seed
    goal counts as "had one" and is NOT re-seeded — insert the
    default $15M / 20y / priority=0 anchor before returning the
    list. The seed:

    - makes the dashboard's FinancialPlans panel render ≥1 goal
      immediately on first load,
    - is fully editable from the Goals page (it's a regular row,
      not a synthetic placeholder),
    - is idempotent: once ANY goal row exists for the user
      (active or archived) the seed branch is skipped forever.

    The seed fence (``once-only``) is intentional. If a user
    deliberately archives/deletes their default goal we honour
    their intent; resurrection on a refresh would be confusing.
    """
    local_user = get_or_create_local_user(db, _current_user)
    has_any = (
        db.query(Goal)
        .filter(Goal.user_id == local_user.id)
        .first()
    )
    if has_any is None:
        # First-time visit. Insert the historical default so the
        # dashboard isn't empty. Same $15M / 20y anchor that
        # used to live on ``User.target_net_worth`` /
        # ``User.time_horizon_years`` — now drives the Goals
        # page + FinancialPlans naturally via the existing
        # ``user_goals`` field on :class:`DashboardSummary`.
        seed = Goal(
            user_id=local_user.id,
            name="Default $15M Goal",
            target_amount=15_000_000.0,
            target_date=None,
            horizon_years=20,
            priority=0,
            is_archived=False,
            notes=(
                "Anchor goal seeded automatically on first visit. "
                "Edit it from the Goals page, or archive it to skip."
            ),
        )
        db.add(seed)
        db.commit()
        db.refresh(seed)
    goals = (
        db.query(Goal)
        .filter(Goal.user_id == local_user.id, Goal.is_archived.is_(False))
        .order_by(Goal.priority.desc(), Goal.created_at.asc())
        .all()
    )
    return goals


@router.post("/", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Create a goal owned by the local user.

    Same ``Pydantic + model_dump`` whitelist pattern as the
    ``users.update_profile`` endpoint (Phase 7 release): declared
    fields on ``GoalCreate`` are written verbatim; undeclared fields
    (e.g. ``user_id``, ``is_archived``, ``id``) are silently dropped
    so a client cannot escalate ownership or pre-archive the goal.
    """
    local_user = get_or_create_local_user(db, _current_user)
    _MUTABLE_FIELDS = frozenset(GoalCreate.model_fields.keys())
    patch = {
        field: value
        for field, value in payload.model_dump().items()
        if field in _MUTABLE_FIELDS
    }
    # Identity-bearing fields the route sets explicitly (NOT through patch):
    patch["user_id"] = local_user.id
    patch["is_archived"] = False
    goal = Goal(**patch)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Fetch a single goal by id, scoped to the local user."""
    local_user = get_or_create_local_user(db, _current_user)
    return _get_user_goal(db, goal_id, local_user.id)


@router.put("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Partial update of a goal. Only fields declared on ``GoalUpdate``
    are written; any key not declared is silently dropped by
    ``model_dump()`` (Phase 7 whitelist contract — clients cannot
    escalate or re-tie ownership via PUT). Empty-string guard mirrors
    Phase 7's ``account_name`` defensive regression: an empty
    ``name`` would round-trip a row with ``name=""`` and confuse
    the projection engine's goal lookup.
    """
    local_user = get_or_create_local_user(db, _current_user)
    goal = _get_user_goal(db, goal_id, local_user.id)
    _MUTABLE_FIELDS = frozenset(GoalUpdate.model_fields.keys())
    patch = {
        field: value
        for field, value in payload.model_dump().items()
        if value is not None and field in _MUTABLE_FIELDS
    }
    # Defensive regression — `name=""` would break the FE's
    # `summary.user_goals[0]?.name` chip. Reject before `setattr`.
    if "name" in patch:
        cleaned = (patch["name"] or "").strip()
        if not cleaned:
            raise HTTPException(
                status_code=400,
                detail="Goal name must not be empty.",
            )
        patch["name"] = cleaned
    for field, value in patch.items():
        setattr(goal, field, value)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    _current_user: str = Depends(require_user),
):
    """Soft-archive a goal — flips ``is_archived=True`` so the row stops
    appearing in ``list_goals`` and the dashboard summary. The row
    stays in the DB so historical ``GoalResponse`` references (rendered
    by id) can still resolve. Idempotent: archiving twice is a no-op
    (no DB write, 204 No Content either way).
    """
    local_user = get_or_create_local_user(db, _current_user)
    goal = _get_user_goal(db, goal_id, local_user.id)
    if not goal.is_archived:
        goal.is_archived = True
        db.add(goal)
        db.commit()
    # 204 No Content — no body returned (same as DELETE /api/accounts/{id}).
    return None
