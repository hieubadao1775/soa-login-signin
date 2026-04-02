from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def generate_token(user_id: int, role: str, secret_key: str, algorithm: str, expire_minutes: int) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_token(token: str, secret_key: str, algorithm: str) -> dict:
    return jwt.decode(token, secret_key, algorithms=[algorithm])


def require_auth(required_roles=None):
    required_roles = required_roles or []

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Missing bearer token"}), 401

            token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = decode_token(
                    token,
                    current_app.config["SECRET_KEY"],
                    current_app.config["JWT_ALGORITHM"],
                )
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

            user_role = payload.get("role")
            if required_roles and user_role not in required_roles:
                return jsonify({"error": "Forbidden"}), 403

            g.auth_payload = payload
            return func(*args, **kwargs)

        return wrapper

    return decorator
