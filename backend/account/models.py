from datetime import datetime
import json

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="candidate")
    full_name = db.Column(db.String(255), nullable=False)
    linkedin_id = db.Column(db.String(128), nullable=True)
    linkedin_profile_json = db.Column(db.Text, nullable=True)
    google_id = db.Column(db.String(128), nullable=True)
    google_profile_json = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    profile_updated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        linkedin_profile = None
        if self.linkedin_profile_json:
            try:
                linkedin_profile = json.loads(self.linkedin_profile_json)
            except json.JSONDecodeError:
                linkedin_profile = None

        google_profile = None
        if self.google_profile_json:
            try:
                google_profile = json.loads(self.google_profile_json)
            except json.JSONDecodeError:
                google_profile = None

        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "full_name": self.full_name,
            "phone": self.phone,
            "address": self.address,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "bio": self.bio,
            "profile_updated_at": self.profile_updated_at.isoformat() if self.profile_updated_at else None,
            "linkedin_id": self.linkedin_id,
            "linkedin_profile": linkedin_profile,
            "google_id": self.google_id,
            "google_profile": google_profile,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }
