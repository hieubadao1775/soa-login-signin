import os

from flask import Flask, render_template


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["API_BASE_URL"] = os.getenv("API_BASE_URL", "http://localhost:8000")

    @app.get("/")
    def index():
        return render_template("index.html", page="home", api_base=app.config["API_BASE_URL"])

    @app.get("/login")
    def login_page():
        return render_template("login.html", page="login", api_base=app.config["API_BASE_URL"])

    @app.get("/register")
    def register_page():
        return render_template("register.html", page="register", api_base=app.config["API_BASE_URL"])

    @app.get("/candidate")
    def candidate_page():
        return render_template("candidate.html", page="candidate", api_base=app.config["API_BASE_URL"])

    @app.get("/candidate/applications")
    def candidate_applications_page():
        return render_template(
            "candidate_applications.html",
            page="candidate-applications",
            api_base=app.config["API_BASE_URL"],
        )

    @app.get("/recruiter")
    def recruiter_page():
        return render_template("recruiter.html", page="recruiter", api_base=app.config["API_BASE_URL"])

    @app.get("/jobs/<int:job_id>/apply")
    def apply_job_page(job_id: int):
        return render_template(
            "job_apply.html",
            page="job-apply",
            api_base=app.config["API_BASE_URL"],
            job_id=job_id,
        )

    @app.get("/oauth/linkedin/callback")
    def linkedin_callback_page():
        return render_template(
            "oauth_linkedin_callback.html",
            page="linkedin-callback",
            api_base=app.config["API_BASE_URL"],
        )

    @app.get("/oauth/google/callback")
    def google_callback_page():
        return render_template(
            "oauth_google_callback.html",
            page="google-callback",
            api_base=app.config["API_BASE_URL"],
        )

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5004, debug=True)
