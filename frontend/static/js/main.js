const API_BASE = window.APP_CONFIG?.apiBase || "http://localhost:8000";
const PAGE = window.APP_CONFIG?.page || "";

const TOKEN_KEY = "srh_token";
const USER_KEY = "srh_user";
let cachedPublicJobs = [];

function showStatus(message, type = "info") {
    const node = document.getElementById("global-status");
    if (!node) {
        return;
    }

    node.textContent = message;
    node.classList.remove("hidden", "error", "success");
    if (type === "error") {
        node.classList.add("error");
    }
    if (type === "success") {
        node.classList.add("success");
    }

    setTimeout(() => node.classList.add("hidden"), 4500);
}

function setSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user || null));
    syncTopNavigation();
}

function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    syncTopNavigation();
}

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function getUser() {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function normalizeRole(role) {
    if ((role || "").toString().trim().toLowerCase() === "recruiter") {
        return "recruiter";
    }
    return "candidate";
}

function normalizeSignupRole(role) {
    const raw = (role || "").toString().trim().toLowerCase();
    if (raw === "candidate") {
        return "candidate";
    }
    if (raw === "recruiter" || raw === "hr") {
        return "recruiter";
    }
    return "";
}

function isAuthenticated() {
    return Boolean(getToken() && getUser());
}

function setElementVisible(node, isVisible) {
    if (!node) {
        return;
    }
    node.classList.toggle("hidden", !isVisible);
}

function syncTopNavigation() {
    const user = getUser();
    const loggedIn = isAuthenticated();
    const role = normalizeRole(user?.role);

    setElementVisible(document.getElementById("nav-candidate"), loggedIn && role === "candidate");
    setElementVisible(document.getElementById("nav-candidate-applications"), loggedIn && role === "candidate");
    setElementVisible(document.getElementById("nav-recruiter"), loggedIn && role === "recruiter");
    setElementVisible(document.getElementById("nav-login"), !loggedIn);
    setElementVisible(document.getElementById("nav-register"), !loggedIn);
    setElementVisible(document.getElementById("logout-btn"), loggedIn);

    const roleBadge = document.getElementById("nav-role-badge");
    if (!loggedIn) {
        setElementVisible(roleBadge, false);
        return;
    }

    if (roleBadge) {
        roleBadge.textContent = role === "recruiter" ? "Vai trò: HR" : "Vai trò: Ứng viên";
    }
    setElementVisible(roleBadge, true);
}

function guardPageAccess() {
    const protectedPages = new Set(["candidate", "candidate-applications", "recruiter"]);
    if (!protectedPages.has(PAGE)) {
        return true;
    }

    const loggedIn = isAuthenticated();
    const role = normalizeRole(getUser()?.role);

    if (!loggedIn) {
        window.location.href = "/login";
        return false;
    }

    if ((PAGE === "candidate" || PAGE === "candidate-applications") && role !== "candidate") {
        window.location.href = "/recruiter";
        return false;
    }

    if (PAGE === "recruiter" && role !== "recruiter") {
        window.location.href = "/candidate";
        return false;
    }

    return true;
}

function getRegisterRole() {
    const form = document.getElementById("register-form");
    if (!form) {
        return "";
    }

    const formData = new FormData(form);
    return normalizeSignupRole(formData.get("role"));
}

function getSocialProviderLabel(provider) {
    return provider === "linkedin" ? "LinkedIn" : "Google";
}

function getSocialCallbackStatusId(provider) {
    return provider === "linkedin" ? "linkedin-callback-status" : "google-callback-status";
}

function getSocialAuthUrlPath(provider) {
    return provider === "linkedin" ? "/api/integrations/linkedin/auth-url" : "/api/integrations/google/auth-url";
}

function getSocialRegisterPath(provider) {
    return provider === "linkedin" ? "/api/auth/linkedin/register" : "/api/auth/google/register";
}

function getSocialRolePanelElements(provider) {
    return {
        panelId: `${provider}-first-role-panel`,
        selectId: `${provider}-first-role-select`,
        submitId: `${provider}-first-role-submit`,
        cancelId: `${provider}-first-role-cancel`,
    };
}

function setCallbackStatus(provider, message, type = "info") {
    const node = document.getElementById(getSocialCallbackStatusId(provider));
    if (!node) {
        return;
    }

    node.textContent = message;
    node.classList.remove("error", "success");
    if (type === "error") {
        node.classList.add("error");
    }
    if (type === "success") {
        node.classList.add("success");
    }
}

async function apiRequest(path, options = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {}),
    };

    const token = getToken();
    if (token && !options.skipAuth) {
        headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}${path}`, {
        method: options.method || "GET",
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
    });

    let data = {};
    try {
        data = await response.json();
    } catch {
        data = {};
    }

    if (!response.ok) {
        const reason = data.error || `Request failed with status ${response.status}`;
        const requestError = new Error(reason);
        requestError.responseData = data;
        requestError.status = response.status;
        throw requestError;
    }

    return data;
}

async function apiMultipartRequest(path, formData, options = {}) {
    const headers = {
        ...(options.headers || {}),
    };

    const token = getToken();
    if (token && !options.skipAuth) {
        headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}${path}`, {
        method: options.method || "POST",
        headers,
        body: formData,
    });

    let data = {};
    try {
        data = await response.json();
    } catch {
        data = {};
    }

    if (!response.ok) {
        const reason = data.error || `Request failed with status ${response.status}`;
        const requestError = new Error(reason);
        requestError.responseData = data;
        requestError.status = response.status;
        throw requestError;
    }

    return data;
}

function formatSalary(job) {
    if (job.salary_min == null && job.salary_max == null) {
        return "Lương: Thỏa thuận";
    }
    return `Lương: ${job.salary_min || 0} - ${job.salary_max || 0}`;
}

const STATUS_LABELS = Object.freeze({
    applied: "Applied",
    reviewing: "Reviewing",
    shortlisted: "Shortlisted",
    interview_scheduled: "Interview Scheduled",
    offer_sent: "Offer Sent",
    hired: "Hired",
    rejected: "Rejected",
    withdrawn: "Withdrawn",
    on_hold: "On Hold",
});

const STATUS_ORDER = Object.keys(STATUS_LABELS);
const TERMINAL_APPLICATION_STATUSES = new Set(["hired", "rejected", "withdrawn"]);

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function formatStatusLabel(status) {
    const normalized = (status || "").toString().trim().toLowerCase();
    return STATUS_LABELS[normalized] || normalized || "Unknown";
}

function formatDateTime(value) {
    const raw = (value || "").toString().trim();
    if (!raw) {
        return "N/A";
    }

    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) {
        return raw;
    }

    return date.toLocaleString("vi-VN");
}

function statusBadgeMarkup(status) {
    const normalized = (status || "").toString().trim().toLowerCase() || "unknown";
    return `<span class="status-pill status-${escapeHtml(normalized)}">${escapeHtml(formatStatusLabel(normalized))}</span>`;
}

function buildStatusOptionsMarkup(selectedStatus) {
    const normalizedSelected = (selectedStatus || "").toString().trim().toLowerCase();
    return STATUS_ORDER
        .map(
            (status) =>
                `<option value="${status}" ${normalizedSelected === status ? "selected" : ""}>${escapeHtml(
                    formatStatusLabel(status)
                )}</option>`
        )
        .join("");
}

function buildStatusChipsMarkup(countsByStatus) {
    return STATUS_ORDER
        .map((status) => {
            const count = Number(countsByStatus?.[status] || 0);
            return `
                <article class="status-chip">
                    <span>${escapeHtml(formatStatusLabel(status))}</span>
                    <strong>${count}</strong>
                </article>
            `;
        })
        .join("");
}

