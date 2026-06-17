from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, String
from ..database import get_db
from ..models import Event, Org
from .auth import get_current_org, COOKIE_NAME

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PALETTE = ['#6366f1', '#f59e0b', '#10b981', '#ec4899', '#3b82f6', '#8b5cf6', '#ef4444', '#14b8a6']


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), days: int = Query(default=30, ge=1, le=90)):
    org = get_current_org(request, db)
    if not org:
        return RedirectResponse(url="/login", status_code=303)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total = db.query(func.count(Event.id)).filter(Event.org_id == org.id).scalar() or 0

    skill_name_expr = cast(Event.properties['skill'], String)

    unique_skills = (
        db.query(func.count(func.distinct(skill_name_expr)))
        .filter(
            Event.org_id == org.id,
            Event.event == 'skill_used',
            skill_name_expr.isnot(None),
        )
        .scalar() or 0
    )

    unique_projects = (
        db.query(func.count(func.distinct(Event.project)))
        .filter(Event.org_id == org.id, Event.project.isnot(None))
        .scalar() or 0
    )

    top_skills = (
        db.query(skill_name_expr.label("skill"), func.count(Event.id).label("count"))
        .filter(
            Event.org_id == org.id,
            Event.event == 'skill_used',
            skill_name_expr.isnot(None),
        )
        .group_by(skill_name_expr)
        .order_by(desc("count"))
        .limit(20)
        .all()
    )

    # Per-skill daily counts for trend chart (top 8 skills only for readability)
    top_skill_names = [row.skill for row in top_skills[:8]]
    skill_daily_rows = (
        db.query(
            skill_name_expr.label("skill"),
            func.date(Event.timestamp).label("date"),
            func.count(Event.id).label("count"),
        )
        .filter(
            Event.org_id == org.id,
            Event.event == 'skill_used',
            skill_name_expr.in_(top_skill_names),
            Event.timestamp >= since,
        )
        .group_by(skill_name_expr, func.date(Event.timestamp))
        .order_by(func.date(Event.timestamp))
        .all()
    )

    # Build full 30-day date list
    date_range = []
    d = since.date()
    end = datetime.now(timezone.utc).date()
    while d <= end:
        date_range.append(d)
        d += timedelta(days=1)

    trend_labels = [dt.strftime('%b %d') for dt in date_range]
    date_strs = [str(dt) for dt in date_range]

    skill_day_map = defaultdict(lambda: defaultdict(int))
    for row in skill_daily_rows:
        skill_day_map[row.skill][str(row.date)] += row.count

    trend_datasets = [
        {
            "label": skill,
            "data": [skill_day_map[skill].get(d, 0) for d in date_strs],
            "borderColor": PALETTE[i % len(PALETTE)],
            "backgroundColor": PALETTE[i % len(PALETTE)] + "26",
            "borderWidth": 2,
            "pointRadius": 2,
            "fill": False,
            "tension": 0.3,
        }
        for i, skill in enumerate(top_skill_names)
    ]

    top_projects = (
        db.query(Event.project, func.count(Event.id).label("count"))
        .filter(Event.org_id == org.id, Event.project.isnot(None))
        .group_by(Event.project)
        .order_by(desc("count"))
        .limit(8)
        .all()
    )

    recent = (
        db.query(Event)
        .filter(Event.org_id == org.id)
        .order_by(desc(Event.created_at))
        .limit(25)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "org": org,
            "total": total,
            "unique_skills": unique_skills,
            "unique_projects": unique_projects,
            "top_skills": top_skills,
            "trend_labels": trend_labels,
            "trend_datasets": trend_datasets,
            "top_projects": top_projects,
            "recent": recent,
            "days": days,
        },
    )
