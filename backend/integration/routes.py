import secrets
from urllib.parse import urlencode

from flask import Blueprint, current_app, jsonify, redirect, request

from backend.integration.adapters.ai_screening import (
    local_rank_potential_candidates,
    local_screen,
    remote_rank_potential_candidates,
    remote_screen,
)
from backend.integration.adapters.calendar import create_event
from backend.integration.adapters.gmail import send_email
from backend.integration.adapters.google_oauth import (
    build_authorize_url as build_google_authorize_url,
    exchange_code_for_token as exchange_google_code_for_token,
    get_profile as get_google_profile,
)
from backend.integration.adapters.linkedin import (
    build_authorize_url as build_linkedin_authorize_url,
    exchange_code_for_token as exchange_linkedin_code_for_token,
    get_profile as get_linkedin_profile,
)
from backend.shared.rabbitmq import publish_event


integration_bp = Blueprint("integration_bp", __name__)


def _publish(event_type: str, payload: dict, routing_key: str):
    publish_event(
        rabbitmq_url=current_app.config["RABBITMQ_URL"],
        event_type=event_type,
        payload=payload,
        routing_key=routing_key,
    )


@integration_bp.get("/health")
def health_check():
    return jsonify({"service": "integration", "status": "ok"})


@integration_bp.get("/integrations/linkedin/auth-url")
def linkedin_auth_url():
    client_id = current_app.config["LINKEDIN_CLIENT_ID"]
    if not client_id:
        return jsonify({"error": "LINKEDIN_CLIENT_ID is not configured"}), 500

    requested_state = (request.args.get("state") or "").strip()
    requested_mode = (request.args.get("mode") or "login").strip().lower()
    mode = "register" if requested_mode == "register" else "login"

    state = requested_state or f"{mode}:{secrets.token_urlsafe(18)}"
    scope = current_app.config["LINKEDIN_SCOPE"]

    url = build_linkedin_authorize_url(
        client_id=client_id,
        redirect_uri=current_app.config["LINKEDIN_REDIRECT_URI"],
        scope=scope,
        state=state,
    )

    return jsonify({"auth_url": url, "state": state, "mode": mode})


@integration_bp.get("/integrations/linkedin/callback")
def linkedin_callback_bridge():
    frontend_callback = current_app.config["LINKEDIN_FRONTEND_CALLBACK_URI"]

    params = {}
    code = (request.args.get("code") or "").strip()
    state = (request.args.get("state") or "").strip()
    error = (request.args.get("error") or "").strip()
    error_description = (request.args.get("error_description") or "").strip()

    if code:
        params["code"] = code
    if state:
        params["state"] = state
    if error:
        params["error"] = error
    if error_description:
        params["error_description"] = error_description

    if not params:
        return jsonify({"error": "missing callback parameters"}), 400

    separator = "&" if "?" in frontend_callback else "?"
    redirect_url = f"{frontend_callback}{separator}{urlencode(params)}"
    return redirect(redirect_url, code=302)


@integration_bp.post("/integrations/linkedin/token")
def linkedin_token():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400

    try:
        token_data = exchange_linkedin_code_for_token(
            client_id=current_app.config["LINKEDIN_CLIENT_ID"],
            client_secret=current_app.config["LINKEDIN_CLIENT_SECRET"],
            redirect_uri=current_app.config["LINKEDIN_REDIRECT_URI"],
            code=code,
        )
    except Exception as exc:
        return jsonify({"error": f"linkedin token exchange failed: {exc}"}), 502

    _publish(
        event_type="linkedin.token.exchanged",
        payload={"expires_in": token_data.get("expires_in")},
        routing_key="integration.linkedin.token",
    )

    return jsonify(token_data)


@integration_bp.get("/integrations/linkedin/profile")
def linkedin_profile():
    access_token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not access_token:
        access_token = (request.args.get("access_token") or "").strip()

    if not access_token:
        return jsonify({"error": "access token is required"}), 400

    try:
        profile = get_linkedin_profile(access_token)
    except Exception as exc:
        return jsonify({"error": f"linkedin profile fetch failed: {exc}"}), 502

    _publish(
        event_type="linkedin.profile.synced",
        payload={"linkedin_sub": profile.get("sub")},
        routing_key="integration.linkedin.profile",
    )

    return jsonify(profile)


@integration_bp.get("/integrations/google/auth-url")
def google_auth_url():
    client_id = current_app.config["GOOGLE_CLIENT_ID"]
    if not client_id:
        return jsonify({"error": "GOOGLE_CLIENT_ID is not configured"}), 500

    requested_state = (request.args.get("state") or "").strip()
    requested_mode = (request.args.get("mode") or "login").strip().lower()
    mode = "register" if requested_mode == "register" else "login"

    state = requested_state or f"{mode}:{secrets.token_urlsafe(18)}"
    scope = current_app.config["GOOGLE_SCOPE"]

    url = build_google_authorize_url(
        client_id=client_id,
        redirect_uri=current_app.config["GOOGLE_REDIRECT_URI"],
        scope=scope,
        state=state,
    )

    return jsonify({"auth_url": url, "state": state, "mode": mode})


@integration_bp.get("/integrations/google/callback")
def google_callback_bridge():
    frontend_callback = current_app.config["GOOGLE_FRONTEND_CALLBACK_URI"]

    params = {}
    code = (request.args.get("code") or "").strip()
    state = (request.args.get("state") or "").strip()
    error = (request.args.get("error") or "").strip()
    error_description = (request.args.get("error_description") or "").strip()

    if code:
        params["code"] = code
    if state:
        params["state"] = state
    if error:
        params["error"] = error
    if error_description:
        params["error_description"] = error_description

    if not params:
        return jsonify({"error": "missing callback parameters"}), 400

    separator = "&" if "?" in frontend_callback else "?"
    redirect_url = f"{frontend_callback}{separator}{urlencode(params)}"
    return redirect(redirect_url, code=302)


