from collections import defaultdict
from datetime import datetime, timedelta, timezone
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func, desc
from .database import SessionLocal
from .models import Event, Org

mcp = FastMCP(
    "lumen",
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _resolve_org(ctx: Context):
    auth = ctx.request_context.request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None, None
    api_key = auth.removeprefix("Bearer ").strip()
    db = SessionLocal()
    org = db.query(Org).filter(Org.api_key == api_key).first()
    if not org:
        db.close()
        return None, None
    return org, db


@mcp.tool()
async def track_event(skill: str, project: str = "", ctx: Context = None) -> str:
    """Track a skill usage event in Lumen."""
    org, db = _resolve_org(ctx)
    if not org:
        return "error: invalid API key"
    try:
        event = Event(
            org_id=org.id,
            event="skill_used",
            properties={"skill": skill},
            project=project or None,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()
        return f"tracked: {skill}"
    finally:
        db.close()


@mcp.tool()
async def get_top_skills(days: int = 30, ctx: Context = None) -> list[dict]:
    """Get skills ranked by usage count over the given number of days."""
    org, db = _resolve_org(ctx)
    if not org:
        return [{"error": "invalid API key"}]
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        skill_expr = func.json_extract_path_text(Event.properties, "skill")
        rows = (
            db.query(skill_expr.label("skill"), func.count(Event.id).label("count"))
            .filter(
                Event.org_id == org.id,
                Event.event == "skill_used",
                skill_expr.isnot(None),
                Event.timestamp >= since,
            )
            .group_by(skill_expr)
            .order_by(desc("count"))
            .all()
        )
        return [{"skill": r.skill, "count": r.count} for r in rows]
    finally:
        db.close()


@mcp.tool()
async def get_stats(days: int = 30, ctx: Context = None) -> dict:
    """Get summary stats: total events, unique skills, unique projects."""
    org, db = _resolve_org(ctx)
    if not org:
        return {"error": "invalid API key"}
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        skill_expr = func.json_extract_path_text(Event.properties, "skill")

        total = (
            db.query(func.count(Event.id))
            .filter(Event.org_id == org.id, Event.timestamp >= since)
            .scalar() or 0
        )
        unique_skills = (
            db.query(func.count(func.distinct(skill_expr)))
            .filter(Event.org_id == org.id, Event.event == "skill_used", Event.timestamp >= since)
            .scalar() or 0
        )
        unique_projects = (
            db.query(func.count(func.distinct(Event.project)))
            .filter(Event.org_id == org.id, Event.project.isnot(None), Event.timestamp >= since)
            .scalar() or 0
        )
        return {
            "days": days,
            "total_events": total,
            "unique_skills": unique_skills,
            "unique_projects": unique_projects,
        }
    finally:
        db.close()
