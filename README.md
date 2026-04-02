# Smart Recruitment and HR Platform

Flask microservices project for recruitment and smart HR management with:
- Candidate and recruiter authentication
- Job posting, listing, search, and filtering
- Candidate job applications
- LinkedIn registration and profile sync hooks
- Google OAuth registration/login
- Google Calendar interview scheduling
- Gmail interview invitation sending
- AI candidate screening and potential-candidate ranking
- RabbitMQ event publishing

## Services

- Account Service: `http://localhost:5001`
- Job Service: `http://localhost:5002`
- Integration Service: `http://localhost:5003`
- Frontend (Jinja): `http://localhost:5004`
- API Gateway: `http://localhost:8000`
- RabbitMQ management: `http://localhost:15672`

## Quick Start with Docker

1. Copy environment file:

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

2. Fill integration credentials in `.env`:
- `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`
- `LINKEDIN_REDIRECT_URI` should match your LinkedIn app callback, recommended: `http://localhost:5003/api/integrations/linkedin/callback`
- `LINKEDIN_FRONTEND_CALLBACK_URI` should point to frontend callback page: `http://localhost:5004/oauth/linkedin/callback`
- `LINKEDIN_SCOPE` optional, default: `r_liteprofile r_emailaddress`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI` should match your Google OAuth callback, recommended: `http://localhost:5003/api/integrations/google/callback`
- `GOOGLE_FRONTEND_CALLBACK_URI` should point to frontend callback page: `http://localhost:5004/oauth/google/callback`
- `GOOGLE_SCOPE` optional, default: `openid email profile`
- OAuth and API tokens for Gmail and Google Calendar
- `AI_API_URL` and `AI_POTENTIAL_CANDIDATES_URL` if using remote AI service

If LinkedIn shows `invalid_scope_error`, usually the app does not have permission for the requested scope:
- Set `LINKEDIN_SCOPE` to a scope your LinkedIn app is allowed to use

3. Start stack:

```bash
docker compose up --build
```

4. Open UI:
- Frontend: `http://localhost:5004`
- Gateway API base: `http://localhost:8000`

## Local Start without Docker

Create and activate a virtual environment, then install dependencies per service:

```bash
pip install -r backend/account/requirements.txt
pip install -r backend/job/requirements.txt
pip install -r backend/integration/requirements.txt
pip install -r backend/gateway/requirements.txt
pip install -r frontend/requirements.txt
```

Run each service in separate terminals:

```bash
python backend/account/app.py
python backend/job/app.py
python backend/integration/app.py
python backend/gateway/app.py
python frontend/app.py
```

## Implemented API Highlights

### Account Service
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/linkedin/register`
- `POST /api/auth/google/register`
- `POST /api/auth/linkedin/sync`
- `GET /api/auth/me`

### Job Service
- `GET /api/jobs` with query params: `q`, `location`, `job_type`, `experience_level`, `salary_min`, `salary_max`
- `POST /api/jobs`
- `POST /api/jobs/{job_id}/apply`
- `POST /api/jobs/{job_id}/ai/potential-candidates`
- `POST /api/interviews/schedule`

### Integration Service
- `GET /api/integrations/linkedin/auth-url`
- `POST /api/integrations/linkedin/token`
- `GET /api/integrations/linkedin/profile`
- `GET /api/integrations/google/auth-url`
- `POST /api/integrations/google/token`
- `GET /api/integrations/google/profile`
- `POST /api/integrations/gmail/send`
- `POST /api/integrations/calendar/schedule`
- `POST /api/integrations/ai/screen`
- `POST /api/integrations/ai/potential-candidates`

## Current Scope in This First Implementation

- Full foundation for authentication, jobs, and integration flows
- Recruiter dashboard actions for company/job management and interview scheduling
- Candidate dashboard actions for LinkedIn sync and application tracking
- Search and filtering on public job listing page

## Next Implementation Steps

- Replace manual token fields in UI with complete OAuth callback flows
- Add admin service and admin dashboard modules
- Add notification consumer workers and retry policies
- Add automated tests and CI pipeline

## Service Verification Script

Use this script to verify docker runtime, service health, gateway proxy, and social OAuth readiness:

PowerShell:
./scripts/check-services.ps1

Optional: start core services before checking:
./scripts/check-services.ps1 -StartStack

Current expected warnings in this version:
- LinkedIn auth-url warns when LINKEDIN_CLIENT_ID is empty in .env
- Google auth-url warns when GOOGLE_CLIENT_ID is empty in .env
