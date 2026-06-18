from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from ..database import get_db
from ..models import Event, Org
from .auth import get_current_org, COOKIE_NAME

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PALETTE = ['#6366f1', '#f59e0b', '#10b981', '#ec4899', '#3b82f6', '#8b5cf6', '#ef4444', '#14b8a6']


def _skill_filter(org_id, since=None):
    """Match both legacy skill_used events and new tool_used events where tool=Skill."""
    tool_expr = func.json_extract_path_text(Event.properties, 'tool')
    filters = [
        Event.org_id == org_id,
        or_(
            Event.event == 'skill_used',
            (Event.event == 'tool_used') & (tool_expr == 'Skill'),
        ),
    ]
    if since:
        filters.append(Event.timestamp >= since)
    return filters


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), days: int = Query(default=30, ge=1, le=90)):
    org = get_current_org(request, db)
    if not org:
        return RedirectResponse(url="/login", status_code=303)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total = (
        db.query(func.count(Event.id))
        .filter(Event.org_id == org.id, Event.timestamp >= since)
        .scalar() or 0
    )

    skill_name_expr = func.json_extract_path_text(Event.properties, 'skill')

    unique_skills = (
        db.query(func.count(func.distinct(skill_name_expr)))
        .filter(*_skill_filter(org.id, since), skill_name_expr.isnot(None))
        .scalar() or 0
    )

    unique_projects = (
        db.query(func.count(func.distinct(Event.project)))
        .filter(Event.org_id == org.id, Event.project.isnot(None), Event.timestamp >= since)
        .scalar() or 0
    )

    top_skills = (
        db.query(skill_name_expr.label("skill"), func.count(Event.id).label("count"))
        .filter(*_skill_filter(org.id, since), skill_name_expr.isnot(None))
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
        .filter(*_skill_filter(org.id, since), skill_name_expr.in_(top_skill_names))
        .group_by(skill_name_expr, func.date(Event.timestamp))
        .order_by(func.date(Event.timestamp))
        .all()
    )

    # Tool breakdown (all tool_used events)
    tool_expr = func.json_extract_path_text(Event.properties, 'tool')
    tool_breakdown = (
        db.query(tool_expr.label("tool"), func.count(Event.id).label("count"))
        .filter(
            Event.org_id == org.id,
            Event.event == 'tool_used',
            tool_expr.isnot(None),
            Event.timestamp >= since,
        )
        .group_by(tool_expr)
        .order_by(desc("count"))
        .limit(15)
        .all()
    )

    # Top bash commands
    cmd_expr = func.json_extract_path_text(Event.properties, 'cmd')
    top_bash_commands = (
        db.query(cmd_expr.label("cmd"), func.count(Event.id).label("count"))
        .filter(
            Event.org_id == org.id,
            Event.event == 'tool_used',
            tool_expr == 'Bash',
            cmd_expr.isnot(None),
            Event.timestamp >= since,
        )
        .group_by(cmd_expr)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )

    # Top file extensions edited
    ext_expr = func.json_extract_path_text(Event.properties, 'ext')
    top_extensions = (
        db.query(ext_expr.label("ext"), func.count(Event.id).label("count"))
        .filter(
            Event.org_id == org.id,
            Event.event == 'tool_used',
            tool_expr.in_(['Edit', 'Write']),
            ext_expr.isnot(None),
            Event.timestamp >= since,
        )
        .group_by(ext_expr)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )

    # Build full date list
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
        .filter(Event.org_id == org.id, Event.project.isnot(None), Event.timestamp >= since)
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
            "tool_breakdown": tool_breakdown,
            "top_bash_commands": top_bash_commands,
            "top_extensions": top_extensions,
            "recent": recent,
            "days": days,
        },
    )
