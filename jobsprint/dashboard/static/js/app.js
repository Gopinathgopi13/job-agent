const $ = (sel) => document.querySelector(sel);

// ── tabs ──────────────────────────────────────────────────────
function switchTab(tabName) {
    document.querySelectorAll(".tab-link").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabName));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tabName}`));
    if (tabName === "profile") loadProfile();
    if (tabName === "preferences") loadPreferences();
    if (tabName === "kb") loadKbEntries();
    if (tabName === "applications") loadApplications();
}

document.querySelectorAll(".tab-link").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s ?? "";
    return div.innerHTML;
}

// ── stats ─────────────────────────────────────────────────────
function renderStats(stats) {
    $("#stat-scanned").textContent = stats.jobs_scanned ?? 0;
    $("#stat-matched").textContent = stats.jobs_matched ?? 0;
    $("#stat-submitted").textContent = stats.applications_submitted ?? 0;
    $("#stat-needs-input").textContent = stats.applications_needing_input ?? 0;
    $("#stat-external").textContent = stats.external_applications_collected ?? 0;
    $("#stat-learned").textContent = stats.questions_learned_total ?? 0;
    $("#activity-line").textContent = stats.current_activity || "Idle";
    $("#progress-fill").style.width = `${stats.progress_percent ?? 0}%`;

    const badge = $("#status-badge");
    const status = stats.session_status || "idle";
    badge.dataset.status = status;
    $("#status-label").textContent = status.charAt(0).toUpperCase() + status.slice(1);

    $("#start-btn").disabled = status === "running";
    $("#stop-btn").disabled = status !== "running";
}

async function refreshStats() {
    try {
        const res = await fetch("/api/stats");
        renderStats(await res.json());
    } catch (e) {
        console.error("Failed to fetch stats", e);
    }
}

// ── live log ──────────────────────────────────────────────────
const LOG_MAX_LINES = 300;
function appendLog(text) {
    const log = $("#log");
    const empty = log.querySelector(".line.empty");
    if (empty) empty.remove();
    const line = document.createElement("div");
    line.className = "line";
    const ts = new Date().toLocaleTimeString();
    line.textContent = `[${ts}] ${text}`;
    log.appendChild(line);
    while (log.children.length > LOG_MAX_LINES) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
}

// ── websocket ─────────────────────────────────────────────────
let wsWasConnectedBefore = false;

function connectWebSocket() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
        appendLog(wsWasConnectedBefore ? "Reconnected — resyncing…" : "Connected to JobSprint backend.");
        wsWasConnectedBefore = true;
        // The WebSocket only pushes deltas going forward — on a fresh
        // connect (or a reconnect after a drop) we might have missed
        // events, so always resync authoritative state from REST.
        refreshStats();
        syncPendingQuestions();
    };
    ws.onclose = () => {
        appendLog("Connection lost — retrying in 3s…");
        setTimeout(connectWebSocket, 3000);
    };
    ws.onerror = () => ws.close();

    ws.onmessage = (msg) => {
        const event = JSON.parse(msg.data);
        handleEvent(event);
    };
}

function handleEvent(event) {
    switch (event.type) {
        case "stats_update":
            renderStats(event.data);
            break;
        case "activity_update":
            $("#activity-line").textContent = event.data.text || "";
            break;
        case "log_line":
            appendLog(event.data.text || "");
            break;
        case "question_pending":
            enqueueQuestion(event.data);
            break;
        case "question_resolved":
            dismissQuestion(event.data.id);
            break;
        case "application_added":
            refreshStats();
            if ($("#tab-applications").classList.contains("active")) loadApplications();
            break;
        case "question_learned":
            if ($("#tab-kb").classList.contains("active")) loadKbEntries();
            break;
        case "session_status_changed":
            refreshStats();
            break;
        default:
            break;
    }
}

// ── start-session modal ──────────────────────────────────────
const startOverlay = $("#start-modal-overlay");
$("#start-btn").addEventListener("click", () => {
    $("#start-error").textContent = "";
    startOverlay.classList.add("visible");
});
$("#start-cancel-btn").addEventListener("click", () => startOverlay.classList.remove("visible"));

$("#start-confirm-btn").addEventListener("click", async () => {
    const email = $("#start-email").value.trim();
    const password = $("#start-password").value;
    const jobsTarget = parseInt($("#start-jobs-target").value, 10) || 10;
    if (!email || !password) {
        $("#start-error").textContent = "Email and password are required.";
        return;
    }
    try {
        const res = await fetch("/api/session/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password, jobs_target: jobsTarget }),
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || "Failed to start session.");
        $("#start-password").value = "";
        startOverlay.classList.remove("visible");
        refreshStats();
    } catch (e) {
        $("#start-error").textContent = e.message;
    }
});

$("#stop-btn").addEventListener("click", async () => {
    try {
        await fetch("/api/session/stop", { method: "POST" });
    } catch (e) {
        appendLog(`Failed to stop: ${e.message}`);
    }
});

// ── "New Question Detected" modal ────────────────────────────
const questionOverlay = $("#question-modal-overlay");
let questionQueue = [];
let activeQuestion = null;

function enqueueQuestion(q) {
    questionQueue.push(q);
    if (!activeQuestion) showNextQuestion();
}

function showNextQuestion() {
    if (questionQueue.length === 0) {
        activeQuestion = null;
        questionOverlay.classList.remove("visible");
        return;
    }
    activeQuestion = questionQueue.shift();
    $("#question-text").textContent = activeQuestion.question;
    const job = activeQuestion.job || {};
    $("#question-job-ctx").textContent = job.title || job.url
        ? `${job.title || "Job"}${job.company ? " at " + job.company : ""}${job.url ? " — " + job.url : ""}`
        : "";
    $("#question-answer-input").value = activeQuestion.suggested_answer || "";

    const candidatesEl = $("#question-candidates");
    candidatesEl.innerHTML = "";
    (activeQuestion.candidates || []).forEach((c) => {
        const btn = document.createElement("button");
        btn.textContent = `${c.answer} (${Math.round(c.score)}% — ${c.canonical_question})`;
        btn.addEventListener("click", () => { $("#question-answer-input").value = c.answer; });
        candidatesEl.appendChild(btn);
    });

    questionOverlay.classList.add("visible");
}

function dismissQuestion(id) {
    // If the resolved question wasn't the one currently showing (e.g. it
    // timed out while queued), just drop it from the queue.
    questionQueue = questionQueue.filter((q) => q.id !== id);
    if (activeQuestion && activeQuestion.id === id) {
        showNextQuestion();
    }
}

$("#question-submit-btn").addEventListener("click", async () => {
    if (!activeQuestion) return;
    const answer = $("#question-answer-input").value.trim();
    if (!answer) return;
    await fetch(`/api/questions/${activeQuestion.id}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
    });
    showNextQuestion();
});

