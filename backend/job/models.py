from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


APPLICATION_STATUS_APPLIED = "applied"
APPLICATION_STATUS_REVIEWING = "reviewing"
APPLICATION_STATUS_SHORTLISTED = "shortlisted"
APPLICATION_STATUS_INTERVIEW_SCHEDULED = "interview_scheduled"
APPLICATION_STATUS_OFFER_SENT = "offer_sent"
APPLICATION_STATUS_HIRED = "hired"
APPLICATION_STATUS_REJECTED = "rejected"
APPLICATION_STATUS_WITHDRAWN = "withdrawn"
APPLICATION_STATUS_ON_HOLD = "on_hold"

ALLOWED_APPLICATION_STATUSES = {
    APPLICATION_STATUS_APPLIED,
    APPLICATION_STATUS_REVIEWING,
    APPLICATION_STATUS_SHORTLISTED,
    APPLICATION_STATUS_INTERVIEW_SCHEDULED,
    APPLICATION_STATUS_OFFER_SENT,
    APPLICATION_STATUS_HIRED,
    APPLICATION_STATUS_REJECTED,
    APPLICATION_STATUS_WITHDRAWN,
    APPLICATION_STATUS_ON_HOLD,
}

TERMINAL_APPLICATION_STATUSES = {
    APPLICATION_STATUS_HIRED,
    APPLICATION_STATUS_REJECTED,
    APPLICATION_STATUS_WITHDRAWN,
}


def _json_loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    recruiter_id = db.Column(db.Integer, nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    website = db.Column(db.String(255), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs = db.relationship("Job", back_populates="company", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "recruiter_id": self.recruiter_id,
            "name": self.name,
            "description": self.description,
            "website": self.website,
            "logo_url": self.logo_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(120), nullable=False)
    job_type = db.Column(db.String(60), nullable=False)
    experience_level = db.Column(db.String(60), nullable=False)
    salary_min = db.Column(db.Float, nullable=True)
    salary_max = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship("Company", back_populates="jobs")
    applications = db.relationship("Application", back_populates="job", cascade="all, delete-orphan")
    saved_jobs = db.relationship("SavedJob", back_populates="job", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "company_id": self.company_id,
            "company_name": self.company.name if self.company else None,
            "title": self.title,
            "description": self.description,
            "requirements": self.requirements,
            "location": self.location,
            "job_type": self.job_type,
            "experience_level": self.experience_level,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "is_active": self.is_active,
            "applications_count": len(self.applications),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CandidateProfile(db.Model):
    __tablename__ = "candidate_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, unique=True)
    full_name = db.Column(db.String(255), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    headline = db.Column(db.String(255), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    skills_json = db.Column(db.Text, nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "full_name": self.full_name,
            "contact_email": self.contact_email,
            "phone": self.phone,
            "headline": self.headline,
            "summary": self.summary,
            "skills": _json_loads(self.skills_json) or [],
            "experience_years": self.experience_years,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CandidateCV(db.Model):
    __tablename__ = "candidate_cvs"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=True)
    resume_text = db.Column(db.Text, nullable=True)
    builder_json = db.Column(db.Text, nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    applications = db.relationship("Application", back_populates="cv")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "title": self.title,
            "file_path": self.file_path,
            "download_url": f"/api/cvs/{self.id}/download" if self.file_path else None,
            "resume_text": self.resume_text,
            "builder": _json_loads(self.builder_json) or {},
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SavedJob(db.Model):
    __tablename__ = "saved_jobs"
    __table_args__ = (db.UniqueConstraint("candidate_id", "job_id", name="uq_saved_job_candidate_job"),)

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    job = db.relationship("Job", back_populates="saved_jobs")

    def to_dict(self):
        payload = {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if self.job:
            payload["job"] = self.job.to_dict()
        return payload


class Application(db.Model):
    __tablename__ = "applications"
    __table_args__ = (db.UniqueConstraint("job_id", "candidate_id", name="uq_application_job_candidate"),)

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    candidate_id = db.Column(db.Integer, nullable=False, index=True)
    candidate_name = db.Column(db.String(255), nullable=True)
    candidate_email = db.Column(db.String(255), nullable=True)
    cv_id = db.Column(db.Integer, db.ForeignKey("candidate_cvs.id"), nullable=False)
    cover_letter = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False, default=APPLICATION_STATUS_APPLIED)
    rejection_reason = db.Column(db.Text, nullable=True)
    stage_updated_by = db.Column(db.Integer, nullable=True)
    stage_updated_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    job = db.relationship("Job", back_populates="applications")
    cv = db.relationship("CandidateCV", back_populates="applications")
    interviews = db.relationship("Interview", back_populates="application", cascade="all, delete-orphan")
    status_history = db.relationship(
        "ApplicationStatusHistory",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.changed_at.desc()",
    )
    notes = db.relationship(
        "ApplicationNote",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationNote.created_at.desc()",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_title": self.job.title if self.job else None,
            "company_name": self.job.company.name if self.job and self.job.company else None,
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "candidate_email": self.candidate_email,
            "cv_id": self.cv_id,
            "cv_title": self.cv.title if self.cv else None,
            "cv_download_url": f"/api/cvs/{self.cv_id}/download" if self.cv and self.cv.file_path else None,
            "cover_letter": self.cover_letter,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "stage_updated_by": self.stage_updated_by,
            "stage_updated_at": self.stage_updated_at.isoformat() if self.stage_updated_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "notes_count": len(self.notes),
            "interviews_count": len(self.interviews),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ApplicationStatusHistory(db.Model):
    __tablename__ = "application_status_history"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    old_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    changed_by_id = db.Column(db.Integer, nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    application = db.relationship("Application", back_populates="status_history")

    def to_dict(self):
        return {
            "id": self.id,
            "application_id": self.application_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "reason": self.reason,
            "changed_by_id": self.changed_by_id,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
        }


class ApplicationNote(db.Model):
    __tablename__ = "application_notes"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    recruiter_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    application = db.relationship("Application", back_populates="notes")

    def to_dict(self):
        return {
            "id": self.id,
            "application_id": self.application_id,
            "recruiter_id": self.recruiter_id,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Interview(db.Model):
    __tablename__ = "interviews"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    recruiter_id = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    meeting_link = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="scheduled")
    outcome = db.Column(db.String(50), nullable=True)
    feedback_text = db.Column(db.Text, nullable=True)
    evaluation_score = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    application = db.relationship("Application", back_populates="interviews")

    def to_dict(self):
        return {
            "id": self.id,
            "application_id": self.application_id,
            "recruiter_id": self.recruiter_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "meeting_link": self.meeting_link,
            "status": self.status,
            "outcome": self.outcome,
            "feedback_text": self.feedback_text,
            "evaluation_score": self.evaluation_score,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(db.Integer, nullable=False, index=True)
    notification_type = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "recipient_user_id": self.recipient_user_id,
            "notification_type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
