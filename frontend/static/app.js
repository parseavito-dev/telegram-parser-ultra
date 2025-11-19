let currentSession = null;
let currentTaskId = null;
let ws = null;

function log(message, type = "info") {
    const logs = document.getElementById("logs");
    const line = document.createElement("div");
    line.className = `log-line animate__animated animate__fadeIn`;
    line.innerHTML = `<span class="text-gray-500">[${new Date().toLocaleTimeString()}]</span> <span class="${type === 'error' ? 'text-red-400' : type === 'success' ? 'text-green-400' : 'text-purple-300'}">${message}</span>`;
    logs.appendChild(line);
    logs.scrollTop = logs.scrollHeight;
}

async function login() {
    const phone = document.getElementById("phone").value.trim();
    const api_id = document.getElementById("api_id").value.trim();
    const api_hash = document.getElementById("api_hash").value.trim();
    const code = document.getElementById("code").value.trim();
    const password = document.getElementById("password").value.trim();

    if (!phone || !api_id || !api_hash) return log("Заполните все поля!", "error");

    const formData = new FormData();
    formData.append("phone", phone);
    formData.append("api_id", api_id);
    formData.append("api_hash", api_hash);
    if (code) formData.append("code", code);
    if (password) formData.append("password", password);

    const res = await fetch("/api/login", { method: "POST", body: formData });
    const data = await res.json();

    if (data.status === "code_sent") {
        log("Код отправлен на " + phone);
        document.getElementById("code").classList.remove("hidden");
        document.getElementById("password").classList.remove("hidden");
    } else if (data.status === "success") {
        log("Успешный вход! Сессия сохранена: " + data.session, "success");
        currentSession = data.session;
        loadSessions();
    } else {
        log("Ошибка: " + data.message, "error");
    }
}

async function loadSessions() {
    const res = await fetch("/api/sessions");
    const data = await res.json();
    const select = document.getElementById("sessionSelect");
    select.innerHTML = "";
    data.sessions.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s;
        select.appendChild(opt);
    });
    if (data.sessions.length > 0) {
        document.getElementById("sessionList").classList.remove("hidden");
    }
}

function selectSession() {
    currentSession = document.getElementById("sessionSelect").value;
    log("Выбрана сессия: " + currentSession, "success");
}

async function startParse() {
    if (!currentSession) return log("Сначала войдите в аккаунт!", "error");

    const target = document.getElementById("target").value.trim();
    if (!target) return log("Укажите чат!", "error");

    const formData = new FormData();
    formData.append("session", currentSession);
    formData.append("target", target);
    formData.append("limit", document.getElementById("limit").value);
    formData.append("online_only", document.getElementById("online_only").checked);
    formData.append("recent_days", document.getElementById("recent_days").value);
    formData.append("letter", document.getElementById("letter").value);

    const res = await fetch("/api/parse", { method: "POST", body: formData });
    const data = await res.json();
    currentTaskId = data.task_id;

    log("Задача запущена! ID: " + currentTaskId, "success");
    document.getElementById("downloadButtons").classList.add("hidden");
    connectWebSocket(currentTaskId);
}

function connectWebSocket(taskId) {
    if (ws) ws.close();
    ws = new WebSocket(`ws://${location.host}/ws/${taskId}`);

    ws.onmessage = function(e) {
        const msg = JSON.parse(e.data);
        if (msg.type === "log") log(msg.message);
        if (msg.type === "progress") {
            document.getElementById("progressText").textContent = msg.status || "Парсинг...";
            document.getElementById("countText").textContent = (msg.parsed || 0) + " пользователей";
        }
        if (msg.type === "finished") {
            log(msg.message, "success");
            document.getElementById("csvLink").href = `/api/download/${taskId}?format=csv`;
            document.getElementById("xlsxLink").href = `/api/download/${taskId}?format=xlsx`;
            document.getElementById("downloadButtons").classList.remove("hidden");
            ws.close();
        }
        if (msg.type === "error") log(msg.message, "error");
    };

    ws.onclose = () => log("WebSocket закрыт");
}

// Загрузка сессий при старте
window.onload = loadSessions;