$("#question-skip-btn").addEventListener("click", async () => {
    if (!activeQuestion) return;
    await fetch(`/api/questions/${activeQuestion.id}/skip`, { method: "POST" });
    showNextQuestion();
});

// On load/reconnect, pick up any question that was already pending.
async function syncPendingQuestions() {
    try {
        const res = await fetch("/api/questions/pending");
        const pending = await res.json();
        pending.forEach(enqueueQuestion);
    } catch (e) {
        console.error("Failed to sync pending questions", e);
    }
}

// ── preferences ──────────────────────────────────────────────
async function loadPreferences() {
    try {
        const res = await fetch("/api/preferences");
        const prefs = await res.json();
        $("#pref-role").value = prefs.role || "";
        $("#pref-location").value = prefs.location || "";
        $("#pref-experience").value = prefs.experience ?? "";
        $("#pref-job-age").value = prefs.job_age_days ?? "";
        $("#pref-jobs-target").value = prefs.jobs_target ?? "";
        $("#pref-timeout").value = prefs.question_timeout_minutes ?? "";
        $("#pref-auto-external").checked = !!prefs.auto_apply_external;
    } catch (e) {
        console.error("Failed to load preferences", e);
    }
}

$("#pref-save-btn").addEventListener("click", async () => {
    const body = {
        role: $("#pref-role").value.trim(),
        location: $("#pref-location").value.trim(),
        experience: Number.isNaN(parseInt($("#pref-experience").value, 10))
            ? null
            : parseInt($("#pref-experience").value, 10),
        job_age_days: parseInt($("#pref-job-age").value, 10) || null,
        jobs_target: parseInt($("#pref-jobs-target").value, 10) || null,
        question_timeout_minutes: parseInt($("#pref-timeout").value, 10) || null,
        auto_apply_external: $("#pref-auto-external").checked,
    };
    try {
        const res = await fetch("/api/preferences", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error((await res.json()).detail || "Save failed.");
        $("#pref-save-status").textContent = "Saved.";
        setTimeout(() => { $("#pref-save-status").textContent = ""; }, 2500);
    } catch (e) {
        $("#pref-save-status").style.color = "var(--red)";
        $("#pref-save-status").textContent = e.message;
    }
});

// ── profile ──────────────────────────────────────────────────
function skillsToText(skills) {
    return Object.entries(skills || {}).map(([k, v]) => `${k}: ${v}`).join("\n");
}

function skillsFromText(text) {
    const skills = {};
    text.split("\n").forEach((line) => {
        const [name, years] = line.split(":");
        if (name && name.trim()) skills[name.trim()] = (years || "").trim();
    });
    return skills;
}

async function loadProfile() {
    try {
        const res = await fetch("/api/profile");
        const body = await res.json();
        const p = body.profile;
        $("#profile-salutation").value = p["Salutation"] || "";
        $("#profile-full-name").value = p["Full name"] || "";
        $("#profile-first-name").value = p["First name"] || "";
        $("#profile-last-name").value = p["Last name"] || "";
        $("#profile-location").value = p["Location"] || "";
        $("#profile-preferred-location").value = p["Preferred work location"] || "";
        $("#profile-total-experience").value = p["Total experience"] || "";
        $("#profile-current-ctc").value = p["Current CTC"] || p["Salary"] || "";
        $("#profile-expected-salary").value = p["Expected salary"] || "";
        $("#profile-notice-period").value = p["Notice period"] || "";
        $("#profile-mobile").value = p["Mobile"] || "";
        $("#profile-email").value = p["Email"] || "";
        $("#profile-dob").value = p["Date of birth"] || "";
        $("#profile-gender").value = p["Gender"] || "";
        $("#profile-relocate").value = p["Relocate"] || "";
        $("#profile-qualification").value = p["Highest qualification"] || "";
        $("#profile-resume-path").value = p["Resume path"] || "";
        $("#profile-skills").value = skillsToText(p["Skills"]);
        $("#profile-cover-letter").value = p["Cover letter"] || "";

        $("#profile-first-run-banner").style.display = body.is_first_run ? "block" : "none";
        return body.is_first_run;
    } catch (e) {
        console.error("Failed to load profile", e);
        return false;
    }
}

async function saveProfile() {
    const body = {
        "Salutation": $("#profile-salutation").value.trim(),
        "Full name": $("#profile-full-name").value.trim(),
        "First name": $("#profile-first-name").value.trim(),
        "Last name": $("#profile-last-name").value.trim(),
        "Location": $("#profile-location").value.trim(),
        "Preferred work location": $("#profile-preferred-location").value.trim(),
        "Total experience": $("#profile-total-experience").value.trim(),
        "Current CTC": $("#profile-current-ctc").value.trim(),
        "Salary": $("#profile-current-ctc").value.trim(),
        "Expected salary": $("#profile-expected-salary").value.trim(),
        "Notice period": $("#profile-notice-period").value.trim(),
        "Mobile": $("#profile-mobile").value.trim(),
        "Email": $("#profile-email").value.trim(),
        "Date of birth": $("#profile-dob").value.trim(),
        "Gender": $("#profile-gender").value.trim(),
        "Relocate": $("#profile-relocate").value.trim(),
        "Highest qualification": $("#profile-qualification").value.trim(),
        "Cover letter": $("#profile-cover-letter").value,
        "Skills": skillsFromText($("#profile-skills").value),
    };
    const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Save failed.");
    return res.json();
}

$("#profile-save-btn").addEventListener("click", async () => {
    try {
        await saveProfile();
        $("#profile-first-run-banner").style.display = "none";
        $("#profile-save-status").textContent = "Saved.";
        setTimeout(() => { $("#profile-save-status").textContent = ""; }, 2500);
    } catch (e) {
        $("#profile-save-status").style.color = "var(--red)";
        $("#profile-save-status").textContent = e.message;
    }
});

// ── resume upload ────────────────────────────────────────────
$("#resume-upload-btn").addEventListener("click", async () => {
    const input = $("#resume-file-input");
    const file = input.files[0];
    if (!file) {
        $("#resume-status").textContent = "Choose a PDF file first.";
        return;
    }
    $("#resume-status").textContent = "Analyzing…";
    $("#resume-skills").innerHTML = "";
    const formData = new FormData();
    formData.append("file", file);
    try {
        const res = await fetch("/api/resume/upload", { method: "POST", body: formData });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || "Upload failed.");
        $("#resume-status").textContent = `Extracted ${body.skills.length} skills from ${body.characters_extracted} characters.`;
        $("#resume-skills").innerHTML = "";
        body.skills.forEach((s) => {
            const chip = document.createElement("span");
            chip.className = "skill-chip";
            chip.textContent = s;
            $("#resume-skills").appendChild(chip);
        });
        // Persist the resume path onto the profile so it's what actually
        // gets attached when the bot fills out Naukri's application forms.
        $("#profile-resume-path").value = body.path;
        await fetch("/api/profile", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ "Resume path": body.path }),
        });
    } catch (e) {
        $("#resume-status").textContent = e.message;
    }
});

