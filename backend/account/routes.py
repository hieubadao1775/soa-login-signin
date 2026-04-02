import json
from datetime import date, datetime
import re

from flask import Blueprint, current_app, g, jsonify, request

from backend.account.models import User, db
from backend.shared.auth import generate_token, hash_password, require_auth, verify_password
from backend.shared.rabbitmq import publish_event


account_bp = Blueprint("account_bp", __name__)
ALLOWED_SIGNUP_ROLES = {"candidate", "recruiter"}
PHONE_PATTERN = re.compile(r"^\+?[0-9\s().-]{8,20}$")


def _normalize_signup_role(raw_role: str) -> str:
    role = (raw_role or "").strip().lower()
    return "recruiter" if role == "hr" else role


def _make_token(user: User) -> str:
    return generate_token(
        user_id=user.id,
        role=user.role,
        secret_key=current_app.config["SECRET_KEY"],
        algorithm=current_app.config["JWT_ALGORITHM"],
        expire_minutes=current_app.config["JWT_EXPIRE_MINUTES"],
    )


def _publish(event_type: str, payload: dict, routing_key: str):
    publish_event(
        rabbitmq_url=current_app.config["RABBITMQ_URL"],
        event_type=event_type,
        payload=payload,
        routing_key=routing_key,
    )


def _parse_profile_date(value: str | None):
    raw = (value or "").strip()
    if not raw:
        return None

    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("date_of_birth must be in YYYY-MM-DD format") from exc

    if parsed > date.today():
        raise ValueError("date_of_birth cannot be in the future")

    return parsed


def _validate_and_normalize_profile_payload(data: dict):
    normalized = {}

    if "full_name" in data:
        full_name = (data.get("full_name") or "").strip()
        if not full_name:
            raise ValueError("full_name cannot be empty")
        if len(full_name) > 255:
            raise ValueError("full_name must be <= 255 characters")
        normalized["full_name"] = full_name

    if "phone" in data:
        phone = (data.get("phone") or "").strip()
        if phone and not PHONE_PATTERN.match(phone):
            raise ValueError("phone format is invalid")
        normalized["phone"] = phone or None

    if "address" in data:
        address = (data.get("address") or "").strip()
        if len(address) > 255:
            raise ValueError("address must be <= 255 characters")
        normalized["address"] = address or None

    if "date_of_birth" in data:
        normalized["date_of_birth"] = _parse_profile_date(data.get("date_of_birth"))

    if "bio" in data:
        bio = (data.get("bio") or "").strip()
        if len(bio) > 2000:
            raise ValueError("bio must be <= 2000 characters")
        normalized["bio"] = bio or None

    return normalized


@account_bp.get("/health")
def health_check():
    return jsonify({"service": "account", "status": "ok"})


@account_bp.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    full_name = (data.get("full_name") or "").strip()
    role = _normalize_signup_role(data.get("role") or "")

    if not email or not password or not full_name:
        return jsonify({"error": "email, password, full_name are required"}), 400

    if not role:
        return jsonify(
            {
                "error": "role is required for first email signup",
                "error_code": "role_required",
                "allowed_roles": ["candidate", "recruiter"],
            }
        ), 400

    if role not in ALLOWED_SIGNUP_ROLES:
        return jsonify({"error": "role must be candidate or recruiter"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already exists"}), 409

    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        full_name=full_name,
    )
    db.session.add(user)
    db.session.commit()

    _publish(
        event_type="user.registered",
        payload={"user_id": user.id, "email": user.email, "role": user.role},
        routing_key="user.registered",
    )

    return jsonify({"token": _make_token(user), "user": user.to_dict()}), 201


@account_bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({"error": "invalid credentials"}), 401

    user.last_login_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"token": _make_token(user), "user": user.to_dict()})


