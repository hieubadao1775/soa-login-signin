from datetime import datetime
import json
import os
import uuid

import requests
from flask import Blueprint, current_app, g, jsonify, request, send_from_directory
from sqlalchemy import func
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from backend.job.models import (
    ALLOWED_APPLICATION_STATUSES,
    APPLICATION_STATUS_APPLIED,
    APPLICATION_STATUS_HIRED,
    APPLICATION_STATUS_INTERVIEW_SCHEDULED,
    APPLICATION_STATUS_OFFER_SENT,
    APPLICATION_STATUS_ON_HOLD,
    APPLICATION_STATUS_REJECTED,
    APPLICATION_STATUS_REVIEWING,
    APPLICATION_STATUS_SHORTLISTED,
    APPLICATION_STATUS_WITHDRAWN,
    TERMINAL_APPLICATION_STATUSES,
    Application,
    ApplicationNote,
    ApplicationStatusHistory,
    CandidateCV,
    CandidateProfile,
    Company,
    Interview,
    Job,
    Notification,
    SavedJob,
    db,
)
from backend.shared.auth import require_auth
from backend.shared.rabbitmq import publish_event


job_bp = Blueprint("job_bp", __name__)


ALLOWED_STATUS_TRANSITIONS = {
    APPLICATION_STATUS_APPLIED: {
        APPLICATION_STATUS_REVIEWING,
        APPLICATION_STATUS_SHORTLISTED,
        APPLICATION_STATUS_REJECTED,
        APPLICATION_STATUS_WITHDRAWN,
        APPLICATION_STATUS_ON_HOLD,
    },
    APPLICATION_STATUS_REVIEWING: {
        APPLICATION_STATUS_SHORTLISTED,
        APPLICATION_STATUS_INTERVIEW_SCHEDULED,
        APPLICATION_STATUS_REJECTED,
        APPLICATION_STATUS_WITHDRAWN,
        APPLICATION_STATUS_ON_HOLD,
    },
    APPLICATION_STATUS_SHORTLISTED: {
        APPLICATION_STATUS_INTERVIEW_SCHEDULED,
        APPLICATION_STATUS_REJECTED,
        APPLICATION_STATUS_WITHDRAWN,
        APPLICATION_STATUS_ON_HOLD,
    },
    APPLICATION_STATUS_INTERVIEW_SCHEDULED: {
        APPLICATION_STATUS_OFFER_SENT,
        APPLICATION_STATUS_REJECTED,
        APPLICATION_STATUS_WITHDRAWN,
        APPLICATION_STATUS_ON_HOLD,
    },
    APPLICATION_STATUS_OFFER_SENT: {
        APPLICATION_STATUS_HIRED,
        APPLICATION_STATUS_REJECTED,
        APPLICATION_STATUS_ON_HOLD,
    },
    APPLICATION_STATUS_ON_HOLD: {
        APPLICATION_STATUS_REVIEWING,
        APPLICATION_STATUS_SHORTLISTED,
        APPLICATION_STATUS_INTERVIEW_SCHEDULED,
        APPLICATION_STATUS_REJECTED,
        APPLICATION_STATUS_WITHDRAWN,
    },
    APPLICATION_STATUS_REJECTED: set(),
    APPLICATION_STATUS_WITHDRAWN: set(),
    APPLICATION_STATUS_HIRED: set(),
}

INTERVIEW_OUTCOME_TO_STATUS = {
    "passed": APPLICATION_STATUS_OFFER_SENT,
    "failed": APPLICATION_STATUS_REJECTED,
    "on_hold": APPLICATION_STATUS_ON_HOLD,
}

ALLOWED_RESUME_EXTENSIONS = {"pdf", "doc", "docx"}


def _publish(event_type: str, payload: dict, routing_key: str):
    publish_event(
        rabbitmq_url=current_app.config["RABBITMQ_URL"],
        event_type=event_type,
        payload=payload,
        routing_key=routing_key,
    )


def _auth_user_id() -> int:
    return int(g.auth_payload.get("sub", 0))


def _auth_role() -> str:
    return g.auth_payload.get("role", "")


def _parse_pagination() -> tuple[int, int]:
    default_limit = max(1, int(current_app.config.get("API_DEFAULT_PAGE_SIZE", 20)))
    max_limit = max(default_limit, int(current_app.config.get("API_MAX_PAGE_SIZE", 100)))

    raw_limit = (request.args.get("limit") or "").strip()
    raw_offset = (request.args.get("offset") or "").strip()

    limit = default_limit
    offset = 0

    if raw_limit:
        limit = int(raw_limit)
    if raw_offset:
        offset = int(raw_offset)

    if limit < 1:
        raise ValueError("limit must be >= 1")
    if limit > max_limit:
        raise ValueError(f"limit must be <= {max_limit}")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    return limit, offset


def _parse_optional_float(raw_value, field_name: str):
    if raw_value in (None, ""):
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


def _parse_optional_status(raw_status: str) -> str:
    status = (raw_status or "").strip().lower()
    if not status:
        return ""
    if status not in ALLOWED_APPLICATION_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_APPLICATION_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")
    return status


def _parse_builder_json(raw_value):
    if raw_value in (None, ""):
        return None
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError("builder_json must be valid JSON") from exc
    raise ValueError("builder_json must be JSON object")


