const WS_URL = "ws://127.0.0.1:8800";
const STATUS_URL = "http://127.0.0.1:8801/status";

const transcriptEl = document.getElementById("transcript");
const systemStatusEl = document.getElementById("system-status");
const alertsEl = document.getElementById("alerts");
const windowInfoEl = document.getElementById("window-info");
const browserInfoEl = document.getElementById("browser-info");
const weatherEl = document.getElementById("weather");
const connectionEl = document.getElementById("connection");
const assistantStateEl = document.getElementById("assistant-state");
const orbEl = document.getElementById("orb");
const manualForm = document.getElementById("manual-form");
const manualInput = document.getElementById("manual-input");
const manualResult = document.getElementById("manual-result");
const quickActions = document.querySelectorAll(".quick-actions button");
const onboardingModal = document.getElementById("onboarding");
const onboardingForm = document.getElementById("onboarding-form");
const onboardingRemote = document.getElementById("onboarding-remote");
const onboardingGroq = document.getElementById("onboarding-groq");
const onboardingWeather = document.getElementById("onboarding-weather");
const onboardingSkip = document.getElementById("onboarding-skip");
const personaSelect = document.getElementById("persona-select");
const personaTone = document.getElementById("persona-tone");
const personaPause = document.getElementById("persona-pause");

let socket;
let weatherCache;
let statusIntervalId = null;
const config = {
  remoteApiKey: "",
  groqApiKey: "",
  weatherApiKey: "",
  persona: "classic",
};

function loadConfig() {
  config.remoteApiKey = localStorage.getItem("REMOTE_API_KEY") || "";
  config.groqApiKey = localStorage.getItem("GROQ_API_KEY") || "";
  config.weatherApiKey = localStorage.getItem("WEATHER_API_KEY") || "";
  config.persona = localStorage.getItem("PERSONA_CHOICE") || "classic";
  if (personaSelect) {
    personaSelect.value = config.persona;
  }
  if (!config.remoteApiKey) {
    onboardingModal.classList.remove("hidden");
    onboardingRemote.focus();
  }
}

function saveConfig(updates) {
  Object.assign(config, updates);
  if (updates.remoteApiKey !== undefined) {
    localStorage.setItem("REMOTE_API_KEY", updates.remoteApiKey);
  }
  if (updates.groqApiKey !== undefined) {
    localStorage.setItem("GROQ_API_KEY", updates.groqApiKey);
  }
  if (updates.weatherApiKey !== undefined) {
    localStorage.setItem("WEATHER_API_KEY", updates.weatherApiKey);
  }
  if (updates.persona !== undefined) {
    localStorage.setItem("PERSONA_CHOICE", updates.persona);
  }
}

function appendEntry(role, text) {
  const li = document.createElement("li");
  li.className = "entry";
  li.innerHTML = `
    <span class="label">${role}</span>
    <div>${text}</div>
  `;
  transcriptEl.prepend(li);
  while (transcriptEl.children.length > 10) {
    transcriptEl.removeChild(transcriptEl.lastChild);
  }
}

function updateWindow(payload) {
  const title = payload.title || (payload.window && payload.window.title);
  const className = payload.class_name || (payload.window && payload.window.class_name);
  windowInfoEl.textContent = title ? `Window: ${title} (${className || "Unknown"})` : "Window info unavailable.";
}

function updateBrowserSummary(payload) {
  if (!browserInfoEl) return;
  if (!payload || !payload.title) {
    browserInfoEl.textContent = "Browser summary not available.";
    return;
  }
  const parts = [payload.title];
  if (payload.url) {
    parts.push(payload.url);
  }
  browserInfoEl.textContent = parts.join(" — ");
}

function updateSystemStatus(payload) {
  if (!payload || !payload.description) {
    systemStatusEl.textContent = "System telemetry unavailable.";
    return;
  }
  systemStatusEl.textContent = payload.description;
}

function updateWeather(payload) {
  weatherCache = payload || weatherCache;
  if (!weatherCache || !weatherCache.message) {
    weatherEl.textContent = "Weather data not available.";
    return;
  }
  const ts = new Date(weatherCache.timestamp * 1000).toLocaleTimeString();
  weatherEl.textContent = `${weatherCache.location}: ${weatherCache.message} (updated ${ts})`;
}

function updatePersonaInfo(payload) {
  if (!payload) return;
  if (personaSelect && payload.current) {
    personaSelect.value = payload.current;
    saveConfig({ persona: payload.current });
  }
  if (personaTone && payload.tone) {
    personaTone.textContent = payload.tone;
  }
  if (personaPause && payload.pause) {
    personaPause.textContent = payload.pause;
  }
}

function pushAlert(message) {
  if (!message) return;
  const li = document.createElement("li");
  li.className = "entry alert-item";
  li.innerHTML = `<span class="label">Alert</span><div>${message}</div>`;
  alertsEl.prepend(li);
  while (alertsEl.children.length > 5) {
    alertsEl.removeChild(alertsEl.lastChild);
  }
}

