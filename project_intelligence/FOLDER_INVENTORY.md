# Folder Inventory

| Folder | Responsibility | Subsystems | Criticality | Notes |
|---|---|---|---|---|
| .git | Git metadata | Git metadata | High | Primary repo history. |
| .git - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| .git - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| .pytest_cache | Other | Other | Unknown |  |
| .pytest_cache - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| .pytest_cache - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| .venv | Virtual env | Virtual env | Medium | Environment snapshot; should not be committed/relied upon for logic. |
| .venv312 | Virtual env | Virtual env | Medium | Environment snapshot; should not be committed/relied upon for logic. |
| __pycache__ | Other | Other | Unknown |  |
| __pycache__ - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| __pycache__ - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| automation | Automation layer (browser + desktop + cognitive loop). | Subsystem | Critical | Primary system code. |
| automation - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| automation - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| awareness | Perception (UIA/window/process/browser state cache). | Subsystem | Critical | Primary system code. |
| awareness - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| awareness - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| build | Build artifacts | Build artifacts | Low | Packaged outputs. |
| build - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| build - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| config | Other | Other | Unknown |  |
| config - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| config - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| core | Orchestration (assistant routing, reasoning, scheduling, safety). | Subsystem | Critical | Primary system code. |
| core - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| core - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| desktop_app | Electron desktop shell. | UI/Client | High | User interfaces and IPC. |
| desktop_app - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| desktop_app - Copy (2) | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| dist | Build artifacts | Build artifacts | Low | Packaged outputs. |
| e2e | Other | Other | Unknown |  |
| friday_env | Virtual env | Virtual env | Medium | Environment snapshot; should not be committed/relied upon for logic. |
| jarvis_ai | Other | Other | Unknown |  |
| jarvis_memory | Other | Other | Unknown |  |
| logs | Runtime artifacts | Runtime artifacts | Low | Generated outputs. |
| memory | Memory controller + UI pattern memory. | Subsystem | Critical | Primary system code. |
| memory_store | Other | Other | Unknown |  |
| mobile_dashboard | React/Vite dashboard client. | UI/Client | High | User interfaces and IPC. |
| node_modules | JS deps | JS deps | Low | Vendored dependencies; ignore for architecture. |
| plugins | Plugin loader and capability extensions. | Support | Medium | Supporting systems and tooling. |
| project_intelligence | Other | Other | Unknown |  |
| remote | Webhook/Telegram relays into local server. | Support | Medium | Supporting systems and tooling. |
| screenshots | Runtime artifacts | Runtime artifacts | Low | Generated outputs. |
| scripts | PowerShell scripts, reality checks. | Support | Medium | Supporting systems and tooling. |
| security | Credential vault + training modes. | Subsystem | Critical | Primary system code. |
| server | FastAPI remote control server + dashboard. | Subsystem | Critical | Primary system code. |
| services | External API services (weather/maps/news). | Support | Medium | Supporting systems and tooling. |
| tests | Python tests. | Support | Medium | Supporting systems and tooling. |
| testsprite_tests | Other | Other | Unknown |  |
| tts_output | Runtime artifacts | Runtime artifacts | Low | Generated outputs. |
| tts_output - Copy | Snapshot/Duplicate | Snapshot/Duplicate | Low | Likely an older copy of the repo subtree; treat as legacy reference only. |
| ui | WebSocket UI client and local control surfaces. | UI/Client | High | User interfaces and IPC. |
| wake_words | Porcupine wake-word assets. | Support | Medium | Supporting systems and tooling. |
