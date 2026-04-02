import os

import requests
from flask import Flask, Response, jsonify, redirect, request
from flask_cors import CORS


ACCOUNT_SERVICE_URL = os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:5001")
JOB_SERVICE_URL = os.getenv("JOB_SERVICE_URL", "http://localhost:5002")
INTEGRATION_SERVICE_URL = os.getenv("INTEGRATION_SERVICE_URL", "http://localhost:5003")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5004")


app = Flask(__name__)
CORS(app, supports_credentials=True)


def _proxy(base_url: str, target_path: str):
    target_url = f"{base_url.rstrip('/')}/{target_path.lstrip('/')}"

    headers = {
        key: value
        for key, value in request.headers
        if key.lower() not in {"host", "content-length"}
    }

    try:
        response = requests.request(
            method=request.method,
            url=target_url,
            params=request.args,
            data=request.get_data(),
            headers=headers,
            timeout=25,
        )
    except requests.RequestException as exc:
        return jsonify({"error": f"gateway proxy failed: {exc}"}), 502

    filtered_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in {"content-encoding", "content-length", "transfer-encoding", "connection"}
    }

    return Response(response.content, response.status_code, filtered_headers)


@app.get("/health")
def health_check():
    return jsonify({"service": "gateway", "status": "ok"})


@app.get("/")
def root():
    return redirect(FRONTEND_URL, code=302)


@app.route("/api/auth/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def auth_proxy(subpath: str):
    return _proxy(ACCOUNT_SERVICE_URL, f"api/auth/{subpath}")


@app.route("/api/companies", methods=["GET", "POST", "OPTIONS"])
def companies_proxy():
    return _proxy(JOB_SERVICE_URL, "api/companies")


@app.route("/api/companies/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def companies_subpath_proxy(subpath: str):
    return _proxy(JOB_SERVICE_URL, f"api/companies/{subpath}")


@app.route("/api/jobs", methods=["GET", "POST", "OPTIONS"])
def jobs_proxy():
    return _proxy(JOB_SERVICE_URL, "api/jobs")


@app.route("/api/jobs/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def job_subpath_proxy(subpath: str):
    return _proxy(JOB_SERVICE_URL, f"api/jobs/{subpath}")


@app.route("/api/applications/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def applications_proxy(subpath: str):
    return _proxy(JOB_SERVICE_URL, f"api/applications/{subpath}")


@app.route("/api/candidate/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def candidate_proxy(subpath: str):
    return _proxy(JOB_SERVICE_URL, f"api/candidate/{subpath}")


@app.route("/api/cvs/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def cv_proxy(subpath: str):
    return _proxy(JOB_SERVICE_URL, f"api/cvs/{subpath}")


@app.route("/api/recruiter/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def recruiter_proxy(subpath: str):
    return _proxy(JOB_SERVICE_URL, f"api/recruiter/{subpath}")


@app.route("/api/interviews/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def interviews_proxy(subpath: str):
    return _proxy(JOB_SERVICE_URL, f"api/interviews/{subpath}")


@app.route("/api/integrations/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def integrations_proxy(subpath: str):
    return _proxy(INTEGRATION_SERVICE_URL, f"api/integrations/{subpath}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