// ── knowledge base ───────────────────────────────────────────
const SOURCE_LABELS = { static_profile: "From profile", computed: "Computed", user_taught: "Learned from you" };

async function loadKbEntries() {
    const query = $("#kb-search-input").value.trim();
    const source = $("#kb-source-filter").value;
    const params = new URLSearchParams();
    if (query) params.set("query", query);
    if (source) params.set("source", source);
    try {
        const res = await fetch(`/api/kb?${params.toString()}`);
        const entries = await res.json();
        renderKbTable(entries);
    } catch (e) {
        console.error("Failed to load KB entries", e);
    }
}

function renderKbTable(entries) {
    const tbody = $("#kb-tbody");
    if (!entries.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="placeholder">No matching knowledge base entries.</td></tr>';
        return;
    }
    tbody.innerHTML = entries.map((e) => {
        const editable = e.source !== "static_profile";
        const answerCell = editable
            ? `<input type="text" value="${escapeHtml(e.answer || "")}" data-kb-answer="${e.id}">`
            : `${escapeHtml(e.answer || "")} <span class="hint">(edit in Profile)</span>`;
        return `<tr>
            <td>${escapeHtml(e.canonical_question)}</td>
            <td>${answerCell}</td>
            <td><span class="pill">${SOURCE_LABELS[e.source] || e.source}</span></td>
            <td>${e.usage_count ?? 0}</td>
            <td>
                ${editable ? `<button class="icon-btn" data-kb-save="${e.id}">Save</button>` : ""}
                <button class="icon-btn danger" data-kb-delete="${e.id}">Delete</button>
            </td>
        </tr>`;
    }).join("");

    tbody.querySelectorAll("[data-kb-save]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = btn.dataset.kbSave;
            const answer = tbody.querySelector(`[data-kb-answer="${id}"]`).value;
            await fetch(`/api/kb/${id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ answer }),
            });
            loadKbEntries();
        });
    });
    tbody.querySelectorAll("[data-kb-delete]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            await fetch(`/api/kb/${btn.dataset.kbDelete}`, { method: "DELETE" });
            loadKbEntries();
        });
    });
}

$("#kb-search-input").addEventListener("input", debounce(loadKbEntries, 300));
$("#kb-source-filter").addEventListener("change", loadKbEntries);

function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ── application history ──────────────────────────────────────
async function loadApplications() {
    const status = $("#app-status-filter").value;
    const params = new URLSearchParams({ limit: "100" });
    if (status) params.set("status", status);
    try {
        const res = await fetch(`/api/applications?${params.toString()}`);
        const rows = await res.json();
        renderApplicationsTable(rows);
    } catch (e) {
        console.error("Failed to load applications", e);
    }
}

function renderApplicationsTable(rows) {
    const tbody = $("#applications-tbody");
    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="placeholder">No applications yet.</td></tr>';
        return;
    }
    tbody.innerHTML = rows.map((r) => {
        const link = r.external_url || r.naukri_url || "";
        return `<tr>
            <td>${escapeHtml(r.datetime)}</td>
            <td>${escapeHtml(r.company)}</td>
            <td>${escapeHtml(r.job_role)}</td>
            <td>${escapeHtml(r.experience)}</td>
            <td>${escapeHtml(r.salary)}</td>
            <td><span class="pill ${r.application_type}">${escapeHtml(r.application_type)}</span></td>
            <td>${escapeHtml(r.status)}</td>
            <td>${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener">Open</a>` : ""}</td>
        </tr>`;
    }).join("");
}

$("#app-refresh-btn").addEventListener("click", loadApplications);
$("#app-status-filter").addEventListener("change", loadApplications);

refreshStats();
syncPendingQuestions();
connectWebSocket();
setInterval(refreshStats, 5000);

// First launch, no profile saved yet — open straight to the Profile tab
// instead of a dashboard with nothing to show and no way to apply yet.
loadProfile().then((isFirstRun) => { if (isFirstRun) switchTab("profile"); });