function setAssistantState(state) {
  assistantStateEl.textContent = state;
  orbEl.style.animationDuration = state.toLowerCase().includes("speaking") ? "1.5s" : "3s";
}

function connectWebSocket() {
  socket = new WebSocket(WS_URL);

  socket.addEventListener("open", () => {
    connectionEl.textContent = "Connected";
    setAssistantState("Listening for wake word…");
  });

  socket.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "conversation") {
        appendEntry("Jarvis", data.payload.assistant || "");
        appendEntry("User", data.payload.user || "");
        updateWindow(data.payload.window || {});
        if (data.payload.browser) {
          updateBrowserSummary(data.payload.browser);
        }
        updateWeather(data.payload.weather);
        setAssistantState("Responding…");
        setTimeout(() => setAssistantState("Listening for wake word…"), 2000);
      } else if (data.type === "window_update") {
        updateWindow(data.payload || {});
      } else if (data.type === "browser_summary") {
        updateBrowserSummary(data.payload || {});
      } else if (data.type === "system_status") {
        updateSystemStatus(data.payload || {});
      } else if (data.type === "alert") {
        pushAlert(data.payload?.message);
      }
    } catch (error) {
      console.error("WebSocket message error", error);
    }
  });

  socket.addEventListener("close", () => {
    connectionEl.textContent = "Disconnected. Retrying…";
    setTimeout(connectWebSocket, 3000);
  });

  socket.addEventListener("error", (error) => {
    console.error("WebSocket error", error);
    socket.close();
  });
}

function startStatusPolling() {
  if (statusIntervalId) {
    clearInterval(statusIntervalId);
  }
  pollStatus();
  statusIntervalId = setInterval(pollStatus, 5000);
}

async function submitManualCommand(text) {
  try {
    const res = await fetch(STATUS_URL.replace("/status", "/commands"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": config.remoteApiKey || "" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    manualResult.textContent = `Queued: "${text}"`;
    manualResult.style.color = "#4dd4ff";
  } catch (error) {
    manualResult.textContent = `Error: ${error.message}`;
    manualResult.style.color = "#ff6b6b";
  }
}

async function pollStatus() {
  if (!config.remoteApiKey) return;
  try {
    const res = await fetch(STATUS_URL, {
      headers: { "X-API-Key": config.remoteApiKey },
    });
    if (!res.ok) return;
    const data = await res.json();
    updateSystemStatus(data.system);
    updateWindow(data.window || {});
    updateBrowserSummary(data.browser || data.awareness?.browser);
    updateWeather(data.weather);
    updatePersonaInfo(data.persona);
    const remoteStatusEl = document.getElementById("remote-status");
    if (remoteStatusEl) {
      const manual = data.pending_manual_commands || [];
      remoteStatusEl.textContent = manual.length
        ? `${manual.length} manual command(s) queued.`
        : "Ready for remote commands.";
    }
  } catch (error) {
    console.error("Status poll failed", error);
  }
}

manualForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = manualInput.value.trim();
  if (!value) return;
  submitManualCommand(value);
  manualInput.value = "";
});

quickActions.forEach((button) => {
  button.addEventListener("click", () => {
    const value = button.dataset.command;
    if (!value) return;
    manualInput.value = value;
    submitManualCommand(value);
  });
});

setInterval(() => {
  const now = new Date();
  const clockEl = document.getElementById("clock");
  if (clockEl) {
    clockEl.textContent = now.toLocaleTimeString();
  }
}, 1000);

window.addEventListener("DOMContentLoaded", () => {
  loadConfig();
  onboardingForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const remote = onboardingRemote.value.trim();
    if (!remote) {
      onboardingRemote.focus();
      return;
    }
    saveConfig({
      remoteApiKey: remote,
      groqApiKey: onboardingGroq.value.trim(),
      weatherApiKey: onboardingWeather.value.trim(),
    });
    onboardingModal.classList.add("hidden");
    connectWebSocket();
    startStatusPolling();
  });

  onboardingSkip.addEventListener("click", () => {
    onboardingModal.classList.add("hidden");
    connectWebSocket();
    startStatusPolling();
  });

  if (config.remoteApiKey) {
    onboardingModal.classList.add("hidden");
    connectWebSocket();
    startStatusPolling();
  }

  if (personaSelect) {
    personaSelect.addEventListener("change", async (event) => {
      const value = event.target.value;
      saveConfig({ persona: value });
      try {
        const res = await fetch("http://127.0.0.1:8801/persona", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": config.remoteApiKey || "",
          },
          body: JSON.stringify({ persona: value }),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        await fetchStatus();
      } catch (error) {
        console.error("Persona update failed", error);
      }
    });
  }
});
