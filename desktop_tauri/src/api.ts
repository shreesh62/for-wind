/**
 * FRIDAY API client — shared by desktop and (future) mobile.
 *
 * Wraps the FastAPI backend at localhost:8801.
 * Same contracts the mobile app will use.
 */

const DEFAULT_BASE = "http://127.0.0.1:8801";

export interface CommandResult {
  ok: boolean;
  text: string;
  mode: string;
  complexity: number;
  handled: boolean;
  verified: boolean | null;
  duration_ms: number;
  error: string | null;
}

export interface SystemStatus {
  online: boolean;
  mode: string;
  active_goal: string | null;
  uptime_seconds: number;
  memory_stats: Record<string, any>;
  model_stats: Record<string, any>;
}

export interface MemoryEpisode {
  user: string;
  assistant: string;
  mode: string;
  timestamp: number;
  success: boolean | null;
}

export class FridayClient {
  private base: string;
  private apiKey: string;

  constructor(apiKey: string, base: string = DEFAULT_BASE) {
    this.apiKey = apiKey;
    this.base = base;
  }

  private headers(): HeadersInit {
    return {
      "Content-Type": "application/json",
      "X-API-Key": this.apiKey,
    };
  }

  async health(): Promise<{ status: string; version: string; uptime: number }> {
    const res = await fetch(`${this.base}/api/health`);
    return res.json();
  }

  async command(text: string, wakeWord?: string): Promise<CommandResult> {
    const res = await fetch(`${this.base}/api/command`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ text, wake_word: wakeWord ?? null }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Request failed");
    }
    return res.json();
  }

  async status(): Promise<SystemStatus> {
    const res = await fetch(`${this.base}/api/status`, {
      headers: this.headers(),
    });
    return res.json();
  }

  async recentMemory(limit: number = 10): Promise<{ episodes: MemoryEpisode[] }> {
    const res = await fetch(`${this.base}/api/memory/recent?limit=${limit}`, {
      headers: this.headers(),
    });
    return res.json();
  }

  async searchMemory(query: string, topK: number = 5): Promise<{ results: any[] }> {
    const res = await fetch(`${this.base}/api/memory/search`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ query, top_k: topK }),
    });
    return res.json();
  }

  async models(): Promise<{ providers: string[]; models: any[]; usage: any }> {
    const res = await fetch(`${this.base}/api/models`, {
      headers: this.headers(),
    });
    return res.json();
  }

  /**
   * Open a WebSocket connection for real-time updates.
   * Returns the WebSocket; caller attaches event handlers.
   */
  connectWebSocket(): WebSocket {
    const wsBase = this.base.replace("http://", "ws://").replace("https://", "wss://");
    return new WebSocket(`${wsBase}/api/ws?token=${encodeURIComponent(this.apiKey)}`);
  }
}
