"""REST endpoints. /api/stats returns a zeroed, idle snapshot when no
orchestrator is wired up yet, so the dashboard has something real to render
from the very first milestone instead of dying on a 404.
"""

from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from .. import paths
from ..preferences.store import DEFAULTS as PREFS_DEFAULTS
from .schemas import KBEntryUpdate, PreferencesUpdate, ProfileUpdate, QuestionAnswerRequest, SessionStartRequest

router = APIRouter()


def _get_kb_store(request: Request):
    return request.app.state.kb_store


_EMPTY_STATS = {
    "jobs_scanned": 0,
    "jobs_matched": 0,
    "applications_submitted": 0,
    "applications_needing_input": 0,
    "external_applications_collected": 0,
    "questions_learned_total": 0,
    "current_activity": "Idle",
    "progress_percent": 0,
    "session_status": "idle",
}


@router.get("/stats")
def get_stats(request: Request):
    orchestrator = request.app.state.orchestrator
    if orchestrator is None:
        return _EMPTY_STATS
    return orchestrator.get_stats()


@router.get("/health")
def health():
    return {"ok": True}


# ── session control ──────────────────────────────────────────────

@router.post("/session/start")
def start_session(body: SessionStartRequest, request: Request):
    orchestrator = request.app.state.orchestrator
    if orchestrator is None:
        raise HTTPException(500, "Session orchestrator is not configured.")
    try:
        ok, message = orchestrator.start(
            email=body.email, password=body.password, jobs_target=body.jobs_target,
            role=body.role, location=body.location, experience=body.experience,
            job_age=body.job_age, portal=body.portal,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not ok:
        raise HTTPException(409, message)
    return {"ok": True, "message": message}


@router.post("/session/stop")
def stop_session(request: Request):
    orchestrator = request.app.state.orchestrator
    if orchestrator is None:
        raise HTTPException(500, "Session orchestrator is not configured.")
    ok, message = orchestrator.stop()
    if not ok:
        raise HTTPException(409, message)
    return {"ok": True, "message": message}


# ── pending questions ──────────────────────────────────────────────

@router.get("/questions/pending")
def list_pending_questions(request: Request):
    registry = request.app.state.pending_registry
    if registry is None:
        return []
    return registry.list_pending()


@router.post("/questions/{question_id}/answer")
def answer_question(question_id: str, body: QuestionAnswerRequest, request: Request):
    registry = request.app.state.pending_registry
    if registry is None or not registry.resolve(question_id, body.answer):
        raise HTTPException(404, "No pending question with that id (it may have already timed out).")
    return {"ok": True}


@router.post("/questions/{question_id}/skip")
def skip_question(question_id: str, request: Request):
    registry = request.app.state.pending_registry
    if registry is None or not registry.cancel(question_id):
        raise HTTPException(404, "No pending question with that id (it may have already timed out).")
    return {"ok": True}


# ── preferences ─────────────────────────────────────────────────────

@router.get("/preferences")
def get_preferences(request: Request):
    prefs_store = request.app.state.prefs_store
    if prefs_store is None:
        return dict(PREFS_DEFAULTS)
    return prefs_store.load()


@router.put("/preferences")
def update_preferences(body: PreferencesUpdate, request: Request):
    prefs_store = request.app.state.prefs_store
    if prefs_store is None:
        raise HTTPException(500, "Preferences store is not configured.")
    return prefs_store.save(body.model_dump(exclude_unset=True))


# ── profile ──────────────────────────────────────────────────────────

@router.get("/profile")
def get_profile(request: Request):
    profile_store = request.app.state.profile_store
    if profile_store is None:
        raise HTTPException(500, "Profile store is not configured.")
    return {"profile": profile_store.load(), "is_first_run": not profile_store.exists()}


@router.put("/profile")
def update_profile(body: ProfileUpdate, request: Request):
    profile_store = request.app.state.profile_store
    if profile_store is None:
        raise HTTPException(500, "Profile store is not configured.")
    return profile_store.save(body.model_dump(exclude_unset=True, by_alias=True))


# ── resume upload ───────────────────────────────────────────────────

@router.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    from ..resume.parser import extract_skills, extract_text

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF resumes are supported right now.")

    import os

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = os.path.basename(file.filename)
    saved_path = os.path.join(paths.RESUME_DIR, f"{ts}_{safe_name}")

    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    try:
        text = extract_text(saved_path)
        skills = extract_skills(text)
    except Exception as e:
        raise HTTPException(422, f"Could not parse this PDF: {e}")

    return {"path": saved_path, "skills": skills, "characters_extracted": len(text)}


# ── knowledge base ──────────────────────────────────────────────────

@router.get("/kb")
def list_kb_entries(request: Request, query: str = None, source: str = None):
    store = _get_kb_store(request)
    return store.list_entries(query=query, source=source)


@router.put("/kb/{entry_id}")
def update_kb_entry(entry_id: int, body: KBEntryUpdate, request: Request):
    store = _get_kb_store(request)
    entry = store.get_entry(entry_id)
    if entry is None:
        raise HTTPException(404, "No such knowledge base entry.")
    if entry["source"] == "static_profile" and body.answer is not None:
        raise HTTPException(
            400,
            "This answer comes from your profile — edit it on the Preferences/Profile "
            "page instead, so there's one source of truth for it.",
        )
    return store.update_entry(entry_id, answer=body.answer, canonical_question=body.canonical_question)


@router.delete("/kb/{entry_id}")
def delete_kb_entry(entry_id: int, request: Request):
    store = _get_kb_store(request)
    store.delete_entry(entry_id)
    return {"ok": True}


# ── application history ─────────────────────────────────────────────

@router.get("/applications")
def list_applications(request: Request, limit: int = 50, offset: int = 0, status: str = None):
    store = _get_kb_store(request)
    return store.list_applications(limit=limit, offset=offset, status=status)