def _is_allowed_resume_filename(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_RESUME_EXTENSIONS


def _save_resume_file(file_storage: FileStorage) -> str:
    original_filename = secure_filename(file_storage.filename or "")
    if not _is_allowed_resume_filename(original_filename):
        allowed = ", ".join(sorted(ALLOWED_RESUME_EXTENSIONS))
        raise ValueError(f"resume file type is not supported, allowed: {allowed}")

    extension = original_filename.rsplit(".", 1)[1].lower()
    generated_name = f"{uuid.uuid4().hex}.{extension}"

    upload_dir = current_app.config["RESUME_UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    target_path = os.path.join(upload_dir, generated_name)
    file_storage.save(target_path)
    return generated_name


def _can_manage_company(role: str, user_id: int, company: Company) -> bool:
    if role == "admin":
        return True
    return role == "recruiter" and company.recruiter_id == user_id


def _can_manage_job(role: str, user_id: int, job: Job, company: Company) -> bool:
    if role == "admin":
        return True
    return role == "recruiter" and company.recruiter_id == user_id


def _application_scope(application: Application):
    job = Job.query.get(application.job_id)
    if not job:
        return None, None
    company = Company.query.get(job.company_id)
    return job, company


def _can_manage_application(application: Application, role: str, user_id: int) -> bool:
    job, company = _application_scope(application)
    if not company or not job:
        return False
    return _can_manage_job(role=role, user_id=user_id, job=job, company=company)


def _can_view_application(application: Application, role: str, user_id: int) -> bool:
    if role == "admin":
        return True
    if role == "candidate":
        return application.candidate_id == user_id
    if role == "recruiter":
        return _can_manage_application(application=application, role=role, user_id=user_id)
    return False


def _can_access_cv(cv: CandidateCV, role: str, user_id: int) -> bool:
    if role == "admin":
        return True
    if role == "candidate":
        return cv.candidate_id == user_id
    if role != "recruiter":
        return False

    owns_application = (
        Application.query.join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
        .filter(Application.cv_id == cv.id, Company.recruiter_id == user_id)
        .first()
    )
    return owns_application is not None


def _status_counts_for_query(query):
    counts = {status: 0 for status in sorted(ALLOWED_APPLICATION_STATUSES)}
    rows = (
        query.order_by(None)
        .with_entities(Application.status, func.count(Application.id))
        .group_by(Application.status)
        .all()
    )
    for status, count in rows:
        counts[status] = int(count)
    return counts


def _status_counts_for_job(job_id: int):
    query = Application.query.filter_by(job_id=job_id)
    return _status_counts_for_query(query)


def _add_status_history(
    *,
    application: Application,
    old_status: str | None,
    new_status: str,
    changed_by_id: int,
    reason: str | None,
):
    history = ApplicationStatusHistory(
        application_id=application.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_id=changed_by_id,
        reason=(reason or "").strip() or None,
    )
    db.session.add(history)


def _can_transition_status(current_status: str, target_status: str) -> bool:
    normalized_current = (current_status or "").strip().lower()
    normalized_target = (target_status or "").strip().lower()
    if normalized_current == normalized_target:
        return True
    allowed_next = ALLOWED_STATUS_TRANSITIONS.get(normalized_current, set())
    return normalized_target in allowed_next


def _update_application_status(
    *,
    application: Application,
    new_status: str,
    changed_by_id: int,
    reason: str | None = None,
    enforce_transition: bool = True,
) -> bool:
    normalized_new = (new_status or "").strip().lower()
    if normalized_new not in ALLOWED_APPLICATION_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_APPLICATION_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")

    old_status = (application.status or "").strip().lower()
    if enforce_transition and not _can_transition_status(old_status, normalized_new):
        raise ValueError(f"invalid status transition from {old_status} to {normalized_new}")

    if old_status == normalized_new:
        return False

    now = datetime.utcnow()
    application.status = normalized_new
    application.stage_updated_by = changed_by_id
    application.stage_updated_at = now
    application.updated_at = now

    if normalized_new == APPLICATION_STATUS_REJECTED:
        application.rejection_reason = (reason or "").strip() or application.rejection_reason
    else:
        application.rejection_reason = None

    _add_status_history(
        application=application,
        old_status=old_status or None,
        new_status=normalized_new,
        changed_by_id=changed_by_id,
        reason=reason,
    )
    return True


def _ensure_candidate_profile(user_id: int, fallback_name: str = "", fallback_email: str = "") -> CandidateProfile:
    profile = CandidateProfile.query.filter_by(user_id=user_id).first()
    if profile:
        return profile

    profile = CandidateProfile(
        user_id=user_id,
        full_name=(fallback_name or "").strip() or None,
        contact_email=(fallback_email or "").strip().lower() or None,
    )
    db.session.add(profile)
    db.session.flush()
    return profile


def _ensure_default_cv(candidate_id: int):
    default_cv = CandidateCV.query.filter_by(candidate_id=candidate_id, is_default=True).first()
    if default_cv:
        return

    first_cv = CandidateCV.query.filter_by(candidate_id=candidate_id).order_by(CandidateCV.created_at.asc()).first()
    if first_cv:
        first_cv.is_default = True


def _set_default_cv(candidate_id: int, cv_id: int):
    CandidateCV.query.filter_by(candidate_id=candidate_id, is_default=True).update({"is_default": False})
    target = CandidateCV.query.filter_by(id=cv_id, candidate_id=candidate_id).first()
    if target:
        target.is_default = True
    return target


def _create_notification(recipient_user_id: int, notification_type: str, title: str, message: str):
    notification = Notification(
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        title=title,
        message=message,
    )
    db.session.add(notification)
    return notification


def _try_send_status_email(application: Application, new_status: str, reason: str | None):
    integration_service_url = current_app.config["INTEGRATION_SERVICE_URL"].rstrip("/")
    from_email = os.getenv("NOTIFICATION_FROM_EMAIL", "").strip()
    access_token = os.getenv("NOTIFICATION_GMAIL_ACCESS_TOKEN", "").strip()

    if not application.candidate_email or not from_email or not access_token:
        return False

    payload = {
        "access_token": access_token,
        "from_email": from_email,
        "to_email": application.candidate_email,
        "subject": f"Cap nhat trang thai ho so: {new_status}",
        "body": (
            f"Xin chao {application.candidate_name or 'ung vien'},\n"
            f"Ho so #{application.id} cua ban da duoc cap nhat sang trang thai: {new_status}.\n"
            f"Ly do: {reason or 'khong co'}"
        ),
    }

    try:
        response = requests.post(
            f"{integration_service_url}/api/integrations/gmail/send",
            json=payload,
            timeout=8,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        print(f"[job] send status email failed: {exc}")
        return False


@job_bp.get("/health")
def health_check():
    return jsonify({"service": "job", "status": "ok"})


@job_bp.get("/companies")
def list_companies():
    companies = Company.query.order_by(Company.created_at.desc()).all()
    return jsonify({"companies": [company.to_dict() for company in companies]})


@job_bp.post("/companies")
@require_auth(required_roles=["recruiter", "admin"])
def create_company():
    user_id = _auth_user_id()
    role = _auth_role()
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    if role == "recruiter" and Company.query.filter_by(recruiter_id=user_id).first():
        return jsonify({"error": "recruiter already has a company"}), 409

    company = Company(
        recruiter_id=user_id,
        name=name,
        description=(data.get("description") or "").strip() or None,
        website=(data.get("website") or "").strip() or None,
        logo_url=(data.get("logo_url") or "").strip() or None,
    )
    db.session.add(company)
    db.session.commit()

    _publish(
        event_type="company.created",
        payload={"company_id": company.id, "recruiter_id": company.recruiter_id},
        routing_key="company.created",
    )

    return jsonify({"company": company.to_dict()}), 201


@job_bp.patch("/companies/<int:company_id>")
@require_auth(required_roles=["recruiter", "admin"])
def update_company(company_id: int):
    company = Company.query.get(company_id)
    if not company:
        return jsonify({"error": "company not found"}), 404

    if not _can_manage_company(role=_auth_role(), user_id=_auth_user_id(), company=company):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        company.name = name
    if "description" in data:
        company.description = (data.get("description") or "").strip() or None
    if "website" in data:
        company.website = (data.get("website") or "").strip() or None
    if "logo_url" in data:
        company.logo_url = (data.get("logo_url") or "").strip() or None

    db.session.commit()
    return jsonify({"company": company.to_dict()})


@job_bp.get("/recruiter/company")
@require_auth(required_roles=["recruiter", "admin"])
def recruiter_company():
    user_id = _auth_user_id()
    role = _auth_role()
    recruiter_id = user_id

    if role == "admin":
        recruiter_id = int(request.args.get("recruiter_id") or user_id)

    company = Company.query.filter_by(recruiter_id=recruiter_id).first()
    return jsonify({"company": company.to_dict() if company else None})


@job_bp.put("/recruiter/company")
@require_auth(required_roles=["recruiter", "admin"])
def upsert_recruiter_company():
    user_id = _auth_user_id()
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    company = Company.query.filter_by(recruiter_id=user_id).first()
    if not company:
        company = Company(recruiter_id=user_id, name=name)
        db.session.add(company)

    company.name = name
    company.description = (data.get("description") or "").strip() or None
    company.website = (data.get("website") or "").strip() or None
    company.logo_url = (data.get("logo_url") or "").strip() or None

    db.session.commit()
    return jsonify({"company": company.to_dict()})


@job_bp.get("/jobs")
def list_jobs():
    query = Job.query.filter_by(is_active=True)

    keyword = (request.args.get("q") or "").strip()
    location = (request.args.get("location") or "").strip()
    job_type = (request.args.get("job_type") or "").strip()
    experience = (request.args.get("experience_level") or "").strip()

    salary_min = request.args.get("salary_min")
    salary_max = request.args.get("salary_max")

    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter((Job.title.ilike(pattern)) | (Job.description.ilike(pattern)))
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    if job_type:
        query = query.filter(Job.job_type == job_type)
    if experience:
        query = query.filter(Job.experience_level == experience)

    if salary_min:
        try:
            query = query.filter(Job.salary_min >= float(salary_min))
        except ValueError:
            return jsonify({"error": "salary_min must be numeric"}), 400

    if salary_max:
        try:
            query = query.filter(Job.salary_max <= float(salary_max))
        except ValueError:
            return jsonify({"error": "salary_max must be numeric"}), 400

    try:
        limit, offset = _parse_pagination()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    total = query.count()
    jobs = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify(
        {
            "jobs": [job.to_dict() for job in jobs],
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }
    )


@job_bp.get("/jobs/<int:job_id>")
def get_job(job_id: int):
    job = Job.query.get(job_id)
    if not job or not job.is_active:
        return jsonify({"error": "job not found"}), 404
    return jsonify({"job": job.to_dict()})


@job_bp.post("/jobs")
@require_auth(required_roles=["recruiter", "admin"])
def create_job():
    data = request.get_json(silent=True) or {}
    required_fields = ["title", "description", "location", "job_type", "experience_level"]
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    user_id = _auth_user_id()
    role = _auth_role()

    company = None
    company_id_raw = data.get("company_id")
    if company_id_raw:
        company = Company.query.get(int(company_id_raw))
    elif role == "recruiter":
        company = Company.query.filter_by(recruiter_id=user_id).first()

    if not company:
        return jsonify({"error": "company not found, please create company profile first"}), 404

    if not _can_manage_company(role=role, user_id=user_id, company=company):
        return jsonify({"error": "forbidden for this company"}), 403

    try:
        salary_min = _parse_optional_float(data.get("salary_min"), "salary_min")
        salary_max = _parse_optional_float(data.get("salary_max"), "salary_max")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        return jsonify({"error": "salary_min must be <= salary_max"}), 400

    job = Job(
        company_id=company.id,
        title=(data.get("title") or "").strip(),
        description=(data.get("description") or "").strip(),
        requirements=(data.get("requirements") or "").strip() or None,
        location=(data.get("location") or "").strip(),
        job_type=(data.get("job_type") or "").strip(),
        experience_level=(data.get("experience_level") or "").strip(),
        salary_min=salary_min,
        salary_max=salary_max,
        is_active=True,
    )
    db.session.add(job)
    db.session.commit()

    _publish(
        event_type="job.created",
        payload={"job_id": job.id, "company_id": company.id, "title": job.title},
        routing_key="job.created",
    )
    return jsonify({"job": job.to_dict()}), 201


@job_bp.get("/recruiter/jobs")
@require_auth(required_roles=["recruiter", "admin"])
def recruiter_jobs():
    user_id = _auth_user_id()
    role = _auth_role()

    query = Job.query.join(Company, Job.company_id == Company.id)
    if role == "recruiter":
        query = query.filter(Company.recruiter_id == user_id)

    jobs = query.order_by(Job.created_at.desc()).all()
    return jsonify({"jobs": [job.to_dict() for job in jobs]})


@job_bp.patch("/recruiter/jobs/<int:job_id>")
@require_auth(required_roles=["recruiter", "admin"])
def update_recruiter_job(job_id: int):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    company = Company.query.get(job.company_id)
    if not company:
        return jsonify({"error": "company not found"}), 404

    if not _can_manage_job(role=_auth_role(), user_id=_auth_user_id(), job=job, company=company):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    mutable_fields = {
        "title": "title",
        "description": "description",
        "requirements": "requirements",
        "location": "location",
        "job_type": "job_type",
        "experience_level": "experience_level",
        "is_active": "is_active",
    }
    for raw_key, attr in mutable_fields.items():
        if raw_key in data:
            value = data.get(raw_key)
            if isinstance(value, str):
                value = value.strip()
            setattr(job, attr, value)

    if "salary_min" in data:
        try:
            job.salary_min = _parse_optional_float(data.get("salary_min"), "salary_min")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    if "salary_max" in data:
        try:
            job.salary_max = _parse_optional_float(data.get("salary_max"), "salary_max")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    if (
        job.salary_min is not None
        and job.salary_max is not None
        and float(job.salary_min) > float(job.salary_max)
    ):
        return jsonify({"error": "salary_min must be <= salary_max"}), 400

    db.session.commit()
    return jsonify({"job": job.to_dict()})


@job_bp.get("/candidate/profile")
@require_auth(required_roles=["candidate", "admin"])
def candidate_profile():
    user_id = _auth_user_id()
    profile = _ensure_candidate_profile(user_id)
    db.session.commit()
    return jsonify({"profile": profile.to_dict()})


@job_bp.patch("/candidate/profile")
@require_auth(required_roles=["candidate", "admin"])
def update_candidate_profile():
    user_id = _auth_user_id()
    profile = _ensure_candidate_profile(user_id)

    data = request.get_json(silent=True) or {}
    if "full_name" in data:
        profile.full_name = (data.get("full_name") or "").strip() or None
    if "contact_email" in data:
        profile.contact_email = (data.get("contact_email") or "").strip().lower() or None
    if "phone" in data:
        profile.phone = (data.get("phone") or "").strip() or None
    if "headline" in data:
        profile.headline = (data.get("headline") or "").strip() or None
    if "summary" in data:
        profile.summary = (data.get("summary") or "").strip() or None
    if "experience_years" in data:
        raw_experience = data.get("experience_years")
        if raw_experience in (None, ""):
            profile.experience_years = None
        else:
            try:
                parsed_experience = int(raw_experience)
            except (TypeError, ValueError):
                return jsonify({"error": "experience_years must be integer"}), 400
            if parsed_experience < 0:
                return jsonify({"error": "experience_years must be >= 0"}), 400
            profile.experience_years = parsed_experience
    if "skills" in data:
        skills = data.get("skills")
        if isinstance(skills, str):
            parsed = [part.strip() for part in skills.split(",") if part.strip()]
            profile.skills_json = json.dumps(parsed)
        elif isinstance(skills, list):
            parsed = [str(item).strip() for item in skills if str(item).strip()]
            profile.skills_json = json.dumps(parsed)
        else:
            return jsonify({"error": "skills must be comma string or list"}), 400

    db.session.commit()
    return jsonify({"profile": profile.to_dict()})


@job_bp.get("/candidate/cvs")
@require_auth(required_roles=["candidate", "admin"])
def list_candidate_cvs():
    candidate_id = _auth_user_id()
    cvs = (
        CandidateCV.query.filter_by(candidate_id=candidate_id)
        .order_by(CandidateCV.is_default.desc(), CandidateCV.created_at.desc())
        .all()
    )
    return jsonify({"cvs": [cv.to_dict() for cv in cvs]})


@job_bp.post("/candidate/cvs")
@require_auth(required_roles=["candidate", "admin"])
def create_candidate_cv():
    candidate_id = _auth_user_id()

    if request.content_type and "multipart/form-data" in request.content_type:
        title = (request.form.get("title") or "").strip()
        resume_text = (request.form.get("resume_text") or "").strip() or None
        builder_raw = request.form.get("builder_json")
        is_default = (request.form.get("is_default") or "").strip().lower() in {"1", "true", "yes"}
        cv_file = request.files.get("cv_file") if request.files else None
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        resume_text = (data.get("resume_text") or "").strip() or None
        builder_raw = data.get("builder_json")
        is_default = bool(data.get("is_default"))
        cv_file = None

    if not title:
        title = f"CV {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

    try:
        builder_payload = _parse_builder_json(builder_raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    filename = None
    if cv_file and isinstance(cv_file, FileStorage) and cv_file.filename:
        try:
            filename = _save_resume_file(cv_file)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    if not filename and not resume_text and not builder_payload:
        return jsonify({"error": "provide cv_file or resume_text or builder_json"}), 400

    cv = CandidateCV(
        candidate_id=candidate_id,
        title=title,
        file_path=filename,
        resume_text=resume_text,
        builder_json=json.dumps(builder_payload) if builder_payload else None,
        is_default=False,
    )
    db.session.add(cv)
    db.session.flush()

    if is_default:
        _set_default_cv(candidate_id=candidate_id, cv_id=cv.id)
    else:
        _ensure_default_cv(candidate_id)

    db.session.commit()
    return jsonify({"cv": cv.to_dict()}), 201


@job_bp.patch("/candidate/cvs/<int:cv_id>/default")
@require_auth(required_roles=["candidate", "admin"])
def set_candidate_cv_default(cv_id: int):
    candidate_id = _auth_user_id()
    cv = _set_default_cv(candidate_id=candidate_id, cv_id=cv_id)
    if not cv:
        return jsonify({"error": "cv not found"}), 404
    db.session.commit()
    return jsonify({"cv": cv.to_dict()})


@job_bp.delete("/candidate/cvs/<int:cv_id>")
@require_auth(required_roles=["candidate", "admin"])
def delete_candidate_cv(cv_id: int):
    candidate_id = _auth_user_id()
    cv = CandidateCV.query.filter_by(id=cv_id, candidate_id=candidate_id).first()
    if not cv:
        return jsonify({"error": "cv not found"}), 404

    used_in_application = Application.query.filter_by(cv_id=cv.id).first()
    if used_in_application:
        return jsonify({"error": "cannot delete CV already used in application"}), 409

    filename = cv.file_path
    was_default = cv.is_default
    db.session.delete(cv)
    db.session.flush()

    if was_default:
        _ensure_default_cv(candidate_id)

    db.session.commit()

    if filename:
        file_path = os.path.join(current_app.config["RESUME_UPLOAD_DIR"], filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

    return jsonify({"message": "cv deleted"})


@job_bp.get("/cvs/<int:cv_id>/download")
@require_auth(required_roles=["candidate", "recruiter", "admin"])
def download_cv(cv_id: int):
    cv = CandidateCV.query.get(cv_id)
    if not cv or not cv.file_path:
        return jsonify({"error": "cv file not found"}), 404

    role = _auth_role()
    user_id = _auth_user_id()
    if not _can_access_cv(cv=cv, role=role, user_id=user_id):
        return jsonify({"error": "forbidden"}), 403

    upload_dir = current_app.config["RESUME_UPLOAD_DIR"]
    target_path = os.path.join(upload_dir, cv.file_path)
    if not os.path.isfile(target_path):
        return jsonify({"error": "file not found"}), 404

    return send_from_directory(upload_dir, cv.file_path, as_attachment=True)


@job_bp.get("/candidate/saved-jobs")
@require_auth(required_roles=["candidate", "admin"])
def list_saved_jobs():
    candidate_id = _auth_user_id()
    records = (
        SavedJob.query.filter_by(candidate_id=candidate_id)
        .order_by(SavedJob.created_at.desc())
        .all()
    )
    return jsonify({"saved_jobs": [record.to_dict() for record in records]})


@job_bp.post("/candidate/saved-jobs/<int:job_id>")
@require_auth(required_roles=["candidate", "admin"])
def save_job(job_id: int):
    candidate_id = _auth_user_id()
    job = Job.query.get(job_id)
    if not job or not job.is_active:
        return jsonify({"error": "job not found"}), 404

    existing = SavedJob.query.filter_by(candidate_id=candidate_id, job_id=job_id).first()
    if existing:
        return jsonify({"saved_job": existing.to_dict(), "message": "already saved"})

    saved_job = SavedJob(candidate_id=candidate_id, job_id=job_id)
    db.session.add(saved_job)
    db.session.commit()
    return jsonify({"saved_job": saved_job.to_dict()}), 201


@job_bp.delete("/candidate/saved-jobs/<int:job_id>")
@require_auth(required_roles=["candidate", "admin"])
def unsave_job(job_id: int):
    candidate_id = _auth_user_id()
    record = SavedJob.query.filter_by(candidate_id=candidate_id, job_id=job_id).first()
    if not record:
        return jsonify({"error": "saved job not found"}), 404

    db.session.delete(record)
    db.session.commit()
    return jsonify({"message": "saved job removed"})


@job_bp.post("/jobs/<int:job_id>/apply")
@require_auth(required_roles=["candidate", "admin"])
def apply_job(job_id: int):
    job = Job.query.get(job_id)
    if not job or not job.is_active:
        return jsonify({"error": "job not found"}), 404

    candidate_id = _auth_user_id()
    if Application.query.filter_by(job_id=job_id, candidate_id=candidate_id).first():
        return jsonify({"error": "already applied for this job"}), 409

    cv_id = None
    cover_letter = None
    candidate_name = ""
    candidate_email = ""

    if request.content_type and "multipart/form-data" in request.content_type:
        cover_letter = (request.form.get("cover_letter") or "").strip() or None
        candidate_name = (request.form.get("candidate_name") or "").strip()
        candidate_email = (request.form.get("candidate_email") or "").strip().lower()
        raw_cv_id = (request.form.get("cv_id") or "").strip()
        cv_file = request.files.get("resume_file") if request.files else None
        if raw_cv_id:
            cv_id = int(raw_cv_id)
        elif cv_file and isinstance(cv_file, FileStorage) and cv_file.filename:
            try:
                file_name = _save_resume_file(cv_file)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            cv_title = (request.form.get("cv_title") or "").strip() or f"CV nop job #{job_id}"
            cv = CandidateCV(
                candidate_id=candidate_id,
                title=cv_title,
                file_path=file_name,
                resume_text=(request.form.get("resume_text") or "").strip() or None,
            )
            db.session.add(cv)
            db.session.flush()
            cv_id = cv.id
            _ensure_default_cv(candidate_id)
    else:
        data = request.get_json(silent=True) or {}
        cover_letter = (data.get("cover_letter") or "").strip() or None
        candidate_name = (data.get("candidate_name") or "").strip()
        candidate_email = (data.get("candidate_email") or "").strip().lower()
        raw_cv_id = data.get("cv_id")
        if raw_cv_id not in (None, ""):
            cv_id = int(raw_cv_id)

    if not cv_id:
        default_cv = CandidateCV.query.filter_by(candidate_id=candidate_id, is_default=True).first()
        if default_cv:
            cv_id = default_cv.id

    if not cv_id:
        return jsonify({"error": "cv_id is required or upload resume_file"}), 400

    cv = CandidateCV.query.filter_by(id=cv_id, candidate_id=candidate_id).first()
    if not cv:
        return jsonify({"error": "cv not found for candidate"}), 404

    profile = _ensure_candidate_profile(candidate_id, fallback_name=candidate_name, fallback_email=candidate_email)
    if candidate_name:
        profile.full_name = candidate_name
    if candidate_email:
        profile.contact_email = candidate_email

    now = datetime.utcnow()
    application = Application(
        job_id=job_id,
        candidate_id=candidate_id,
        candidate_name=profile.full_name,
        candidate_email=profile.contact_email,
        cv_id=cv_id,
        cover_letter=cover_letter,
        status=APPLICATION_STATUS_APPLIED,
        stage_updated_by=candidate_id,
        stage_updated_at=now,
        updated_at=now,
    )
    db.session.add(application)
    db.session.flush()

    _add_status_history(
        application=application,
        old_status=None,
        new_status=APPLICATION_STATUS_APPLIED,
        changed_by_id=candidate_id,
        reason="application_submitted",
    )

    db.session.commit()

    _publish(
        event_type="application.submitted",
        payload={
            "application_id": application.id,
            "job_id": job_id,
            "candidate_id": candidate_id,
            "cv_id": cv_id,
        },
        routing_key="application.submitted",
    )

    return jsonify({"application": application.to_dict()})


@job_bp.get("/applications/me")
@require_auth(required_roles=["candidate", "admin"])
def my_applications():
    candidate_id = _auth_user_id()
    query = Application.query.filter_by(candidate_id=candidate_id)

    try:
        status_filter = _parse_optional_status(request.args.get("status"))
        limit, offset = _parse_pagination()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if status_filter:
        query = query.filter_by(status=status_filter)

    total = query.count()
    applications = query.order_by(Application.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify(
        {
            "applications": [app.to_dict() for app in applications],
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }
    )


@job_bp.get("/candidate/applications")
@require_auth(required_roles=["candidate", "admin"])
def candidate_applications_alias():
    return my_applications()


@job_bp.get("/recruiter/applications")
@require_auth(required_roles=["recruiter", "admin"])
def recruiter_applications():
    user_id = _auth_user_id()
    role = _auth_role()

    query = (
        Application.query.join(Job, Application.job_id == Job.id)
        .join(Company, Job.company_id == Company.id)
    )
    if role == "recruiter":
        query = query.filter(Company.recruiter_id == user_id)

    try:
        status_filter = _parse_optional_status(request.args.get("status"))
        limit, offset = _parse_pagination()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    job_id_raw = (request.args.get("job_id") or "").strip()
    if job_id_raw:
        try:
            query = query.filter(Application.job_id == int(job_id_raw))
        except ValueError:
            return jsonify({"error": "job_id must be integer"}), 400

    if status_filter:
        query = query.filter(Application.status == status_filter)

    sort = (request.args.get("sort") or "created_at_desc").strip().lower()
    if sort == "created_at_asc":
        query = query.order_by(Application.created_at.asc())
    else:
        query = query.order_by(Application.created_at.desc())

    total = query.count()
    applications = query.offset(offset).limit(limit).all()
    return jsonify(
        {
            "applications": [item.to_dict() for item in applications],
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }
    )


@job_bp.get("/applications/job/<int:job_id>")
@require_auth(required_roles=["recruiter", "admin"])
def list_job_applications(job_id: int):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    company = Company.query.get(job.company_id)
    if not company:
        return jsonify({"error": "company not found"}), 404

    if not _can_manage_job(role=_auth_role(), user_id=_auth_user_id(), job=job, company=company):
        return jsonify({"error": "forbidden"}), 403

    query = Application.query.filter_by(job_id=job_id)

    try:
        status_filter = _parse_optional_status(request.args.get("status"))
        limit, offset = _parse_pagination()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if status_filter:
        query = query.filter_by(status=status_filter)

    total = query.count()
    applications = query.order_by(Application.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify(
        {
            "job": job.to_dict(),
            "applications": [app.to_dict() for app in applications],
            "counts_by_status": _status_counts_for_job(job_id),
            "pagination": {"total": total, "limit": limit, "offset": offset},
        }
    )


@job_bp.get("/recruiter/jobs/<int:job_id>/pipeline")
@require_auth(required_roles=["recruiter", "admin"])
def recruiter_job_pipeline(job_id: int):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    company = Company.query.get(job.company_id)
    if not company:
        return jsonify({"error": "company not found"}), 404

    if not _can_manage_job(role=_auth_role(), user_id=_auth_user_id(), job=job, company=company):
        return jsonify({"error": "forbidden"}), 403

    return jsonify({"job_id": job_id, "counts_by_status": _status_counts_for_job(job_id)})


@job_bp.patch("/applications/<int:application_id>/status")
@require_auth(required_roles=["recruiter", "admin"])
def update_application_status(application_id: int):
    application = Application.query.get(application_id)
    if not application:
        return jsonify({"error": "application not found"}), 404

    role = _auth_role()
    user_id = _auth_user_id()
    if not _can_manage_application(application=application, role=role, user_id=user_id):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().lower()
    reason = (data.get("reason") or "").strip() or None
    note_text = (data.get("note") or "").strip()

    if not new_status:
        return jsonify({"error": "status is required"}), 400
    if new_status == APPLICATION_STATUS_REJECTED and not reason:
        return jsonify({"error": "reason is required when status is rejected"}), 400

    old_status = application.status
    try:
        status_changed = _update_application_status(
            application=application,
            new_status=new_status,
            changed_by_id=user_id,
            reason=reason,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    note = None
    if note_text:
        note = ApplicationNote(
            application_id=application.id,
            recruiter_id=user_id,
            content=note_text,
        )
        db.session.add(note)

    if status_changed:
        _create_notification(
            recipient_user_id=application.candidate_id,
            notification_type="application_status_changed",
            title="Ho so duoc cap nhat",
            message=(
                f"Ho so #{application.id} cua ban da chuyen sang trang thai '{new_status}'."
                f" Ly do: {reason or 'khong co'}"
            ),
        )
        _try_send_status_email(application=application, new_status=new_status, reason=reason)

    db.session.commit()

    if status_changed:
        _publish(
            event_type="application.status_changed",
            payload={
                "application_id": application.id,
                "old_status": old_status,
                "new_status": application.status,
                "changed_by": user_id,
            },
            routing_key="application.status.changed",
        )

    return jsonify(
        {
            "application": application.to_dict(),
            "status_changed": status_changed,
            "note": note.to_dict() if note else None,
        }
    )


@job_bp.get("/applications/<int:application_id>/notes")
@require_auth(required_roles=["recruiter", "admin"])
def list_application_notes(application_id: int):
    application = Application.query.get(application_id)
    if not application:
        return jsonify({"error": "application not found"}), 404

    if not _can_manage_application(application=application, role=_auth_role(), user_id=_auth_user_id()):
        return jsonify({"error": "forbidden"}), 403

    notes = (
        ApplicationNote.query.filter_by(application_id=application.id)
        .order_by(ApplicationNote.created_at.desc())
        .all()
    )
    return jsonify({"notes": [note.to_dict() for note in notes]})


@job_bp.post("/applications/<int:application_id>/notes")
@require_auth(required_roles=["recruiter", "admin"])
def add_application_note(application_id: int):
    application = Application.query.get(application_id)
    if not application:
        return jsonify({"error": "application not found"}), 404

    user_id = _auth_user_id()
    if not _can_manage_application(application=application, role=_auth_role(), user_id=user_id):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400

    note = ApplicationNote(
        application_id=application.id,
        recruiter_id=user_id,
        content=content,
    )
    db.session.add(note)
    db.session.commit()

    return jsonify({"note": note.to_dict()}), 201


@job_bp.get("/applications/<int:application_id>/timeline")
@require_auth(required_roles=["candidate", "recruiter", "admin"])
def application_timeline(application_id: int):
    application = Application.query.get(application_id)
    if not application:
        return jsonify({"error": "application not found"}), 404

    role = _auth_role()
    user_id = _auth_user_id()
    if not _can_view_application(application=application, role=role, user_id=user_id):
        return jsonify({"error": "forbidden"}), 403

    history = (
        ApplicationStatusHistory.query.filter_by(application_id=application.id)
        .order_by(ApplicationStatusHistory.changed_at.asc())
        .all()
    )
    interviews = (
        Interview.query.filter_by(application_id=application.id)
        .order_by(Interview.created_at.asc())
        .all()
    )
    notes = []
    if role in {"recruiter", "admin"}:
        notes = (
            ApplicationNote.query.filter_by(application_id=application.id)
            .order_by(ApplicationNote.created_at.asc())
            .all()
        )

    return jsonify(
        {
            "application": application.to_dict(),
            "status_history": [item.to_dict() for item in history],
            "interviews": [item.to_dict() for item in interviews],
            "notes": [item.to_dict() for item in notes],
        }
    )


@job_bp.post("/applications/<int:application_id>/withdraw")
@require_auth(required_roles=["candidate", "admin"])
def withdraw_application(application_id: int):
    application = Application.query.get(application_id)
    if not application:
        return jsonify({"error": "application not found"}), 404

    user_id = _auth_user_id()
    if application.candidate_id != user_id and _auth_role() != "admin":
        return jsonify({"error": "forbidden"}), 403

    if application.status == APPLICATION_STATUS_WITHDRAWN:
        return jsonify({"application": application.to_dict(), "message": "already withdrawn"})

    if application.status in TERMINAL_APPLICATION_STATUSES:
        return jsonify({"error": "cannot withdraw a terminal application"}), 409

    reason = (request.get_json(silent=True) or {}).get("reason") or "candidate_withdrawn"
    old_status = application.status

    try:
        _update_application_status(
            application=application,
            new_status=APPLICATION_STATUS_WITHDRAWN,
            changed_by_id=user_id,
            reason=reason,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    db.session.commit()

    _publish(
        event_type="application.withdrawn",
        payload={
            "application_id": application.id,
            "old_status": old_status,
            "candidate_id": user_id,
        },
        routing_key="application.withdrawn",
    )

    return jsonify({"application": application.to_dict()})


@job_bp.post("/interviews/schedule")
@require_auth(required_roles=["recruiter", "admin"])
def schedule_interview():
    data = request.get_json(silent=True) or {}
    required_fields = ["application_id", "start_time", "end_time"]
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    application = Application.query.get(int(data["application_id"]))
    if not application:
        return jsonify({"error": "application not found"}), 404

    user_id = _auth_user_id()
    if not _can_manage_application(application=application, role=_auth_role(), user_id=user_id):
        return jsonify({"error": "forbidden"}), 403

    try:
        start_time = datetime.fromisoformat(data["start_time"])
        end_time = datetime.fromisoformat(data["end_time"])
    except ValueError:
        return jsonify({"error": "start_time and end_time must be ISO datetime"}), 400

    if end_time <= start_time:
        return jsonify({"error": "end_time must be later than start_time"}), 400

    interview = Interview(
        application_id=application.id,
        recruiter_id=user_id,
        start_time=start_time,
        end_time=end_time,
        meeting_link=(data.get("meeting_link") or "").strip() or None,
        status="scheduled",
    )
    db.session.add(interview)

    try:
        _update_application_status(
            application=application,
            new_status=APPLICATION_STATUS_INTERVIEW_SCHEDULED,
            changed_by_id=user_id,
            reason="interview_scheduled",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    _create_notification(
        recipient_user_id=application.candidate_id,
        notification_type="interview_scheduled",
        title="Da len lich phong van",
        message=(
            f"Ban co lich phong van cho ho so #{application.id} vao "
            f"{start_time.isoformat()} - {end_time.isoformat()}"
        ),
    )

    db.session.commit()
    return jsonify({"interview": interview.to_dict(), "application": application.to_dict()})


@job_bp.patch("/interviews/<int:interview_id>/feedback")
@require_auth(required_roles=["recruiter", "admin"])
def update_interview_feedback(interview_id: int):
    interview = Interview.query.get(interview_id)
    if not interview:
        return jsonify({"error": "interview not found"}), 404

    application = Application.query.get(interview.application_id)
    if not application:
        return jsonify({"error": "application not found"}), 404

    user_id = _auth_user_id()
    if not _can_manage_application(application=application, role=_auth_role(), user_id=user_id):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    outcome = (data.get("outcome") or "").strip().lower()
    feedback_text = (data.get("feedback_text") or "").strip()
    raw_score = data.get("evaluation_score")

    if outcome and outcome not in INTERVIEW_OUTCOME_TO_STATUS:
        allowed = ", ".join(sorted(INTERVIEW_OUTCOME_TO_STATUS.keys()))
        return jsonify({"error": f"outcome must be one of: {allowed}"}), 400

    if feedback_text:
        interview.feedback_text = feedback_text
    if raw_score not in (None, ""):
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            return jsonify({"error": "evaluation_score must be numeric"}), 400
        if score < 0 or score > 5:
            return jsonify({"error": "evaluation_score must be between 0 and 5"}), 400
        interview.evaluation_score = score

    if outcome:
        interview.outcome = outcome
        interview.status = "completed"
        target_status = INTERVIEW_OUTCOME_TO_STATUS[outcome]
        reason = feedback_text if target_status == APPLICATION_STATUS_REJECTED else None
        try:
            _update_application_status(
                application=application,
                new_status=target_status,
                changed_by_id=user_id,
                reason=reason,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409

    db.session.commit()
    return jsonify({"interview": interview.to_dict(), "application": application.to_dict()})


@job_bp.get("/recruiter/dashboard")
@require_auth(required_roles=["recruiter", "admin"])
def recruiter_dashboard():
    user_id = _auth_user_id()
    role = _auth_role()

    jobs_query = Job.query.join(Company, Job.company_id == Company.id)
    apps_query = Application.query.join(Job, Application.job_id == Job.id).join(Company, Job.company_id == Company.id)

    if role == "recruiter":
        jobs_query = jobs_query.filter(Company.recruiter_id == user_id)
        apps_query = apps_query.filter(Company.recruiter_id == user_id)

    jobs_total = jobs_query.count()
    jobs_active = jobs_query.filter(Job.is_active.is_(True)).count()
    applications_total = apps_query.count()
    status_counts = _status_counts_for_query(apps_query)

    return jsonify(
        {
            "jobs_total": jobs_total,
            "jobs_active": jobs_active,
            "applications_total": applications_total,
            "counts_by_status": status_counts,
        }
    )


@job_bp.get("/candidate/notifications")
@require_auth(required_roles=["candidate", "admin"])
def candidate_notifications():
    user_id = _auth_user_id()
    notifications = (
        Notification.query.filter_by(recipient_user_id=user_id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify({"notifications": [item.to_dict() for item in notifications]})


@job_bp.patch("/candidate/notifications/<int:notification_id>/read")
@require_auth(required_roles=["candidate", "admin"])
def mark_notification_read(notification_id: int):
    user_id = _auth_user_id()
    notification = Notification.query.filter_by(id=notification_id, recipient_user_id=user_id).first()
    if not notification:
        return jsonify({"error": "notification not found"}), 404

    notification.is_read = True
    db.session.commit()
    return jsonify({"notification": notification.to_dict()})