function buildNotesMarkup(notes, emptyMessage = "Chưa có ghi chú.") {
    if (!notes || notes.length === 0) {
        return `<div class="stack-item">${escapeHtml(emptyMessage)}</div>`;
    }

    return notes
        .map(
            (note) => `
                <article class="stack-item note-item">
                    <strong>Recruiter #${escapeHtml(note.recruiter_id)}</strong>
                    <p>${escapeHtml(note.content || "")}</p>
                    <div class="note-meta">${escapeHtml(formatDateTime(note.created_at))}</div>
                </article>
            `
        )
        .join("");
}

function buildTimelineMarkup(data, options = {}) {
    const showNotes = Boolean(options.showNotes);
    const application = data?.application || {};
    const history = data?.status_history || [];
    const interviews = data?.interviews || [];
    const notes = data?.notes || [];

    const historyMarkup = history.length
        ? history
              .map((item) => {
                  const oldStatus = item.old_status ? `${formatStatusLabel(item.old_status)} -> ` : "";
                  const reason = item.reason ? ` • ${item.reason}` : "";
                  return `
                    <li class="timeline-item">
                        <strong>${escapeHtml(oldStatus)}${escapeHtml(formatStatusLabel(item.new_status))}</strong>
                        <div class="meta">By #${escapeHtml(item.changed_by_id)} • ${escapeHtml(
                      formatDateTime(item.changed_at)
                  )}${escapeHtml(reason)}</div>
                    </li>
                  `;
              })
              .join("")
        : `<li class="timeline-item">Chưa có lịch sử trạng thái.</li>`;

    const interviewMarkup = interviews.length
        ? interviews
              .map(
                  (item) => `
                    <li class="timeline-item">
                        <strong>Interview #${escapeHtml(item.id)} • ${escapeHtml(item.status || "scheduled")}</strong>
                        <div class="meta">${escapeHtml(formatDateTime(item.start_time))} - ${escapeHtml(
                      formatDateTime(item.end_time)
                  )}</div>
                        <div class="meta">Outcome: ${escapeHtml(item.outcome || "pending")}</div>
                    </li>
                  `
              )
              .join("")
        : `<li class="timeline-item">Chưa có lịch phỏng vấn.</li>`;

    const notesSection = showNotes
        ? `
            <div class="timeline-block">
                <h4>Notes nội bộ</h4>
                ${buildNotesMarkup(notes, "Chưa có notes nội bộ.")}
            </div>
        `
        : "";

    return `
        <article class="stack-item">
            <div class="app-card-header">
                <strong>Application #${escapeHtml(application.id || "")}</strong>
                ${statusBadgeMarkup(application.status)}
            </div>
            <p class="job-meta">Job #${escapeHtml(application.job_id || "")} • Candidate #${escapeHtml(
        application.candidate_id || ""
    )}</p>
            <div class="timeline-block">
                <h4>Lịch sử trạng thái</h4>
                <ul class="timeline-list">${historyMarkup}</ul>
            </div>
            <div class="timeline-block">
                <h4>Phỏng vấn</h4>
                <ul class="timeline-list">${interviewMarkup}</ul>
            </div>
            ${notesSection}
        </article>
    `;
}

function renderJobs(jobs) {
    const container = document.getElementById("jobs-container");
    if (!container) {
        return;
    }

    const user = getUser();
    const loggedIn = isAuthenticated();
    const role = normalizeRole(user?.role);

    if (!jobs || jobs.length === 0) {
        container.innerHTML = `<div class="stack-item">Không tìm thấy job phù hợp.</div>`;
        return;
    }

    container.innerHTML = jobs
        .map((job) => {
            const isCandidate = loggedIn && role === "candidate";
            const isRecruiter = loggedIn && role === "recruiter";

            let actionMarkup = "";
            if (!loggedIn) {
                actionMarkup = `<button class="primary-btn apply-action" type="button" data-apply-id="${job.id}">Đăng nhập để ứng tuyển</button>`;
            } else if (isCandidate) {
                actionMarkup = `
                    <div class="inline-actions">
                        <button class="primary-btn apply-action" type="button" data-apply-id="${job.id}">Ứng tuyển ngay</button>
                        <button class="ghost-btn save-job-action" type="button" data-save-id="${job.id}">Lưu job</button>
                    </div>
                `;
            } else if (!isRecruiter) {
                actionMarkup = `<button class="ghost-btn apply-action" type="button" data-apply-id="${job.id}">Không khả dụng</button>`;
            }

            return `
                <article class="job-card">
                    <h3>${job.title}</h3>
                    <p class="job-meta">${job.company_name || "Chưa có công ty"} • ${job.location}</p>
                    <p>${(job.description || "").slice(0, 140)}...</p>
                    <div class="tag-row">
                        <span class="tag">${job.job_type}</span>
                        <span class="tag">${job.experience_level}</span>
                    </div>
                    <p class="job-meta">${formatSalary(job)}</p>
                    ${actionMarkup}
                </article>
            `;
        })
        .join("");

    container.querySelectorAll("[data-apply-id]").forEach((button) => {
        button.addEventListener("click", async () => {
            const jobId = button.getAttribute("data-apply-id");
            await applyJob(jobId);
        });
    });

    container.querySelectorAll("[data-save-id]").forEach((button) => {
        button.addEventListener("click", async () => {
            const jobId = button.getAttribute("data-save-id");
            await saveJobForCandidate(jobId);
        });
    });
}