def _social_register(
    *,
    provider: str,
    social_id_keys: list[str],
    social_id_field: str,
    profile_field: str,
    profile_json_field: str,
    default_full_name: str,
):
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    full_name = (data.get("full_name") or "").strip() or default_full_name
    raw_role = (data.get("role") or "").strip()
    role = _normalize_signup_role(raw_role) if raw_role else ""
    social_profile = data.get(profile_field) or {}

    social_id = ""
    for key in social_id_keys:
        social_id = (data.get(key) or "").strip()
        if social_id:
            break

    if not isinstance(social_profile, dict):
        return jsonify({"error": f"{profile_field} must be an object"}), 400

    if role and role not in ALLOWED_SIGNUP_ROLES:
        return jsonify({"error": "role must be candidate or recruiter"}), 400

    if not email or not social_id:
        return jsonify({"error": f"email and {social_id_field} are required"}), 400

    user_by_social = User.query.filter_by(**{social_id_field: social_id}).first()
    user_by_email = User.query.filter_by(email=email).first()

    # Require role whenever this social identity is linking for the first time,
    # even if the email already exists from another auth path.
    if user_by_social is None and not role:
        return jsonify(
            {
                "error": "role is required for first social signup",
                "error_code": "role_required",
                "allowed_roles": ["candidate", "recruiter"],
            }
        ), 400

    user = user_by_social or user_by_email

    if user_by_social is None and user_by_email is not None and role:
        # On first social link for an existing email account, honor explicit role
        # so users are not stuck with an accidental default role.
        user.role = role

    is_new_user = False

    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(social_id + email),
            role=role,
            full_name=full_name,
            **{social_id_field: social_id, profile_json_field: json.dumps(social_profile)},
        )
        db.session.add(user)
        is_new_user = True

    if not getattr(user, social_id_field):
        setattr(user, social_id_field, social_id)
    user.full_name = full_name
    setattr(user, profile_json_field, json.dumps(social_profile))
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    event_action = "registered" if is_new_user else "logged_in"
    _publish(
        event_type=f"user.{provider}_{event_action}",
        payload={"user_id": user.id, social_id_field: social_id},
        routing_key=f"user.{provider}.{event_action}",
    )

    return jsonify({"token": _make_token(user), "user": user.to_dict(), "is_new_user": is_new_user})


@account_bp.post("/auth/linkedin/register")
def linkedin_register():
    return _social_register(
        provider="linkedin",
        social_id_keys=["linkedin_id"],
        social_id_field="linkedin_id",
        profile_field="linkedin_profile",
        profile_json_field="linkedin_profile_json",
        default_full_name="LinkedIn User",
    )


@account_bp.post("/auth/google/register")
def google_register():
    return _social_register(
        provider="google",
        social_id_keys=["google_id", "sub"],
        social_id_field="google_id",
        profile_field="google_profile",
        profile_json_field="google_profile_json",
        default_full_name="Google User",
    )


@account_bp.post("/auth/linkedin/sync")
@require_auth(required_roles=["candidate", "recruiter", "admin"])
def linkedin_sync():
    payload = g.auth_payload
    user_id = int(payload.get("sub", 0))
    data = request.get_json(silent=True) or {}

    linkedin_profile = data.get("linkedin_profile")
    linkedin_id = (data.get("linkedin_id") or "").strip()

    if not linkedin_profile or not isinstance(linkedin_profile, dict):
        return jsonify({"error": "linkedin_profile object is required"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    if linkedin_id:
        user.linkedin_id = linkedin_id
    if linkedin_profile.get("full_name"):
        user.full_name = linkedin_profile["full_name"]
    user.linkedin_profile_json = json.dumps(linkedin_profile)
    db.session.commit()

    _publish(
        event_type="user.linkedin_synced",
        payload={"user_id": user.id, "linkedin_id": user.linkedin_id},
        routing_key="user.linkedin.synced",
    )

    return jsonify({"message": "linkedin profile synced", "user": user.to_dict()})


@account_bp.get("/auth/me")
@require_auth(required_roles=["candidate", "recruiter", "admin"])
def me():
    payload = g.auth_payload
    user_id = int(payload.get("sub", 0))
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    return jsonify({"user": user.to_dict()})


@account_bp.patch("/auth/me")
@require_auth(required_roles=["candidate", "recruiter", "admin"])
def update_me():
    payload = g.auth_payload
    user_id = int(payload.get("sub", 0))
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    data = request.get_json(silent=True) or {}
    mutable_keys = {"full_name", "phone", "address", "date_of_birth", "bio"}
    provided_keys = mutable_keys.intersection(set(data.keys()))
    if not provided_keys:
        return jsonify({"error": "no profile fields provided for update"}), 400

    try:
        normalized = _validate_and_normalize_profile_payload(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    for key, value in normalized.items():
        setattr(user, key, value)

    user.profile_updated_at = datetime.utcnow()
    db.session.commit()

    _publish(
        event_type="user.profile_updated",
        payload={"user_id": user.id, "role": user.role},
        routing_key="user.profile.updated",
    )

    return jsonify({"message": "profile updated", "user": user.to_dict()})
