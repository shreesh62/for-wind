import React, { useState, useRef, useEffect, useCallback } from "react";
import { FridayClient, CommandResult, SystemStatus } from "./api";
import "./styles.css";

interface Message {
  role: "user" | "assistant";
  text: string;
  mode?: string;
  complexity?: number;
  timestamp: number;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"jarvis" | "friday">("jarvis");
  const [apiKey, setApiKey] = useState(localStorage.getItem("friday_api_key") || "");
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [showStatus, setShowStatus] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const clientRef = useRef<FridayClient | null>(null);

  // Initialize client when API key set
  useEffect(() => {
    if (apiKey) {
      clientRef.current = new FridayClient(apiKey);
      // Test connection
      clientRef.current.health()
        .then(() => setConnected(true))
        .catch(() => setConnected(false));
    }
  }, [apiKey]);

  // Poll status every 10s
  useEffect(() => {
    if (!apiKey || !clientRef.current) return;
    const poll = () => {
      clientRef.current?.status()
        .then(setStatus)
        .catch(() => {});
    };
    poll();
    const interval = setInterval(poll, 10000);
    return () => clearInterval(interval);
  }, [apiKey]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendCommand = useCallback(async () => {
    if (!input.trim() || !clientRef.current) return;

    const userMsg: Message = { role: "user", text: input, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    const cmd = input;
    setInput("");
    setBusy(true);

    try {
      const data: CommandResult = await clientRef.current.command(cmd);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.text || data.error || "No response",
          mode: data.mode,
          complexity: data.complexity,
          timestamp: Date.now(),
        },
      ]);
      setMode(data.mode === "friday" ? "friday" : "jarvis");
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `Error: ${err.message}. Is the backend running? (python -m friday.api.server)`,
          timestamp: Date.now(),
        },
      ]);
      setConnected(false);
    } finally {
      setBusy(false);
    }
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendCommand();
    }
  };

  const saveApiKey = (val: string) => {
    setApiKey(val);
    localStorage.setItem("friday_api_key", val);
  };

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <span className="mode-indicator" data-mode={mode}>
            {mode === "friday" ? "⚡" : "🧠"}
          </span>
          <h1>FRIDAY</h1>
          <span className="mode-label">{mode === "friday" ? "Agent" : "Assistant"}</span>
        </div>
        <div className="header-right">
          <button className="icon-btn" onClick={() => setShowStatus(!showStatus)} title="Status">
            ⚙
          </button>
          <span className={`conn-dot ${connected ? "online" : "offline"}`} title={connected ? "Connected" : "Disconnected"} />
        </div>
      </header>

      <div className="body">
        <main className="messages">
          {messages.length === 0 && (
            <div className="empty-state">
              <p>Ask a question (JARVIS) or give a command (FRIDAY).</p>
              <p className="hint">"What is Python?" • "Open Chrome" • "Send Om hello"</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <div className="message-content">
                {msg.text}
                {msg.mode && (
                  <span className="message-meta">
                    {msg.mode === "friday" ? "⚡" : "🧠"} L{msg.complexity}
                  </span>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="message assistant">
              <div className="message-content typing">●●●</div>
            </div>
          )}
          <div ref={messagesEnd} />
        </main>

        {showStatus && status && (
          <aside className="status-panel">
            <h3>System</h3>
            <div className="stat-row">
              <span>Mode</span>
              <span>{status.mode}</span>
            </div>
            <div className="stat-row">
              <span>Uptime</span>
              <span>{Math.round(status.uptime_seconds)}s</span>
            </div>
            {status.active_goal && (
              <div className="stat-row">
                <span>Goal</span>
                <span>{status.active_goal}</span>
              </div>
            )}
            <h3>Memory</h3>
            <div className="stat-row">
              <span>Episodes</span>
              <span>{status.memory_stats?.episodic?.total_episodes ?? 0}</span>
            </div>
            <div className="stat-row">
              <span>Facts</span>
              <span>{status.memory_stats?.semantic?.total_facts ?? 0}</span>
            </div>
            <h3>Models</h3>
            <div className="stat-row">
              <span>Requests</span>
              <span>{status.model_stats?.total_requests ?? 0}</span>
            </div>
            <div className="stat-row">
              <span>Avg latency</span>
              <span>{Math.round(status.model_stats?.avg_latency_ms ?? 0)}ms</span>
            </div>
          </aside>
        )}
      </div>

      <footer className="input-area">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={mode === "friday" ? "Command FRIDAY..." : "Ask JARVIS..."}
          disabled={busy}
        />
        <button onClick={sendCommand} disabled={busy || !input.trim()}>
          Send
        </button>
      </footer>

      {!apiKey && (
        <div className="setup-overlay">
          <div className="setup-card">
            <h2>API Key Required</h2>
            <p>Enter your FRIDAY API key (REMOTE_API_KEY from .env)</p>
            <input
              type="password"
              placeholder="API Key..."
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  saveApiKey((e.target as HTMLInputElement).value);
                }
              }}
            />
            <p className="hint">Start backend: python -m friday.api.server</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
