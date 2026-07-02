# OWNER ACTION REQUIRED

## Configure Chrome Profile for Logged-In Sessions

### Why
FRIDAY can now control Chrome via Playwright (just tested — it navigated to
Instagram successfully). But it's using a dedicated profile directory, so it
doesn't have your Instagram/WhatsApp/Gmail logins.

### What to Do

**Option A (recommended): Point to your real Chrome profile**

Add to `.env`:
```
JARVIS_CHROME_USER_DATA_DIR=C:\Users\Shreesh\AppData\Local\Google\Chrome\User Data
```

This makes FRIDAY use your actual Chrome where Instagram, WhatsApp, etc.
are already logged in. **Important**: Close Chrome before starting the FRIDAY
server (Chrome locks the profile — only one process can use it).

**Option B: Log in once in the FRIDAY Chrome instance**

1. Start: `python -m friday.api.server` (Chrome opens with debug port)
2. Manually log into Instagram, WhatsApp, Gmail in that Chrome window
3. Sessions persist across restarts

### How to Test

```powershell
# Close all Chrome first
Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# Start FRIDAY
python -m friday.api.server

# In another terminal, send a command:
$body = '{"text":"Open Instagram and check who has messaged me","wake_word":"friday"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8801/api/command" -Method Post `
  -Headers @{"X-API-Key"="shreesh1201";"Content-Type"="application/json"} `
  -Body $body
```

Should navigate to Instagram DMs and (when logged in) read the message list.

### What's Working Now
- ✅ FRIDAY launches Chrome with remote debugging port
- ✅ Playwright connects and controls the browser
- ✅ Navigation to URLs (Instagram, WhatsApp, Gmail, etc.)
- ✅ Multi-step plan decomposition (Level 2)
- ✅ DOM-based interaction (click, type, read)
- ⚠ Login state needed for site-specific content

### Status
- 324 tests passing
- Server output shows: `[✓] Browser: Chrome connected (remote debug)`
- Tested: navigated to instagram.com/direct/inbox (4.2s)