async function loadJobs() {
    const searchForm = document.getElementById("job-search-form");
    const params = new URLSearchParams();

    if (searchForm) {
        const formData = new FormData(searchForm);
        for (const [key, value] of formData.entries()) {
            if (value) {
                params.set(key, value.toString());
            }
        }
    }

    try {
        const data = await apiRequest(`/api/jobs?${params.toString()}`, { skipAuth: true });
        cachedPublicJobs = data.jobs || [];
        renderJobs(cachedPublicJobs);
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function applyJob(jobId) {
    const token = getToken();
    const user = getUser();

    if (!token || !user) {
        showStatus("Bạn cần đăng nhập tài khoản ứng viên trước khi nộp hồ sơ.", "error");
        setTimeout(() => {
            window.location.href = "/login";
        }, 400);
        return;
    }

    if (normalizeRole(user.role) !== "candidate") {
        showStatus("Vai trò HR không thể nộp hồ sơ. Chỉ ứng viên mới nộp được.", "error");
        return;
    }

    window.location.href = `/jobs/${jobId}/apply`;
}

async function saveJobForCandidate(jobId) {
    const user = getUser();
    if (!isAuthenticated() || normalizeRole(user?.role) !== "candidate") {
        showStatus("Bạn cần đăng nhập tài khoản ứng viên để lưu job.", "error");
        return;
    }

    try {
        await apiRequest(`/api/candidate/saved-jobs/${jobId}`, {
            method: "POST",
        });
        showStatus("Đã lưu job thành công", "success");
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function submitJobApplicationForm(event) {
    event.preventDefault();

    const user = getUser();
    if (!user || normalizeRole(user.role) !== "candidate") {
        showStatus("Chỉ tài khoản ứng viên mới có thể nộp hồ sơ.", "error");
        return;
    }

    const jobId = (document.getElementById("apply-job-id")?.value || "").trim();
    const cvId = (document.getElementById("apply-cv-id")?.value || "").trim();
    const resumeFileInput = document.getElementById("apply-resume-file");
    const cvTitleInput = document.getElementById("apply-cv-title");
    const coverLetterInput = document.getElementById("apply-cover-letter");

    const resumeFile = resumeFileInput?.files?.[0] || null;
    const cvTitle = (cvTitleInput?.value || "").trim();
    const coverLetter = (coverLetterInput?.value || "").trim();

    if (!jobId) {
        showStatus("Thiếu thông tin công việc cần ứng tuyển.", "error");
        return;
    }

    if (!resumeFile && !cvId) {
        showStatus("Vui lòng chọn CV đã lưu hoặc tải CV mới để nộp hồ sơ.", "error");
        return;
    }

    try {
        if (resumeFile) {
            const formData = new FormData();
            formData.append("resume_file", resumeFile);
            if (coverLetter) {
                formData.append("cover_letter", coverLetter);
            }
            if (cvTitle) {
                formData.append("cv_title", cvTitle);
            }
            if (cvId) {
                formData.append("cv_id", cvId);
            }
            if (user?.full_name) {
                formData.append("candidate_name", user.full_name);
            }
            if (user?.email) {
                formData.append("candidate_email", user.email);
            }
            await apiMultipartRequest(`/api/jobs/${jobId}/apply`, formData);
        } else {
            await apiRequest(`/api/jobs/${jobId}/apply`, {
                method: "POST",
                body: {
                    cv_id: Number(cvId),
                    cover_letter: coverLetter,
                    candidate_name: user?.full_name,
                    candidate_email: user?.email,
                },
            });
        }

        showStatus("Nộp hồ sơ thành công", "success");
        setTimeout(() => {
            window.location.href = "/candidate/applications";
        }, 800);
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function loadCandidateCvOptionsForApply() {
    const cvSelect = document.getElementById("apply-cv-id");
    if (!cvSelect) {
        return;
    }

    try {
        const data = await apiRequest("/api/candidate/cvs");
        const cvs = data.cvs || [];
        if (!cvs.length) {
            cvSelect.innerHTML = `<option value="">Chưa có CV đã lưu, hãy tải CV mới bên dưới</option>`;
            return;
        }

        cvSelect.innerHTML = `
            <option value="">Chọn CV đã lưu</option>
            ${cvs
                .map(
                    (cv) =>
                        `<option value="${cv.id}" ${cv.is_default ? "selected" : ""}>${escapeHtml(cv.title)}${
                            cv.is_default ? " (mặc định)" : ""
                        }</option>`
                )
                .join("")}
        `;
    } catch (error) {
        cvSelect.innerHTML = `<option value="">Không tải được danh sách CV</option>`;
        showStatus(error.message, "error");
    }
}

async function bindJobApplyPage() {
    const pageRoot = document.getElementById("job-apply-page");
    const applyForm = document.getElementById("job-apply-form");
    const jobInfoNode = document.getElementById("job-apply-info");

    if (!pageRoot || !applyForm || !jobInfoNode) {
        return;
    }

    const jobId = (pageRoot.getAttribute("data-job-id") || "").trim();
    if (!jobId) {
        jobInfoNode.classList.add("error");
        jobInfoNode.textContent = "Thiếu mã công việc để nộp hồ sơ.";
        return;
    }

    const user = getUser();
    if (!isAuthenticated()) {
        showStatus("Bạn cần đăng nhập tài khoản ứng viên để nộp hồ sơ.", "error");
        setTimeout(() => {
            window.location.href = "/login";
        }, 400);
        return;
    }

    if (normalizeRole(user?.role) !== "candidate") {
        showStatus("Trang nộp hồ sơ chỉ dành cho ứng viên.", "error");
        setTimeout(() => {
            window.location.href = "/recruiter";
        }, 500);
        return;
    }

    try {
        const jobData = await apiRequest(`/api/jobs/${jobId}`, { skipAuth: true });
        const job = jobData.job || {};
        jobInfoNode.classList.remove("error");
        jobInfoNode.innerHTML = `
            <strong>${escapeHtml(job.title || "N/A")}</strong>
            <p class="job-meta">${escapeHtml(job.company_name || "Chưa có công ty")} • ${escapeHtml(job.location || "N/A")}</p>
            <p class="job-meta">Company ID: #${escapeHtml(job.company_id || "N/A")}</p>
            <p>${escapeHtml((job.description || "").slice(0, 260))}${(job.description || "").length > 260 ? "..." : ""}</p>
        `;
    } catch (error) {
        jobInfoNode.classList.add("error");
        jobInfoNode.textContent = `Không tải được công việc: ${error.message}`;
    }

    await loadCandidateCvOptionsForApply();
    applyForm.addEventListener("submit", submitJobApplicationForm);
}

function bindHomePage() {
    const searchForm = document.getElementById("job-search-form");
    if (searchForm) {
        searchForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            await loadJobs();
        });
    }

    const refreshButton = document.getElementById("refresh-jobs-btn");
    if (refreshButton) {
        refreshButton.addEventListener("click", loadJobs);
    }

    loadJobs();
}

function bindLoginPage() {
    const form = document.getElementById("login-form");
    if (!form) {
        return;
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(form);

        try {
            const data = await apiRequest("/api/auth/login", {
                method: "POST",
                body: {
                    email: formData.get("email"),
                    password: formData.get("password"),
                },
                skipAuth: true,
            });

            setSession(data.token, data.user);
            showStatus("Đăng nhập thành công", "success");

            if (data.user.role === "recruiter") {
                window.location.href = "/recruiter";
                return;
            }
            window.location.href = "/candidate";
        } catch (error) {
            showStatus(error.message, "error");
        }
    });

    const forgotPasswordLink = document.getElementById("forgot-password-link");
    if (forgotPasswordLink) {
        forgotPasswordLink.addEventListener("click", (event) => {
            event.preventDefault();
            showStatus("Tính năng quên mật khẩu sẽ được bật ở pha tiếp theo.", "info");
        });
    }

    bindSocialAuthButtons();
}

function bindRegisterPage() {
    const form = document.getElementById("register-form");
    if (form) {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(form);

            const password = (formData.get("password") || "").toString();
            const confirmPassword = (formData.get("confirm_password") || "").toString();
            const hasAgreedTerms = !!formData.get("terms");

            if (password !== confirmPassword) {
                showStatus("Mật khẩu xác nhận không khớp.", "error");
                return;
            }

            if (!hasAgreedTerms) {
                showStatus("Bạn cần đồng ý điều khoản trước khi đăng ký.", "error");
                return;
            }

            const selectedRole = getRegisterRole();
            if (!selectedRole) {
                showStatus("Vui lòng chọn vai trò tài khoản (Ứng viên hoặc HR).", "error");
                return;
            }

            try {
                const data = await apiRequest("/api/auth/register", {
                    method: "POST",
                    body: {
                        email: formData.get("email"),
                        password,
                        full_name: formData.get("full_name"),
                        role: selectedRole,
                    },
                    skipAuth: true,
                });

                setSession(data.token, data.user);
                showStatus("Tạo tài khoản thành công", "success");
                window.location.href = data.user.role === "recruiter" ? "/recruiter" : "/candidate";
            } catch (error) {
                showStatus(error.message, "error");
            }
        });
    }

    bindSocialAuthButtons();
}

function normalizeGoogleProfile(profile) {
    const googleId =
        profile.sub ||
        profile.id ||
        profile.user_id ||
        `gg-${Date.now()}`;

    const fullName =
        profile.name ||
        `${profile.given_name || ""} ${profile.family_name || ""}`.trim() ||
        "Google User";

    const email =
        profile.email ||
        profile.email_address ||
        `${googleId}@google.local`;

    return {
        email,
        full_name: fullName,
        google_id: googleId,
        google_profile: {
            ...profile,
            full_name: fullName,
        },
    };
}

function normalizeLinkedinProfile(profile) {
    const linkedinId =
        profile.sub ||
        profile.id ||
        profile.user_id ||
        `li-${Date.now()}`;

    const fullName =
        profile.name ||
        `${profile.given_name || ""} ${profile.family_name || ""}`.trim() ||
        "LinkedIn User";

    const email =
        profile.email ||
        profile.email_address ||
        profile.preferred_username ||
        `${linkedinId}@linkedin.local`;

    return {
        email,
        full_name: fullName,
        linkedin_id: linkedinId,
        linkedin_profile: {
            ...profile,
            full_name: fullName,
        },
    };
}

function normalizeSocialMode(mode) {
    return mode === "register" ? "register" : "login";
}

function buildSocialState(mode) {
    const safeMode = normalizeSocialMode(mode);
    return `${safeMode}:${Date.now()}`;
}

function parseSocialState(rawState) {
    const fallback = { mode: "login" };
    const state = (rawState || "").trim().toLowerCase();
    if (!state) {
        return fallback;
    }

    const [modePart] = state.split(":");

    return {
        mode: normalizeSocialMode(modePart),
    };
}

async function startSocialOAuth(provider, mode) {
    const safeMode = normalizeSocialMode(mode);
    const params = new URLSearchParams();
    params.set("mode", safeMode);
    params.set("state", buildSocialState(safeMode));

    const data = await apiRequest(
        `${getSocialAuthUrlPath(provider)}?${params.toString()}`,
        {
            skipAuth: true,
        }
    );

    if (!data.auth_url) {
        throw new Error(`Khong lay duoc URL xac thuc ${getSocialProviderLabel(provider)}.`);
    }

    window.location.href = data.auth_url;
}

function bindSocialAuthButtons() {
    const buttons = document.querySelectorAll("[data-social-provider]");
    if (!buttons.length) {
        return;
    }

    buttons.forEach((button) => {
        button.addEventListener("click", async () => {
            const provider = button.getAttribute("data-social-provider");
            const mode = normalizeSocialMode(button.getAttribute("data-social-mode") || "login");

            if (provider !== "google" && provider !== "linkedin") {
                showStatus("Nha cung cap dang nhap khong hop le.", "error");
                return;
            }

            try {
                await startSocialOAuth(provider, mode);
            } catch (error) {
                showStatus(error.message, "error");
            }
        });
    });
}

function redirectAfterSocialAuth(user) {
    if (user?.role === "recruiter") {
        window.location.href = "/recruiter";
        return;
    }
    window.location.href = "/candidate";
}

function handleSocialAuthSuccess(account, mode, providerName, setStatus) {
    setSession(account.token, account.user);
    setStatus(
        account.is_new_user || mode === "register"
            ? `Dang ky ${providerName} thanh cong. Dang chuyen vao dashboard...`
            : `Dang nhap ${providerName} thanh cong. Dang chuyen vao dashboard...`,
        "success"
    );

    setTimeout(() => {
        redirectAfterSocialAuth(account.user);
    }, 900);
}

function showSocialFirstRolePanel(provider, basePayload, mode) {
    const providerLabel = getSocialProviderLabel(provider);
    const setStatus = (message, type = "info") => setCallbackStatus(provider, message, type);
    const { panelId, selectId, submitId, cancelId } = getSocialRolePanelElements(provider);
    const panel = document.getElementById(panelId);
    const select = document.getElementById(selectId);
    const submit = document.getElementById(submitId);
    const cancel = document.getElementById(cancelId);

    if (!panel || !select || !submit || !cancel) {
        setStatus("Khong mo duoc buoc chon vai tro. Vui long thu lai.", "error");
        return;
    }

    select.value = "";
    panel.classList.remove("hidden");
    setStatus(`Lan dau dang nhap ${providerLabel}. Vui long chon vai tro de hoan tat dang ky.`);

    submit.onclick = async () => {
        const selectedRole = normalizeSignupRole(select.value);
        if (!selectedRole) {
            setStatus("Vui long chon vai tro (Ung vien hoac HR).", "error");
            return;
        }

        try {
            setStatus("Dang hoan tat dang ky...");
            const account = await apiRequest(getSocialRegisterPath(provider), {
                method: "POST",
                body: {
                    ...basePayload,
                    role: selectedRole,
                },
                skipAuth: true,
            });

            panel.classList.add("hidden");
            handleSocialAuthSuccess(account, mode, providerLabel, setStatus);
        } catch (error) {
            setStatus(`Xac thuc ${providerLabel} that bai: ${error.message}`, "error");
        }
    };

    cancel.onclick = () => {
        panel.classList.add("hidden");
        setStatus("Ban da huy chon vai tro. Vui long dang nhap lai neu muon tiep tuc.", "error");
    };
}

async function processSocialCallbackPage(provider, options) {
    const providerLabel = getSocialProviderLabel(provider);
    const setStatus = (message, type = "info") => setCallbackStatus(provider, message, type);
    const query = new URLSearchParams(window.location.search);
    const code = (query.get("code") || "").trim();
    const state = query.get("state") || "";
    const parsedState = parseSocialState(state);
    const mode = parsedState.mode;
    const providerError = query.get("error");
    const providerErrorDescription = query.get("error_description");

    if (providerError) {
        if (options?.onProviderError?.(providerError, providerErrorDescription, setStatus)) {
            return;
        }

        const message = providerErrorDescription
            ? `${providerError}: ${providerErrorDescription}`
            : providerError;
        setStatus(`${providerLabel} tra ve loi xac thuc: ${message}`, "error");
        return;
    }

    if (!code) {
        setStatus(
            `Khong nhan duoc ma xac thuc tu ${providerLabel}. Vui long thu lai.`,
            "error"
        );
        return;
    }

    let payload = null;

    try {
        setStatus("Dang doi ma xac thuc lay access token...");
        const tokenData = await apiRequest(options.tokenPath, {
            method: "POST",
            body: { code },
            skipAuth: true,
        });

        const accessToken = tokenData.access_token;
        if (!accessToken) {
            throw new Error(`Khong nhan duoc access token ${providerLabel}.`);
        }

        setStatus(`Dang lay thong tin ho so ${providerLabel}...`);
        const profile = await apiRequest(options.profilePath, {
            method: "GET",
            headers: {
                Authorization: `Bearer ${accessToken}`,
            },
            skipAuth: true,
        });

        payload = options.normalizeProfile(profile);

        setStatus("Dang tao hoac khoi phuc tai khoan tren he thong...");
        const account = await apiRequest(getSocialRegisterPath(provider), {
            method: "POST",
            body: payload,
            skipAuth: true,
        });

        handleSocialAuthSuccess(account, mode, providerLabel, setStatus);
    } catch (error) {
        if (payload && error.responseData?.error_code === "role_required") {
            showSocialFirstRolePanel(provider, payload, mode);
            return;
        }

        setStatus(`Xac thuc ${providerLabel} that bai: ${error.message}`, "error");
    }
}

async function bindGoogleCallbackPage() {
    await processSocialCallbackPage("google", {
        tokenPath: "/api/integrations/google/token",
        profilePath: "/api/integrations/google/profile",
        normalizeProfile: normalizeGoogleProfile,
    });
}

async function bindLinkedinCallbackPage() {
    await processSocialCallbackPage("linkedin", {
        tokenPath: "/api/integrations/linkedin/token",
        profilePath: "/api/integrations/linkedin/profile",
        normalizeProfile: normalizeLinkedinProfile,
        onProviderError: (providerError, _providerErrorDescription, setStatus) => {
            if (!providerError || !providerError.toLowerCase().includes("invalid_scope")) {
                return false;
            }

            setStatus(
                "LinkedIn từ chối scope hiện tại. Hãy chỉnh LINKEDIN_SCOPE trong .env đúng quyền app rồi thử lại.",
                "error"
            );
            return true;
        },
    });
}

function renderCandidateApplications(applications) {
    const node = document.getElementById("applications-container");
    if (!node) {
        return;
    }

    if (!applications.length) {
        node.innerHTML = `<div class="stack-item">Bạn chưa có hồ sơ nào khớp bộ lọc hiện tại.</div>`;
        return;
    }

    node.innerHTML = applications
        .map((item) => {
            const canWithdraw = !TERMINAL_APPLICATION_STATUSES.has((item.status || "").toLowerCase());
            return `
                <article class="stack-item recruiter-app-card" data-application-id="${item.id}">
                    <div class="app-card-header">
                        <strong>Application #${escapeHtml(item.id)}</strong>
                        ${statusBadgeMarkup(item.status)}
                    </div>
                    <p class="job-meta">Job #${escapeHtml(item.job_id)} • ${escapeHtml(item.job_title || "N/A")}</p>
                    <p class="job-meta">CV: ${escapeHtml(item.cv_title || "N/A")} • Cập nhật: ${escapeHtml(
                formatDateTime(item.updated_at)
            )}</p>
                    ${
                        item.cv_download_url
                            ? `<p><a href="${escapeHtml(API_BASE + item.cv_download_url)}" target="_blank" rel="noopener">Tải CV đã nộp</a></p>`
                            : ""
                    }
                    <div class="inline-actions">
                        <button type="button" class="ghost-btn" data-candidate-action="timeline" data-application-id="${item.id}">Xem timeline</button>
                        <button type="button" class="ghost-btn" data-candidate-action="withdraw" data-application-id="${item.id}" ${
                canWithdraw ? "" : "disabled"
            }>Rút hồ sơ</button>
                    </div>
                </article>
            `;
        })
        .join("");
}

async function loadApplications() {
    const node = document.getElementById("applications-container");
    if (!node) {
        return;
    }

    const statusFilter = (document.getElementById("candidate-status-filter")?.value || "").trim();
    const params = new URLSearchParams();
    params.set("limit", "50");
    if (statusFilter) {
        params.set("status", statusFilter);
    }

    node.innerHTML = `<div class="stack-item">Đang tải hồ sơ ứng tuyển...</div>`;

    try {
        const query = params.toString();
        const data = await apiRequest(`/api/applications/me?${query}`);
        const applications = data.applications || [];
        renderCandidateApplications(applications);
    } catch (error) {
        node.innerHTML = `<div class="stack-item error">Không tải được hồ sơ: ${escapeHtml(error.message)}</div>`;
    }
}

async function loadCandidateTimeline(applicationId) {
    const timelineNode = document.getElementById("candidate-timeline-output");
    if (!timelineNode) {
        return;
    }

    timelineNode.innerHTML = `<div class="stack-item">Đang tải timeline cho application #${escapeHtml(applicationId)}...</div>`;
    try {
        const data = await apiRequest(`/api/applications/${applicationId}/timeline`);
        timelineNode.innerHTML = buildTimelineMarkup(data, { showNotes: false });
    } catch (error) {
        timelineNode.innerHTML = `<div class="stack-item error">Không tải được timeline: ${escapeHtml(error.message)}</div>`;
    }
}

async function withdrawCandidateApplication(applicationId) {
    const confirmed = window.confirm("Bạn chắc chắn muốn rút hồ sơ này?");
    if (!confirmed) {
        return;
    }

    const reasonInput = window.prompt("Lý do rút hồ sơ (tuỳ chọn):", "candidate_withdrawn");
    if (reasonInput === null) {
        return;
    }

    const reason = (reasonInput || "").trim();
    const payload = reason ? { reason } : {};

    try {
        await apiRequest(`/api/applications/${applicationId}/withdraw`, {
            method: "POST",
            body: payload,
        });
        showStatus("Đã rút hồ sơ thành công", "success");
        const timelineNode = document.getElementById("candidate-timeline-output");
        if (timelineNode) {
            timelineNode.innerHTML = `<div class="stack-item">Chọn một hồ sơ để xem chi tiết lịch sử trạng thái và lịch phỏng vấn.</div>`;
        }
        await loadApplications();
    } catch (error) {
        showStatus(error.message, "error");
    }
}

function renderCandidateProfileReadonly(user) {
    const emailNode = document.getElementById("profile-email");
    const roleNode = document.getElementById("profile-role");
    const updatedNode = document.getElementById("profile-updated-at");
    const socialNode = document.getElementById("profile-social-links");

    if (emailNode) {
        emailNode.textContent = user?.email || "N/A";
    }

    if (roleNode) {
        roleNode.textContent = normalizeRole(user?.role) === "candidate" ? "Ứng viên" : user?.role || "N/A";
    }

    if (updatedNode) {
        updatedNode.textContent = user?.profile_updated_at ? formatDateTime(user.profile_updated_at) : "Chưa cập nhật";
    }

    if (socialNode) {
        const links = [];
        if (user?.linkedin_id) {
            links.push("LinkedIn đã liên kết");
        }
        if (user?.google_id) {
            links.push("Google đã liên kết");
        }
        socialNode.textContent = links.length ? links.join(" • ") : "Chưa liên kết social";
    }
}

function populateCandidateProfileForm(user) {
    const fullNameInput = document.getElementById("profile-full-name");
    const phoneInput = document.getElementById("profile-phone");
    const addressInput = document.getElementById("profile-address");
    const dobInput = document.getElementById("profile-date-of-birth");
    const bioInput = document.getElementById("profile-bio");

    if (fullNameInput) {
        fullNameInput.value = user?.full_name || "";
    }
    if (phoneInput) {
        phoneInput.value = user?.phone || "";
    }
    if (addressInput) {
        addressInput.value = user?.address || "";
    }
    if (dobInput) {
        dobInput.value = user?.date_of_birth || "";
    }
    if (bioInput) {
        bioInput.value = user?.bio || "";
    }
}

async function loadCandidateProfile() {
    try {
        const data = await apiRequest("/api/auth/me");
        const user = data.user || {};
        setSession(getToken(), user);
        renderCandidateProfileReadonly(user);
        populateCandidateProfileForm(user);
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function saveCandidateProfile(event) {
    event.preventDefault();

    const fullName = (document.getElementById("profile-full-name")?.value || "").trim();
    const phone = (document.getElementById("profile-phone")?.value || "").trim();
    const address = (document.getElementById("profile-address")?.value || "").trim();
    const dateOfBirth = (document.getElementById("profile-date-of-birth")?.value || "").trim();
    const bio = (document.getElementById("profile-bio")?.value || "").trim();

    if (!fullName) {
        showStatus("Họ và tên không được để trống.", "error");
        return;
    }

    const payload = {
        full_name: fullName,
        phone,
        address,
        date_of_birth: dateOfBirth,
        bio,
    };

    try {
        const data = await apiRequest("/api/auth/me", {
            method: "PATCH",
            body: payload,
        });

        const updatedUser = data.user || {};
        setSession(getToken(), updatedUser);
        renderCandidateProfileReadonly(updatedUser);
        populateCandidateProfileForm(updatedUser);
        showStatus("Đã lưu hồ sơ thành công", "success");
    } catch (error) {
        showStatus(error.message, "error");
    }
}

function buildCandidateCvBuilderPayload() {
    const skillsRaw = (document.getElementById("cv-builder-skills")?.value || "").trim();
    const experience = (document.getElementById("cv-builder-experience")?.value || "").trim();
    const education = (document.getElementById("cv-builder-education")?.value || "").trim();
    const projects = (document.getElementById("cv-builder-projects")?.value || "").trim();

    const skills = skillsRaw
        ? skillsRaw
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean)
        : [];

    if (!skills.length && !experience && !education && !projects) {
        return null;
    }

    return {
        skills,
        experience,
        education,
        projects,
    };
}

function renderCandidateCvList(cvs) {
    const node = document.getElementById("candidate-cv-list");
    if (!node) {
        return;
    }

    if (!cvs || !cvs.length) {
        node.innerHTML = `<div class="stack-item">Chưa có CV nào. Hãy tạo hoặc tải CV để bắt đầu.</div>`;
        return;
    }

    node.innerHTML = cvs
        .map(
            (cv) => `
                <article class="stack-item" data-cv-id="${cv.id}">
                    <div class="app-card-header">
                        <strong>${escapeHtml(cv.title || `CV #${cv.id}`)}</strong>
                        ${cv.is_default ? `<span class="status-pill status-shortlisted">Mặc định</span>` : ""}
                    </div>
                    <p class="job-meta">Cập nhật: ${escapeHtml(formatDateTime(cv.updated_at || cv.created_at))}</p>
                    ${cv.file_path ? `<p><a href="${escapeHtml(API_BASE + (cv.download_url || ""))}" target="_blank" rel="noopener">Tải file CV</a></p>` : ""}
                    <div class="inline-actions">
                        <button type="button" class="ghost-btn" data-cv-action="set-default" data-cv-id="${cv.id}">Đặt mặc định</button>
                        <button type="button" class="ghost-btn" data-cv-action="delete" data-cv-id="${cv.id}">Xóa CV</button>
                    </div>
                </article>
            `
        )
        .join("");
}

async function loadCandidateCvs() {
    try {
        const data = await apiRequest("/api/candidate/cvs");
        renderCandidateCvList(data.cvs || []);
    } catch (error) {
        const node = document.getElementById("candidate-cv-list");
        if (node) {
            node.innerHTML = `<div class="stack-item error">Không tải được danh sách CV: ${escapeHtml(error.message)}</div>`;
        }
    }
}

async function submitCandidateCvForm(event) {
    event.preventDefault();

    const form = document.getElementById("candidate-cv-form");
    const fileInput = document.getElementById("cv-file");
    const title = (document.getElementById("cv-title")?.value || "").trim();
    const resumeText = (document.getElementById("cv-resume-text")?.value || "").trim();
    const isDefault = !!document.getElementById("cv-is-default")?.checked;
    const cvFile = fileInput?.files?.[0] || null;
    const builderPayload = buildCandidateCvBuilderPayload();

    if (!cvFile && !resumeText && !builderPayload) {
        showStatus("Vui lòng tải file CV hoặc nhập nội dung CV builder.", "error");
        return;
    }

    try {
        if (cvFile) {
            const formData = new FormData();
            if (title) {
                formData.append("title", title);
            }
            formData.append("cv_file", cvFile);
            if (resumeText) {
                formData.append("resume_text", resumeText);
            }
            if (builderPayload) {
                formData.append("builder_json", JSON.stringify(builderPayload));
            }
            if (isDefault) {
                formData.append("is_default", "true");
            }
            await apiMultipartRequest("/api/candidate/cvs", formData);
        } else {
            await apiRequest("/api/candidate/cvs", {
                method: "POST",
                body: {
                    title,
                    resume_text: resumeText,
                    builder_json: builderPayload,
                    is_default: isDefault,
                },
            });
        }

        if (form) {
            form.reset();
        }
        showStatus("Đã lưu CV thành công", "success");
        await loadCandidateCvs();
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function setCandidateCvDefault(cvId) {
    try {
        await apiRequest(`/api/candidate/cvs/${cvId}/default`, {
            method: "PATCH",
        });
        showStatus("Đã đặt CV mặc định", "success");
        await loadCandidateCvs();
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function deleteCandidateCv(cvId) {
    const confirmed = window.confirm("Bạn có chắc muốn xóa CV này?");
    if (!confirmed) {
        return;
    }

    try {
        await apiRequest(`/api/candidate/cvs/${cvId}`, {
            method: "DELETE",
        });
        showStatus("Đã xóa CV", "success");
        await loadCandidateCvs();
    } catch (error) {
        showStatus(error.message, "error");
    }
}

function renderCandidateSavedJobs(savedJobs) {
    const node = document.getElementById("candidate-saved-jobs");
    if (!node) {
        return;
    }

    if (!savedJobs || !savedJobs.length) {
        node.innerHTML = `<div class="stack-item">Bạn chưa lưu việc nào.</div>`;
        return;
    }

    node.innerHTML = savedJobs
        .map((item) => {
            const job = item.job || {};
            return `
                <article class="stack-item" data-job-id="${job.id || item.job_id}">
                    <strong>${escapeHtml(job.title || `Job #${item.job_id}`)}</strong>
                    <p class="job-meta">${escapeHtml(job.company_name || "N/A")} • ${escapeHtml(job.location || "N/A")}</p>
                    <div class="inline-actions">
                        <a class="ghost-btn" href="/jobs/${job.id || item.job_id}/apply">Ứng tuyển</a>
                        <button type="button" class="ghost-btn" data-saved-job-action="remove" data-job-id="${
                            item.job_id
                        }">Bỏ lưu</button>
                    </div>
                </article>
            `;
        })
        .join("");
}

async function loadCandidateSavedJobs() {
    try {
        const data = await apiRequest("/api/candidate/saved-jobs");
        renderCandidateSavedJobs(data.saved_jobs || []);
    } catch (error) {
        const node = document.getElementById("candidate-saved-jobs");
        if (node) {
            node.innerHTML = `<div class="stack-item error">Không tải được việc đã lưu: ${escapeHtml(error.message)}</div>`;
        }
    }
}

async function removeCandidateSavedJob(jobId) {
    try {
        await apiRequest(`/api/candidate/saved-jobs/${jobId}`, {
            method: "DELETE",
        });
        showStatus("Đã bỏ lưu job", "success");
        await loadCandidateSavedJobs();
    } catch (error) {
        showStatus(error.message, "error");
    }
}

function bindCandidateProfilePage() {
    const profileForm = document.getElementById("candidate-profile-form");
    if (profileForm) {
        profileForm.addEventListener("submit", saveCandidateProfile);
    }

    const cvForm = document.getElementById("candidate-cv-form");
    if (cvForm) {
        cvForm.addEventListener("submit", submitCandidateCvForm);
    }

    const cvList = document.getElementById("candidate-cv-list");
    if (cvList) {
        cvList.addEventListener("click", async (event) => {
            const actionButton = event.target.closest("[data-cv-action]");
            if (!actionButton) {
                return;
            }

            const action = actionButton.getAttribute("data-cv-action");
            const cvId = Number(actionButton.getAttribute("data-cv-id"));
            if (!cvId) {
                return;
            }

            if (action === "set-default") {
                await setCandidateCvDefault(cvId);
            }
            if (action === "delete") {
                await deleteCandidateCv(cvId);
            }
        });
    }

    const savedJobsNode = document.getElementById("candidate-saved-jobs");
    if (savedJobsNode) {
        savedJobsNode.addEventListener("click", async (event) => {
            const actionButton = event.target.closest("[data-saved-job-action]");
            if (!actionButton) {
                return;
            }

            const action = actionButton.getAttribute("data-saved-job-action");
            const jobId = Number(actionButton.getAttribute("data-job-id"));
            if (!jobId) {
                return;
            }

            if (action === "remove") {
                await removeCandidateSavedJob(jobId);
            }
        });
    }

    const loadSavedJobsButton = document.getElementById("load-saved-jobs-btn");
    if (loadSavedJobsButton) {
        loadSavedJobsButton.addEventListener("click", loadCandidateSavedJobs);
    }

    loadCandidateProfile();
    loadCandidateCvs();
    loadCandidateSavedJobs();
}

function bindCandidateApplicationsPage() {
    const loadButton = document.getElementById("load-applications-btn");
    if (loadButton) {
        loadButton.addEventListener("click", loadApplications);
    }

    const statusFilter = document.getElementById("candidate-status-filter");
    if (statusFilter) {
        statusFilter.addEventListener("change", loadApplications);
    }

    const applicationsContainer = document.getElementById("applications-container");
    if (applicationsContainer) {
        applicationsContainer.addEventListener("click", async (event) => {
            const actionButton = event.target.closest("[data-candidate-action]");
            if (!actionButton) {
                return;
            }

            const action = actionButton.getAttribute("data-candidate-action");
            const applicationId = Number(actionButton.getAttribute("data-application-id"));
            if (!applicationId) {
                return;
            }

            if (action === "timeline") {
                await loadCandidateTimeline(applicationId);
            }

            if (action === "withdraw") {
                await withdrawCandidateApplication(applicationId);
            }
        });
    }

    loadApplications();
}

function renderRecruiterApplications(applications) {
    const container = document.getElementById("recruiter-applications-container");
    if (!container) {
        return;
    }

    if (!applications.length) {
        container.innerHTML = `<div class="stack-item">Chưa có hồ sơ nào khớp điều kiện lọc.</div>`;
        return;
    }

    container.innerHTML = applications
        .map(
            (item) => `
                <article class="stack-item recruiter-app-card" data-application-id="${item.id}">
                    <div class="app-card-header">
                        <strong>Application #${escapeHtml(item.id)}</strong>
                        ${statusBadgeMarkup(item.status)}
                    </div>
                    <p class="job-meta">Job #${escapeHtml(item.job_id)} • ${escapeHtml(item.job_title || "N/A")}</p>
                    <p class="job-meta">Ứng viên: ${escapeHtml(item.candidate_name || `#${item.candidate_id}`)}</p>
                    <p class="job-meta">Email: ${escapeHtml(item.candidate_email || "N/A")}</p>
                    <p class="job-meta">CV: ${escapeHtml(item.cv_title || "N/A")}</p>
                    ${
                        item.cv_download_url
                            ? `<p><a href="${escapeHtml(API_BASE + item.cv_download_url)}" target="_blank" rel="noopener">Tải CV ứng viên</a></p>`
                            : ""
                    }
                    <p class="job-meta">Updated: ${escapeHtml(formatDateTime(item.updated_at))}</p>
                    ${
                        item.rejection_reason
                            ? `<p class="job-meta">Lý do reject: ${escapeHtml(item.rejection_reason)}</p>`
                            : ""
                    }

                    <div class="ats-controls">
                        <label>Trạng thái mới
                            <select data-field="status">
                                ${buildStatusOptionsMarkup(item.status)}
                            </select>
                        </label>
                        <label>Lý do (bắt buộc khi rejected)
                            <input type="text" data-field="reason" placeholder="Ví dụ: Không phù hợp kỹ năng">
                        </label>
                        <label>Ghi chú nhanh
                            <input type="text" data-field="note" placeholder="Nhập ghi chú và bấm cập nhật hoặc lưu note">
                        </label>
                    </div>

                    <div class="inline-actions">
                        <button type="button" class="primary-btn" data-recruiter-action="update-status" data-application-id="${item.id}">Cập nhật trạng thái</button>
                        <button type="button" class="ghost-btn" data-recruiter-action="load-timeline" data-application-id="${item.id}">Xem timeline</button>
                        <button type="button" class="ghost-btn" data-recruiter-action="load-notes" data-application-id="${item.id}">Xem notes</button>
                        <button type="button" class="ghost-btn" data-recruiter-action="add-note" data-application-id="${item.id}">Lưu note riêng</button>
                    </div>
                </article>
            `
        )
        .join("");
}

async function loadRecruiterApplications() {
    const container = document.getElementById("recruiter-applications-container");
    if (!container) {
        return;
    }

    const filterForm = document.getElementById("recruiter-app-filter-form");
    const formData = filterForm ? new FormData(filterForm) : new FormData();

    const params = new URLSearchParams();
    params.set("limit", "50");

    const jobId = (formData.get("job_id") || "").toString().trim();
    const status = (formData.get("status") || "").toString().trim();
    const sort = (formData.get("sort") || "").toString().trim();

    if (jobId) {
        params.set("job_id", jobId);
    }
    if (status) {
        params.set("status", status);
    }
    if (sort) {
        params.set("sort", sort);
    }

    container.innerHTML = `<div class="stack-item">Đang tải danh sách hồ sơ...</div>`;

    try {
        const data = await apiRequest(`/api/recruiter/applications?${params.toString()}`);
        const applications = data.applications || [];
        renderRecruiterApplications(applications);

        const pagination = data.pagination || {};
        const summaryNode = document.getElementById("recruiter-pagination-summary");
        if (summaryNode) {
            summaryNode.textContent = `Hiển thị ${applications.length} / ${pagination.total || 0} hồ sơ`;
        }

        if (jobId) {
            const pipelineInput = document.getElementById("pipeline-job-id");
            if (pipelineInput) {
                pipelineInput.value = jobId;
            }
            await loadRecruiterPipeline(jobId, false);
        }
    } catch (error) {
        container.innerHTML = `<div class="stack-item error">Không tải được hồ sơ: ${escapeHtml(error.message)}</div>`;
    }
}

async function loadRecruiterPipeline(jobId, showError = true) {
    const pipelineNode = document.getElementById("pipeline-counts");
    if (!pipelineNode) {
        return;
    }

    const normalizedJobId = Number(jobId);
    if (!Number.isInteger(normalizedJobId) || normalizedJobId <= 0) {
        pipelineNode.innerHTML = `<div class="stack-item error">Job ID không hợp lệ để tải pipeline.</div>`;
        return;
    }

    pipelineNode.innerHTML = `<div class="stack-item">Đang tải pipeline cho job #${normalizedJobId}...</div>`;

    try {
        const data = await apiRequest(`/api/recruiter/jobs/${normalizedJobId}/pipeline`);
        pipelineNode.innerHTML = buildStatusChipsMarkup(data.counts_by_status || {});
    } catch (error) {
        pipelineNode.innerHTML = `<div class="stack-item error">Không tải được pipeline: ${escapeHtml(error.message)}</div>`;
        if (showError) {
            showStatus(error.message, "error");
        }
    }
}

async function loadRecruiterTimeline(applicationId) {
    const timelineNode = document.getElementById("recruiter-activity-output");
    if (!timelineNode) {
        return;
    }

    timelineNode.innerHTML = `<div class="stack-item">Đang tải timeline cho application #${escapeHtml(applicationId)}...</div>`;

    try {
        const data = await apiRequest(`/api/applications/${applicationId}/timeline`);
        timelineNode.innerHTML = buildTimelineMarkup(data, { showNotes: true });

        const notesNode = document.getElementById("recruiter-notes-output");
        if (notesNode) {
            notesNode.innerHTML = `
                <article class="stack-item">
                    <strong>Notes - Application #${escapeHtml(applicationId)}</strong>
                </article>
                ${buildNotesMarkup(data.notes || [])}
            `;
        }
    } catch (error) {
        timelineNode.innerHTML = `<div class="stack-item error">Không tải được timeline: ${escapeHtml(error.message)}</div>`;
    }
}

async function loadRecruiterNotes(applicationId) {
    const notesNode = document.getElementById("recruiter-notes-output");
    if (!notesNode) {
        return;
    }

    notesNode.innerHTML = `<div class="stack-item">Đang tải notes cho application #${escapeHtml(applicationId)}...</div>`;

    try {
        const data = await apiRequest(`/api/applications/${applicationId}/notes`);
        notesNode.innerHTML = `
            <article class="stack-item">
                <strong>Notes - Application #${escapeHtml(applicationId)}</strong>
            </article>
            ${buildNotesMarkup(data.notes || [])}
        `;
    } catch (error) {
        notesNode.innerHTML = `<div class="stack-item error">Không tải được notes: ${escapeHtml(error.message)}</div>`;
    }
}

async function updateRecruiterApplicationStatus(applicationId, cardNode) {
    const statusSelect = cardNode?.querySelector('[data-field="status"]');
    const reasonInput = cardNode?.querySelector('[data-field="reason"]');
    const noteInput = cardNode?.querySelector('[data-field="note"]');

    const status = (statusSelect?.value || "").toString().trim().toLowerCase();
    const reason = (reasonInput?.value || "").toString().trim();
    const note = (noteInput?.value || "").toString().trim();

    if (!status) {
        showStatus("Vui lòng chọn trạng thái mới.", "error");
        return;
    }

    const payload = { status };
    if (reason) {
        payload.reason = reason;
    }
    if (note) {
        payload.note = note;
    }

    try {
        await apiRequest(`/api/applications/${applicationId}/status`, {
            method: "PATCH",
            body: payload,
        });

        if (noteInput) {
            noteInput.value = "";
        }
        if (reasonInput && status !== "rejected") {
            reasonInput.value = "";
        }

        showStatus("Cập nhật trạng thái thành công", "success");
        await loadRecruiterApplications();
        await loadRecruiterTimeline(applicationId);
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function addRecruiterNote(applicationId, cardNode) {
    const noteInput = cardNode?.querySelector('[data-field="note"]');
    const content = (noteInput?.value || "").toString().trim();
    if (!content) {
        showStatus("Vui lòng nhập nội dung note trước khi lưu.", "error");
        return;
    }

    try {
        await apiRequest(`/api/applications/${applicationId}/notes`, {
            method: "POST",
            body: { content },
        });

        if (noteInput) {
            noteInput.value = "";
        }

        showStatus("Đã lưu note", "success");
        await loadRecruiterNotes(applicationId);
    } catch (error) {
        showStatus(error.message, "error");
    }
}

async function loadRecruiterDashboardSummary() {
    const node = document.getElementById("recruiter-dashboard-summary");
    if (!node) {
        return;
    }

    try {
        const data = await apiRequest("/api/recruiter/dashboard");
        node.innerHTML = `
            <article class="stack-item">
                <strong>Jobs đang quản lý: ${escapeHtml(data.jobs_total ?? 0)}</strong>
                <p class="job-meta">Jobs active: ${escapeHtml(data.jobs_active ?? 0)}</p>
                <p class="job-meta">Tổng hồ sơ: ${escapeHtml(data.applications_total ?? 0)}</p>
            </article>
            ${buildStatusChipsMarkup(data.counts_by_status || {})}
        `;
    } catch (error) {
        node.innerHTML = `<div class="stack-item error">Không tải được dashboard: ${escapeHtml(error.message)}</div>`;
    }
}

async function loadRecruiterCompanyProfile() {
    const form = document.getElementById("create-company-form");
    if (!form) {
        return;
    }

    try {
        const data = await apiRequest("/api/recruiter/company");
        const company = data.company;
        if (!company) {
            return;
        }

        form.querySelector('input[name="name"]').value = company.name || "";
        form.querySelector('textarea[name="description"]').value = company.description || "";
        form.querySelector('input[name="website"]').value = company.website || "";
    } catch (error) {
        showStatus(error.message, "error");
    }
}

function bindRecruiterPage() {
    const companyForm = document.getElementById("create-company-form");
    if (companyForm) {
        companyForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(companyForm);

            try {
                const data = await apiRequest("/api/recruiter/company", {
                    method: "PUT",
                    body: {
                        name: formData.get("name"),
                        description: formData.get("description"),
                        website: formData.get("website"),
                    },
                });
                showStatus(`Lưu công ty thành công. Company ID: ${data.company.id}`, "success");
            } catch (error) {
                showStatus(error.message, "error");
            }
        });
    }

    const jobForm = document.getElementById("create-job-form");
    if (jobForm) {
        jobForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(jobForm);

            const companyIdRaw = (formData.get("company_id") || "").toString().trim();

            const payload = {
                title: formData.get("title"),
                description: formData.get("description"),
                requirements: formData.get("requirements"),
                location: formData.get("location"),
                job_type: formData.get("job_type"),
                experience_level: formData.get("experience_level"),
                salary_min: formData.get("salary_min") ? Number(formData.get("salary_min")) : null,
                salary_max: formData.get("salary_max") ? Number(formData.get("salary_max")) : null,
            };

            if (companyIdRaw) {
                payload.company_id = Number(companyIdRaw);
            }

            try {
                const data = await apiRequest("/api/jobs", {
                    method: "POST",
                    body: payload,
                });
                showStatus(`Đăng job thành công. Job ID: ${data.job.id}`, "success");
            } catch (error) {
                showStatus(error.message, "error");
            }
        });
    }

    const aiForm = document.getElementById("ai-candidates-form");
    if (aiForm) {
        aiForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(aiForm);
            const output = document.getElementById("ai-candidates-output");

            let candidates = [];
            try {
                candidates = JSON.parse(formData.get("candidates_json").toString());
            } catch {
                showStatus("Candidates JSON không hợp lệ", "error");
                return;
            }

            try {
                const data = await apiRequest(`/api/jobs/${formData.get("job_id")}/ai/potential-candidates`, {
                    method: "POST",
                    body: {
                        candidates,
                    },
                });

                const ranked = data.candidates || [];
                output.innerHTML = ranked
                    .map(
                        (item) => `
                        <article class="stack-item">
                            <strong>${item.candidate?.name || item.candidate?.id || "Candidate"}</strong>
                            <p>Score: ${item.score}</p>
                            <p>${item.summary || "Không có mô tả"}</p>
                        </article>
                    `
                    )
                    .join("");

                if (!ranked.length) {
                    output.innerHTML = `<div class="stack-item">Không có ứng viên tiềm năng.</div>`;
                }

                showStatus("Phân tích ứng viên hoàn tất", "success");
            } catch (error) {
                showStatus(error.message, "error");
            }
        });
    }

    const interviewForm = document.getElementById("schedule-interview-form");
    if (interviewForm) {
        interviewForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const formData = new FormData(interviewForm);

            const payload = {
                application_id: Number(formData.get("application_id")),
                start_time: formData.get("start_time"),
                end_time: formData.get("end_time"),
                meeting_link: formData.get("meeting_link"),
            };

            try {
                const data = await apiRequest("/api/interviews/schedule", {
                    method: "POST",
                    body: payload,
                });
                showStatus(`Tạo lịch phỏng vấn thành công. Interview ID: ${data.interview.id}`, "success");
            } catch (error) {
                showStatus(error.message, "error");
            }
        });
    }

    const filterForm = document.getElementById("recruiter-app-filter-form");
    if (filterForm) {
        filterForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            await loadRecruiterApplications();
        });
    }

    const reloadApplicationsButton = document.getElementById("load-recruiter-applications-btn");
    if (reloadApplicationsButton) {
        reloadApplicationsButton.addEventListener("click", loadRecruiterApplications);
    }

    const loadPipelineButton = document.getElementById("load-pipeline-btn");
    if (loadPipelineButton) {
        loadPipelineButton.addEventListener("click", async () => {
            const jobId = (document.getElementById("pipeline-job-id")?.value || "").trim();
            if (!jobId) {
                showStatus("Vui lòng nhập Job ID để xem pipeline.", "error");
                return;
            }
            await loadRecruiterPipeline(jobId);
        });
    }

    const recruiterApplicationsContainer = document.getElementById("recruiter-applications-container");
    if (recruiterApplicationsContainer) {
        recruiterApplicationsContainer.addEventListener("click", async (event) => {
            const actionButton = event.target.closest("[data-recruiter-action]");
            if (!actionButton) {
                return;
            }

            const action = actionButton.getAttribute("data-recruiter-action");
            const applicationId = Number(actionButton.getAttribute("data-application-id"));
            if (!applicationId) {
                return;
            }

            const cardNode = actionButton.closest("[data-application-id]");

            if (action === "update-status") {
                await updateRecruiterApplicationStatus(applicationId, cardNode);
            }

            if (action === "load-timeline") {
                await loadRecruiterTimeline(applicationId);
            }

            if (action === "load-notes") {
                await loadRecruiterNotes(applicationId);
            }

            if (action === "add-note") {
                await addRecruiterNote(applicationId, cardNode);
            }
        });
    }

    loadRecruiterCompanyProfile();
    loadRecruiterDashboardSummary();
    loadRecruiterApplications();
}

function bindGlobalActions() {
    const logoutButton = document.getElementById("logout-btn");
    if (logoutButton) {
        logoutButton.addEventListener("click", () => {
            clearSession();
            window.location.href = "/login";
        });
    }
}

function bootstrap() {
    bindGlobalActions();
    syncTopNavigation();

    if (!guardPageAccess()) {
        return;
    }

    if (PAGE === "home") {
        bindHomePage();
    }
    if (PAGE === "login") {
        bindLoginPage();
    }
    if (PAGE === "register") {
        bindRegisterPage();
    }
    if (PAGE === "candidate") {
        bindCandidateProfilePage();
    }
    if (PAGE === "candidate-applications") {
        bindCandidateApplicationsPage();
    }
    if (PAGE === "recruiter") {
        bindRecruiterPage();
    }
    if (PAGE === "linkedin-callback") {
        bindLinkedinCallbackPage();
    }
    if (PAGE === "google-callback") {
        bindGoogleCallbackPage();
    }
    if (PAGE === "job-apply") {
        bindJobApplyPage();
    }
}

document.addEventListener("DOMContentLoaded", bootstrap);
