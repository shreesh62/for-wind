import React, { useEffect, useRef, useState } from "react";

const STATUS_URL = "http://127.0.0.1:8801/status";
const COMMANDS_URL = "http://127.0.0.1:8801/commands";

export default function App() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("REMOTE_API_KEY") || "");
  const [status, setStatus] = useState("Disconnected");
  const [weather, setWeather] = useState(null);
  const [system, setSystem] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [conversation, setConversation] = useState([]);
  const [pendingCommands, setPendingCommands] = useState([]);
  const [commandText, setCommandText] = useState("");
  const [message, setMessage] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const refreshTimer = useRef(null);

  const fetchStatus = async (apiKeyOverride) => {
    const key = apiKeyOverride || apiKey;
    if (!key) return;
    try {
      const res = await fetch(STATUS_URL, {
        headers: { "X-API-Key": key },
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setWeather(data.weather || null);
      setSystem(data.system || null);
      setAlerts(data.alerts || []);
      setConversation(data.recent_conversation || []);
      setPendingCommands(data.pending_manual_commands || []);
      setStatus("Connected");
      setLastUpdated(new Date());
    } catch (error) {
      setStatus(`Error: ${error.message}`);
    }
  };

  useEffect(() => {
    if (!apiKey) return;
    localStorage.setItem("REMOTE_API_KEY", apiKey);
    fetchStatus(apiKey);
  }, [apiKey]);

  useEffect(() => {
    if (refreshTimer.current) {
      clearInterval(refreshTimer.current);
      refreshTimer.current = null;
    }
    if (!apiKey || !autoRefresh) {
      return;
    }
    refreshTimer.current = setInterval(() => fetchStatus(), 5000);
    return () => {
      if (refreshTimer.current) {
        clearInterval(refreshTimer.current);
      }
    };
  }, [apiKey, autoRefresh]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!commandText.trim() || !apiKey) return;
    try {
      const res = await fetch(COMMANDS_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify({ text: commandText }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      setMessage(`Queued: "${commandText}"`);
      setCommandText("");
      fetchStatus();
    } catch (error) {
      setMessage(`Error: ${error.message}`);
    }
  };

  const handleQuickAction = async (text) => {
    setCommandText(text);
    await handleSubmit({ preventDefault: () => {} });
  };

  const handleManualRefresh = () => {
    fetchStatus();
    setMessage("Status refreshed");
  };

  const toggleAutoRefresh = () => {
    setAutoRefresh((prev) => !prev);
  };

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Jarvis Remote</h1>
          <p>{status}</p>
        </div>
        <input
          type="password"
          placeholder="API Key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
      </header>

      <main className="grid">
        <section className="card">
          <h2>Weather</h2>
          {weather ? (
            <>
              <p>{weather.location}</p>
              <p>{weather.message}</p>
              <p className="muted">
                Updated {new Date(weather.timestamp * 1000).toLocaleTimeString()}
              </p>
            </>
          ) : (
            <p>No weather data.</p>
          )}
        </section>

        <section className="card">
          <h2>System</h2>
          <p>{system?.description || "No telemetry."}</p>
          <div className="muted">
            <div>Status: {status}</div>
            {lastUpdated && (
              <div>Last updated: {lastUpdated.toLocaleTimeString()}</div>
            )}
          </div>
          <div className="muted" style={{ marginTop: "12px" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={toggleAutoRefresh}
              />
              Auto-refresh every 5s
            </label>
            <button className="muted" style={{ marginTop: "8px" }} onClick={handleManualRefresh}>
              Refresh now
            </button>
          </div>
        </section>

        <section className="card">
          <h2>Alerts</h2>
          <ul className="list">
            {alerts.map((item, idx) => (
              <li key={idx}>
                <span className="muted">
                  {new Date(item.timestamp * 1000).toLocaleTimeString()}
                </span>
                <div>{item.message}</div>
              </li>
            ))}
            {alerts.length === 0 && <li>No alerts.</li>}
          </ul>
        </section>

        <section className="card">
          <h2>Conversation</h2>
          <ul className="list">
            {conversation.map((turn, idx) => (
              <li key={idx}>
                <span className="muted">
                  {new Date(turn.timestamp * 1000).toLocaleTimeString()}
                </span>
                <div><strong>You:</strong> {turn.user}</div>
                <div><strong>Jarvis:</strong> {turn.assistant}</div>
              </li>
            ))}
            {conversation.length === 0 && <li>No recent conversation.</li>}
          </ul>
        </section>

        <section className="card">
          <h2>Manual Command</h2>
          <form onSubmit={handleSubmit} className="form">
            <input
              value={commandText}
              onChange={(e) => setCommandText(e.target.value)}
              placeholder="Type a command"
            />
            <button type="submit">Send</button>
          </form>
          <p className="muted">{message}</p>
        </section>

        <section className="card">
          <h2>Quick Actions</h2>
          <div className="form" style={{ flexWrap: "wrap" }}>
            <button type="button" onClick={() => handleQuickAction("status report")}>Status Report</button>
            <button type="button" onClick={() => handleQuickAction("run morning briefing")}>Morning Briefing</button>
            <button type="button" onClick={() => handleQuickAction("refresh weather data")}>Refresh Weather</button>
          </div>
          <div className="muted" style={{ marginTop: "12px" }}>
            <div>Pending commands:</div>
            {pendingCommands.length === 0 && <div>None</div>}
            {pendingCommands.map((cmd, idx) => (
              <div key={`${cmd}-${idx}`}>• {cmd}</div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