@integration_bp.post("/integrations/google/token")
def google_token():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400

    try:
        token_data = exchange_google_code_for_token(
            client_id=current_app.config["GOOGLE_CLIENT_ID"],
            client_secret=current_app.config["GOOGLE_CLIENT_SECRET"],
            redirect_uri=current_app.config["GOOGLE_REDIRECT_URI"],
            code=code,
        )
    except Exception as exc:
        return jsonify({"error": f"google token exchange failed: {exc}"}), 502

    _publish(
        event_type="google.token.exchanged",
        payload={"expires_in": token_data.get("expires_in")},
        routing_key="integration.google.token",
    )

    return jsonify(token_data)


@integration_bp.get("/integrations/google/profile")
def google_profile():
    access_token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not access_token:
        access_token = (request.args.get("access_token") or "").strip()

    if not access_token:
        return jsonify({"error": "access token is required"}), 400

    try:
        profile = get_google_profile(access_token)
    except Exception as exc:
        return jsonify({"error": f"google profile fetch failed: {exc}"}), 502

    _publish(
        event_type="google.profile.synced",
        payload={"google_sub": profile.get("sub")},
        routing_key="integration.google.profile",
    )

    return jsonify(profile)


@integration_bp.post("/integrations/gmail/send")
def gmail_send():
    data = request.get_json(silent=True) or {}
    required_fields = ["access_token", "from_email", "to_email", "subject", "body"]
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    try:
        result = send_email(
            api_base=current_app.config["GMAIL_API_BASE"],
            access_token=data["access_token"],
            from_email=data["from_email"],
            to_email=data["to_email"],
            subject=data["subject"],
            body=data["body"],
        )
    except Exception as exc:
        return jsonify({"error": f"gmail send failed: {exc}"}), 502

    _publish(
        event_type="gmail.sent",
        payload={"to_email": data["to_email"], "message_id": result.get("id")},
        routing_key="integration.gmail.sent",
    )

    return jsonify(result)


@integration_bp.post("/integrations/calendar/schedule")
def calendar_schedule():
    data = request.get_json(silent=True) or {}
    required_fields = ["access_token", "calendar_id", "summary", "start", "end", "attendees"]
    missing = [field for field in required_fields if data.get(field) in (None, "")]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    attendees = data.get("attendees")
    if not isinstance(attendees, list):
        return jsonify({"error": "attendees must be a list"}), 400

    try:
        result = create_event(
            api_base=current_app.config["CALENDAR_API_BASE"],
            access_token=data["access_token"],
            calendar_id=data["calendar_id"],
            summary=data["summary"],
            description=data.get("description") or "",
            start_iso=data["start"],
            end_iso=data["end"],
            attendees=attendees,
        )
    except Exception as exc:
        return jsonify({"error": f"calendar schedule failed: {exc}"}), 502

    meet_link = None
    conference_data = result.get("conferenceData") or {}
    entry_points = conference_data.get("entryPoints") or []
    if entry_points:
        meet_link = entry_points[0].get("uri")

    payload = {
        "event_id": result.get("id"),
        "html_link": result.get("htmlLink"),
        "meeting_link": meet_link,
    }

    _publish(
        event_type="calendar.event.created",
        payload=payload,
        routing_key="integration.calendar.created",
    )

    return jsonify(payload)


@integration_bp.post("/integrations/ai/screen")
def ai_screen():
    data = request.get_json(silent=True) or {}
    candidate_profile = data.get("candidate_profile") or {}
    job = data.get("job") or {}

    if not job:
        return jsonify({"error": "job object is required"}), 400

    ai_url = current_app.config["AI_API_URL"]
    ai_key = current_app.config["AI_API_KEY"]
    timeout_seconds = current_app.config["AI_TIMEOUT_SECONDS"]

    if ai_url:
        try:
            result = remote_screen(
                api_url=ai_url,
                api_key=ai_key,
                payload={"candidate_profile": candidate_profile, "job": job},
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            fallback = local_screen(candidate_profile=candidate_profile, job=job)
            fallback["warning"] = f"remote AI failed: {exc}"
            result = fallback
    else:
        result = local_screen(candidate_profile=candidate_profile, job=job)

    _publish(
        event_type="ai.screen.completed",
        payload={"score": result.get("score"), "source": result.get("source")},
        routing_key="integration.ai.screen",
    )

    return jsonify(result)


@integration_bp.post("/integrations/ai/potential-candidates")
def ai_potential_candidates():
    data = request.get_json(silent=True) or {}
    job = data.get("job") or {}
    candidates = data.get("candidates") or []

    if not job:
        return jsonify({"error": "job object is required"}), 400
    if not isinstance(candidates, list):
        return jsonify({"error": "candidates must be a list"}), 400

    ai_url = current_app.config["AI_POTENTIAL_CANDIDATES_URL"]
    ai_key = current_app.config["AI_API_KEY"]
    timeout_seconds = current_app.config["AI_TIMEOUT_SECONDS"]

    if ai_url:
        try:
            result = remote_rank_potential_candidates(
                api_url=ai_url,
                api_key=ai_key,
                payload={"job": job, "candidates": candidates},
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            result = local_rank_potential_candidates(job=job, candidates=candidates)
            result["warning"] = f"remote AI candidate ranking failed: {exc}"
    else:
        result = local_rank_potential_candidates(job=job, candidates=candidates)

    _publish(
        event_type="ai.potential_candidates.completed",
        payload={"count": len(result.get("candidates", [])), "source": result.get("source", "local")},
        routing_key="integration.ai.potential",
    )

    return jsonify(result)
