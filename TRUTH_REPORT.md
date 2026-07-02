# FRIDAY Operator Truth Report

Audit date: 2026-06-18  
Scope: local repository at `C:\Projects\JARVIS\for wind`  
Prompt source: `C:\Users\Shreesh\Downloads\FRIDAY OPERATOR AUDIT.docx`

## Bottom Line

FRIDAY currently has a real Python package with planning, memory, file creation, browser-controller wrappers, desktop pyautogui wrappers, perception schemas, and verification heuristics.

FRIDAY is not currently a proven general-purpose computer operator.

The strongest proven behavior is:

- Building plans from heuristics or mocked LLM responses.
- Creating, reading, appending, deleting text/html/basic docx files.
- Recording/retrieving memory in local JSON stores.
- Producing `WorldState` objects from available desktop/browser state-cache inputs.
- Running mocked/unit-tested routing, planning, verification, API, provider, and memory code.

The weakest or overstated behavior is:

- End-to-end browser control with the user's live Chrome session.
- Desktop control of arbitrary applications.
- Gmail/email sending.
- Attachment workflows.
- Official-source research.
- Deep verification of content quality, citations, delivery, or real goal completion.
- The Universal Action Layer being used by the operator.

## Execution Evidence

Commands run:

| Command | Result |
|---|---|
| `python -m pytest tests/friday -q` | 381 passed, 22 warnings, 41.69s |
| `python -m pytest -q` | 431 passed, 1 failed, 110 warnings, 80.21s |
| Targeted `FileTool` smoke check | Created a real temp file, size 5, content `hello` |
| Chrome CDP port check on `127.0.0.1:9222` | Not reachable; socket and `/json/version` timed out |
| Targeted primitive smoke check | `click()` fails before init with `not_initialized`; after init with no matching target fails with `target_not_found` |
| Targeted operator research smoke check | Reported complete despite `No browser available for search` and `No browser to read from` |
| Targeted complex Gmail task smoke check | Reported complete and created a generic temp `.docx`, but search/read failed and send was only a placeholder |

Full-suite failure:

- `tests/test_prompt_builder.py::test_phase6_followups_route_to_planner` failed.
- Expected `OPENED_LAST_SITE`.
- Actual response: `I cannot perceive the current state. Awareness system may be unavailable.`

## Section 1 - Capability Inventory

Status meanings:

- Implemented: code exists and local tests or smoke checks prove basic behavior.
- Partially Implemented: code exists but behavior is limited, mocked, shallow, or not wired end-to-end.
- Stub/Placeholder: registered or routed but does not actually perform the claimed operation.
- Mock-Tested Only: tests exist but use mocks/fakes rather than real external execution.
- Not Started/Unproven: no meaningful implementation or no evidence found.

| Capability | Status | Evidence |
|---|---|---|
| Browser Navigation | Partially Implemented | `BrowserController.navigate()` uses Playwright page goto (`friday/actions/browser_controller.py:132`). `GoalExecutor` calls it only if `_browser.available` (`friday/executor.py:156`). No live CDP connection available in audit. |
| Browser Reading | Partially Implemented | `BrowserController.read_text()` reads `body` text (`friday/actions/browser_controller.py:143`). Executor reads only current page (`friday/executor.py:172`). No live browser read proven. |
| Browser Clicking | Partially Implemented | `BrowserController.click()` clicks by visible text (`friday/actions/browser_controller.py:171`). `BrowserAdapter.click()` wraps it (`friday/actions/adapters/browser.py:123`). No direct primitive tests found. |
| Browser Typing | Partially Implemented | `BrowserController.type_text()` fills selector or types into focused page (`friday/actions/browser_controller.py:183`). |
| Browser Search | Partially Implemented | `BrowserController.search_web()` goes to Google and captures body/link text (`friday/actions/browser_controller.py:196`). In smoke test, operator returned `No browser available for search`. |
| Existing Chrome Profile | Unproven/Partial | `BrowserController` attempts `connect_over_cdp` and uses first context (`friday/actions/browser_controller.py:96`). If that fails, it silently launches fresh Chromium (`friday/actions/browser_controller.py:117`). CDP port 9222 was unreachable during audit. |
| Existing Chrome Tabs | Partial | `BrowserController` uses first context page if present (`friday/actions/browser_controller.py:112`). `EnvironmentObserver` explicitly leaves browser tab collection deferred (`friday/perception/environment.py:164`). |
| Desktop Clicking | Partially Implemented | `DesktopAdapter.click()` and `DesktopActionsAdapter.click()` use pyautogui coordinates (`friday/actions/adapters/desktop.py:67`, `friday/actions/adapters/desktop_actions.py:157`). No live arbitrary-app desktop click test found. |
| Desktop Typing | Partially Implemented | `DesktopAdapter.type_text()` uses pyautogui/clipboard (`friday/actions/adapters/desktop.py:127`). No live arbitrary-app typing test found. |
| Desktop Window Switching | Partially Implemented | `SystemActions.focus_window()` and adapters use pyautogui windows (`friday/actions/system.py:150`, `friday/actions/adapters/desktop.py:264`). Tests mock pyautogui (`tests/friday/test_system_actions.py:89`). |
| Opening Applications | Partially Implemented | `SystemActions.launch_app()` uses subprocess and app aliases (`friday/actions/system.py:48`). Tests mock `subprocess.Popen` (`tests/friday/test_system_actions.py:18`). |
| File Creation | Implemented | `FileTool.create_file()` writes real files and verifies exists/size (`friday/actions/file_tool.py:27`). Smoke test created a real temp file. |
| File Editing | Partially Implemented | `FileTool.write_file()` is overwrite alias (`friday/actions/file_tool.py:101`); append/delete implemented (`friday/actions/file_tool.py:105`, `:125`). |
| Word Documents | Partially Implemented | `.docx` output creates paragraphs with `python-docx` if available (`friday/actions/file_tool.py:157`). No formatting, flag insertion, citation validation, or professional layout verification. |
| PowerPoint | Not Started/Unproven | No `friday` PowerPoint action found. |
| Email Sending | Stub/Placeholder in operator; separate old implementation exists | Operator executor returns `Communication step... (requires verified send)` (`friday/executor.py:224`). `GmailAutomation.send_email_async()` exists in old automation (`automation/gmail_actions.py:38`) but is not wired into `friday.operator`. |
| WhatsApp | Separate old implementation only | `WhatsAppAutomation.send_message_async()` exists (`automation/quick_actions.py:38`) but is app-specific and not wired into current operator. |
| Instagram | Separate old implementation only | `InstagramAutomation.get_inbox_async()` and DM methods exist (`automation/quick_actions.py:90`, `:74`) but are not proven in current run. |
| Research | Partially Implemented but can false-positive | Executor searches only if browser available (`friday/executor.py:141`). Smoke test: search/read failed, generated fallback content, operator still completed. |
| Memory | Implemented for local JSON tiers | `FridayMemory` wires working/episodic/procedural/semantic stores (`friday/memory/controller.py:80`). Tests cover memory (`tests/friday/test_memory.py`). |
| Planning | Partially Implemented | `OperatorPlanner.plan()` maps goals to capabilities (`friday/planner/operator_planner.py:118`). LLM path is mocked in tests; fallback is keyword heuristic (`friday/planner/operator_planner.py:217`). |
| Verification | Partially Implemented | `ActionVerifier` compares before/after `WorldState` (`friday/verification/verifier.py:84`). `Operator._verify_requirements()` is heuristic and can mark failed research as satisfied (`friday/operator.py:178`). |
| Replanning | Weak/Partial | Operator loops, but accepts partial progress and stops (`friday/operator.py:142`). No per-requirement repair. |
| Vision | Partially Implemented | `VisionPerception` calls model router when vision-capable model exists (`friday/perception/vision.py:71`). Tests use fake router (`tests/friday/test_vision.py`). |
| OCR | Partially Implemented | `OCREngine` wraps Tesseract (`friday/perception/ocr.py:27`). Tests use blank image/basic returns (`tests/friday/test_perception.py:65`). |
| WorldState | Implemented schema, partial population | Schema exists (`friday/perception/world_state.py:45`). `FridayEngine.perceive()` populates desktop, screen hash, browser if connected (`friday/core.py:101`). |
| UIA | Partial | `DesktopPerception` converts state-cache UIA elements (`friday/perception/desktop.py:67`). Without state cache, UI elements are empty. |
| DOM | Partial | `BrowserPerception` converts cached DOM summary (`friday/perception/browser.py:75`). It depends on external state cache, not live DOM by itself. |
| Self-Improvement | Not Started/Unproven | No safe generate-test-integrate capability found in `friday`. |
| Code Generation | Partial via LLM text generation only | `GoalExecutor._generate()` can ask model router for text (`friday/executor.py:234`). No code-specific validation loop. |
| Code Modification | Not Started/Unproven | No `friday` code edit tool. |
| Test Execution | Placeholder | Registry has `RUN_COMMAND` (`friday/tools/registry.py:61`), but executor returns gated placeholder (`friday/executor.py:220`). |
| Download File | Not Started/Unproven | Registry enum exists (`friday/tools/registry.py:73`), no executor branch found. |
| Upload/Attach File | Not Started/Unproven | Registry enum exists (`friday/tools/registry.py:74`), no executor branch found. |

## Section 2 - Universal Action Layer Audit

The Universal Action Layer exists in `friday/actions/primitives.py`, but it is not proven as the active operator execution path.

Evidence:

- `init_primitives()` creates adapters (`friday/actions/primitives.py:39`).
- `_execute_with_fallback()` resolves adapters and retries excluding failed adapters (`friday/actions/primitives.py:65`).
- `register_primitives()` can add six `universal.*` tools (`friday/actions/primitives.py:600`).
- `build_default_registry()` does not call `register_primitives()` (`friday/tools/registry.py:174`).
- `Operator.__init__()` uses `build_default_registry()` and `GoalExecutor` directly (`friday/operator.py:80`).
- `GoalExecutor._execute_step()` calls `_browser`, `FileTool`, and `SystemActions`; it does not call `friday.actions.primitives` (`friday/executor.py:136`).
- `rg` found no tests referencing `friday.actions.primitives`, `BrowserAdapter`, `DesktopAdapter`, `DesktopActionsAdapter`, or `VisionAdapter`.

Primitive table:

| Primitive | Source | Status | Real implementation? | Fallback behavior | Test coverage | Actual evidence |
|---|---|---|---|---|---|---|
| `click()` | `friday/actions/primitives.py:164` | Partially Implemented | Wrapper over selected adapter | Adapter cascade, then failed | No direct tests found | Smoke: before init `not_initialized`; after init no target `target_not_found` |
| `double_click()` | `friday/actions/primitives.py:180` | Partially Implemented | Wrapper | Adapter cascade | No direct tests found | Code evidence only |
| `right_click()` | `friday/actions/primitives.py:196` | Partially Implemented | Wrapper | Adapter cascade | No direct tests found | Code evidence only |
| `scroll()` | `friday/actions/primitives.py:212` | Partially Implemented | Wrapper; default coordinate `(960, 540)` | Adapter cascade | No direct tests found | Code evidence only |
| `drag()` | `friday/actions/primitives.py:245` | Partially Implemented | Resolves source/dest once and calls source adapter | No alternate source adapter retry after drag failure | No direct tests found | Code evidence only |
| `type_text()` | `friday/actions/primitives.py:332` | Partially Implemented | Wrapper; requires browser connected or focused element if no target | Fails with `no_focus` | No direct tests found | Code evidence only |
| `press_key()` | `friday/actions/primitives.py:380` | Partially Implemented | Wrapper | Fails with `no_focus` unless browser connected | No direct tests found | Code evidence only |
| `press_hotkey()` | `friday/actions/primitives.py:422` | Partially Implemented | Wrapper over OS-level target | Adapter cascade | No direct tests found | Code evidence only |
| `switch_window()` | `friday/actions/primitives.py:450` | Partially Implemented | Wrapper over adapter `focus_window()` | Adapter cascade | No direct tests found | Code evidence only |
| `observe()` | `friday/actions/primitives.py:466` | Partially Implemented | Summarizes supplied `WorldState`; does not capture a new one | Fails if no sources/data | No direct tests found | Code evidence only |
| `verify()` | `friday/actions/primitives.py:507` | Weak/Partial | String containment in `WorldState.all_text` | Fails if text missing | No direct tests found | Code evidence only |
| `wait_for()` | `friday/actions/primitives.py:540` | Partially Implemented | Polls a supplied `world_state_fn` for text | Timeout | No direct tests found | Code evidence only |

## Section 3 - Adapter Audit

### BrowserAdapter

Status: Partially Implemented, unproven live in audit.

What it actually does:

- Handles targets only when `world_state.browser_connected` is true (`friday/actions/adapters/browser.py:45`).
- Resolves against `world_state.browser_elements` by selector, text, or role (`friday/actions/adapters/browser.py:51`).
- Delegates click/type to `BrowserController` (`friday/actions/adapters/browser.py:123`, `:214`).
- Directly accesses `self._controller._page` for double-click, right-click, keyboard, scroll, and drag (`friday/actions/adapters/browser.py:156`, `:185`, `:258`, `:313`, `:360`).
- Cannot switch OS windows (`friday/actions/adapters/browser.py:399`).

Cannot prove:

- Profile chooser handling.
- Extension popup handling.
- Permission dialog handling.
- Recovery from browser crash.
- Attachment workflows.

### DesktopAdapter

Status: Partially Implemented.

What it actually does:

- Resolves `UIElement` objects already present in `WorldState.ui_elements` (`friday/actions/adapters/desktop.py:41`).
- Uses pyautogui at UIA bounding-box centers for click/double/right-click (`friday/actions/adapters/desktop.py:67`, `:87`, `:107`).
- Types with pyautogui, using clipboard paste for non-ASCII (`friday/actions/adapters/desktop.py:127`).
- Focuses windows by title via pyautogui (`friday/actions/adapters/desktop.py:264`).

Cannot prove:

- Arbitrary app semantic control.
- File picker control.
- Dialog handling beyond title/click primitives.
- DPI/multiple-monitor correctness.

### DesktopActionsAdapter

Status: Partially Implemented.

What it actually does:

- Handles raw coordinates, window titles, and non-semantic OS actions (`friday/actions/adapters/desktop_actions.py:45`).
- Uses pyautogui for pointer, keyboard, scroll, drag, and window focus (`friday/actions/adapters/desktop_actions.py:157`, `:218`, `:238`, `:256`, `:281`, `:325`, `:356`).
- For missing window-title matches, it returns a placeholder resolved element with confidence `0.5` (`friday/actions/adapters/desktop_actions.py:127`).

Risk:

- Placeholder resolution can allow later operations to proceed with weak evidence.

### VisionAdapter

Status: Coordinate/OCR fallback only.

What it actually does:

- Resolves text from `world_state.ocr_regions` or explicit coordinates (`friday/actions/adapters/vision.py:49`).
- Uses pyautogui at OCR/coordinate centers (`friday/actions/adapters/vision.py:110`).
- Cannot switch windows (`friday/actions/adapters/vision.py:277`).

It is not image understanding. Image understanding is separate `VisionPerception`, model-router-based, and mock-tested.

## Section 4 - Playwright Audit

| Question | Answer | Evidence |
|---|---|---|
| Can FRIDAY use my actual Chrome profile? | PARTIAL/UNPROVEN | `BrowserController` attempts CDP connection and uses first context (`friday/actions/browser_controller.py:102`). Audit CDP port 9222 timed out. If CDP fails, it launches fresh Chromium without the user's profile (`friday/actions/browser_controller.py:117`). |
| Can FRIDAY use an already-running Chrome instance? | PARTIAL | Only if that instance exposes CDP on port 9222. `connect_over_cdp` is used (`friday/actions/browser_controller.py:105`). |
| Can FRIDAY handle profile chooser? | PARTIAL outside current operator | Old `automation/chrome_pipeline.py` has OCR profile selection (`automation/chrome_pipeline.py:117`), but current `friday.operator` does not use it. |
| Can FRIDAY handle browser lock screen? | PARTIAL outside current operator | Old pipeline detects/unlocks extension lock (`automation/chrome_pipeline.py:149`, `:196`), not wired into `friday.operator`. |
| Can FRIDAY handle login prompts? | PARTIAL detection only | WorldState derives possible login keywords (`friday/perception/world_state.py:323`). Gmail/Instagram old automation returns failure if sign-in page detected (`automation/gmail_actions.py:43`, `automation/quick_actions.py:156`). |
| Can FRIDAY handle extension popups? | UNPROVEN | No active operator path. |
| Can FRIDAY handle permission dialogs? | UNPROVEN | No tested active path. |
| Can FRIDAY recover from browser crashes? | PARTIAL at cache level only | Old `PlaywrightManager.invalidate_cache()` clears cached references (`automation/playwright_manager.py:314`). Not integrated into `friday.operator`. |
| Can FRIDAY reuse existing tabs? | PARTIAL | `BrowserController` picks first existing page (`friday/actions/browser_controller.py:112`). Environment tab observation is deferred (`friday/perception/environment.py:164`). |

## Section 5 - Desktop Control Audit

| Can FRIDAY... | Answer | Evidence |
|---|---|---|
| Click desktop icons? | PARTIAL/UNPROVEN | Coordinate and UIA clicking exist via pyautogui. No live desktop-icon test found. |
| Open applications? | PARTIAL | `SystemActions.launch_app()` exists (`friday/actions/system.py:48`). Tests mock process launch. |
| Move windows? | NO/UNPROVEN | Focus exists. No move/resize primitive found. |
| Switch windows? | PARTIAL | `focus_window()` exists (`friday/actions/system.py:150`). |
| Select profile cards? | PARTIAL outside current operator | Old OCR Chrome pipeline has profile selection (`automation/chrome_pipeline.py:117`). |
| Handle popups? | PARTIAL/UNPROVEN | Derived facts detect error/consent keywords (`friday/perception/world_state.py:323`), no general popup solver proven. |
| Handle file pickers? | NO/UNPROVEN | No active upload/attach/file-picker workflow found. |
| Handle dialogs? | PARTIAL/UNPROVEN | Verification has `dismiss_dialog` heuristic (`friday/verification/verifier.py:354`), but no active general dialog execution proven. |
| Handle unexpected screens? | NO/UNPROVEN | No proven recovery loop for arbitrary screens. |
| Handle multiple monitors? | PARTIAL screenshot only | MSS screen capture supports monitor index (`friday/perception/screen.py:70`), but actions do not prove multi-monitor target correctness. |
| Handle DPI scaling? | UNPROVEN | No DPI handling evidence found. |
| Handle browser profile selection? | PARTIAL outside current operator | Old OCR path only. |
| Handle login forms? | PARTIAL/UNPROVEN | Can type/click if selectors/focus work; no credential/login solver in `friday.operator`. |
| Handle signup forms? | NO/UNPROVEN | No general form reasoning and submission proof. |
| Handle arbitrary applications? | NO | UIA/pyautogui primitives exist, but no arbitrary-app planning/execution proof. |

## Section 6 - WorldState Audit

Current schema is `WorldState` in `friday/perception/world_state.py:45`.

Actual fields:

- Metadata: `timestamp`, `build_duration_ms`, `sources_used`.
- Desktop: `active_window`, `cursor_position`, `focused_element`, `ui_elements`.
- Visual: `screenshot_hash`, `ocr_regions`, `screen_regions`.
- Browser: `browser_url`, `browser_title`, `browser_elements`, `browser_connected`.
- Derived: `possible_login_screen`, `possible_error_dialog`, `possible_profile_selection`, `possible_consent_dialog`, `possible_loading`, `has_text_input_focused`, `has_modal_overlay`.

Population sources:

- `FridayEngine.perceive()` builds the state (`friday/core.py:101`).
- Desktop active window/cursor/UIA from `DesktopPerception` (`friday/core.py:111`).
- Screenshot hash from `ScreenCapture.grab_hash_only()` (`friday/core.py:127`).
- Browser URL/title/elements from `BrowserPerception` only if connected (`friday/core.py:132`).

Confidence metrics:

- UI elements have `confidence` (`friday/perception/types.py:51`).
- OCR regions have `confidence` (`friday/perception/types.py:66`).
- Browser elements do not carry confidence beyond source/type.
- WorldState itself has no global confidence score. API adds semantic coverage through resolver quality (`friday/core.py:82`).

Known blind spots:

- No clipboard content.
- No open file handles.
- No full browser-tab enumeration in current observer (`friday/perception/environment.py:164`).
- `has_modal_overlay` is hardcoded false (`friday/perception/world_state.py:342`).
- Browser DOM depends on state cache summary, not active live DOM unless that cache is maintained elsewhere.
- OCR is not added by `FridayEngine.perceive()`; screen hash is captured, OCR regions are not populated there.

## Section 7 - Research Claim Audit

Test request: `Research laptops and create summary`

Targeted smoke result:

- `completed True`
- `requirements 3 / 3`
- Trace contained:
  - `Gather information -> No browser available for search`
  - `Extract relevant content -> No browser to read from`
  - `Produce content -> Generated 49 chars`
  - `All requirements satisfied - goal complete`

Answer:

| Research step | Did it happen? | Evidence |
|---|---|---|
| Actually search? | NO in smoke test | Trace: no browser available. |
| Actually open pages? | NO in smoke test | No browser. |
| Actually read pages? | NO in smoke test | Trace: no browser to read from. |
| Actually extract content? | NO in smoke test | No page content. |
| Actually summarize content? | PARTIAL/FALSE POSITIVE | Generated fallback text without gathered info. |
| Summarize from model knowledge? | PARTIAL | With no model router, `_generate()` returns `Content about ...` (`friday/executor.py:236`). With model router, it can prompt an LLM without source enforcement. |

Root cause:

- `Operator._verify_requirements()` marks information requirements satisfied if `gathered_info` or `produced_content` exists (`friday/operator.py:196`).
- This allows generated content to satisfy research even when search and extraction failed.

## Section 8 - General Operator Test Matrix

These are evidence-based outcomes from code inspection, tests, and smoke checks. They are not all live external-app runs. Where live evidence does not exist, the result is not PASS.

| Task | Difficulty | Result | Reason |
|---|---:|---|---|
| Open Chrome | Easy | PARTIAL | App launch exists, but tests mock launch and no live Chrome launch was performed. |
| Open Notepad | Easy | PARTIAL | Same `SystemActions.launch_app()` path; mocked tests. |
| Create text file | Easy | PASS | Live `FileTool` smoke created a real file. |
| Create basic docx | Easy | PARTIAL | Code writes paragraphs; no formatting validation. |
| Read local text file | Easy | PASS | `FileTool.read_file()` implemented/tested. |
| Rename/move files | Medium | FAIL/UNPROVEN | Registry enum exists; no `FileTool.move_file()` implementation found. |
| Search web | Medium | PARTIAL | Code exists, but no live browser/CDP in audit. |
| Research topic | Medium | FAIL as verified operator behavior | Smoke reported complete without search/read. |
| Read Instagram DMs | Medium | PARTIAL outside operator | Old Instagram automation exists, not wired/proven in `friday.operator`. |
| Create Word report | Medium | PARTIAL | Basic `.docx` possible, professional report not proven. |
| Create PowerPoint | Medium | FAIL | No implementation found. |
| Send email | Hard | FAIL in operator | Executor placeholder only. Old Gmail automation is separate. |
| Attach document to email | Hard | FAIL | No active attach/upload workflow. |
| Download file | Hard | FAIL/UNPROVEN | Enum exists; no executor implementation. |
| Handle popup | Hard | FAIL/UNPROVEN | Detection heuristics only. |
| Fill form | Hard | PARTIAL/UNPROVEN | Browser/desktop typing exists, no general form completion proof. |
| Book ticket | Insane | FAIL | Requires search/form/payment/session/dialog handling not proven. |
| Use unfamiliar website | Insane | FAIL/UNPROVEN | No robust DOM exploration/recovery proof. |
| Use unfamiliar desktop app | Insane | FAIL/UNPROVEN | No arbitrary UIA workflow proof. |
| Cross browser + desktop workflow | Insane | FAIL/UNPROVEN | Operator does not use Universal Action Layer and lacks verified attach/send chain. |

## Section 9 - Hallucination Audit

Places where FRIDAY appears more capable than it is:

| Claim/Surface | Reality | Evidence |
|---|---|---|
| "Every higher-level capability composes from primitives" | False for current operator | `GoalExecutor` directly calls browser/file/system actions (`friday/executor.py:136`). |
| Universal Action Layer preferred in registry | Not by default | `build_default_registry()` returns 25 tools and does not include `universal.*`; they appear only after explicit `register_primitives()`. |
| Research completed | Can be false positive | Smoke test completed with search/read failures. |
| Email sent/delivered | Operator placeholder | `SEND_MESSAGE`/`SEND_EMAIL` returns text only (`friday/executor.py:224`). |
| Delivery requirement verified | Delivery is made non-blocking | `Operator._verify_requirements()` sets delivery requirement `blocking = False` (`friday/operator.py:220`). |
| User Chrome profile available | Unproven and falls back to fresh Chromium | `BrowserController._connect()` launches fresh Chromium if CDP fails (`friday/actions/browser_controller.py:117`). |
| Browser tabs observed | Deferred | Environment observer comments tabs are deferred (`friday/perception/environment.py:164`). |
| Modal overlay detection | Hardcoded false | `has_modal_overlay=False` (`friday/perception/world_state.py:342`). |
| Professional Word reports | Basic paragraphs only | `_write_docx()` adds one paragraph per line (`friday/actions/file_tool.py:157`). |
| Run command capability | Safety-gated placeholder | Executor returns placeholder (`friday/executor.py:220`). |
| Gmail plugin proves operator Gmail | Separate old plugin, not `friday.operator` | `plugins/gmail_sender/module.py:10` calls old `automation.gmail_actions`. |
| Tests prove real external systems | Many use mocks | Examples: operator mocked router (`tests/friday/test_operator.py:10`), system actions mock Popen/pyautogui (`tests/friday/test_system_actions.py:18`), providers mock API clients (`tests/friday/test_providers.py`). |

## Section 10 - Subsystem Scores

| Subsystem | Score | Why |
|---|---:|---|
| Planning | 5/10 | Planner exists and is tested, but fallback is keyword heuristic and LLM path is mock-tested. |
| Perception | 4/10 | WorldState schema is real; live population depends on state cache/CDP/UIA availability. OCR not wired into main `perceive()`. |
| Browser | 3/10 | Controller and wrappers exist, but CDP was unreachable and profile use is unproven. |
| Desktop | 3/10 | pyautogui/UIA wrappers exist; arbitrary desktop workflows are unproven. |
| Memory | 7/10 | Local memory tiers are implemented/tested. Semantic embeddings depend on provider availability. |
| Research | 2/10 | Search path exists but can falsely complete without search/read. |
| Verification | 3/10 | Action verifier exists; operator requirement verification is shallow and false-positive-prone. |
| Adaptation | 2/10 | Replanner exists, but operator accepts partial progress and lacks per-requirement repair. |
| Recovery | 2/10 | Some cache/reset/error hints exist; no proven recovery from unexpected screens/browser crashes. |
| Generalization | 2/10 | Registry and capability language exist, but end-to-end behavior is not proven for unfamiliar tasks. |

## Final Question

Task:

> Research France's position on an ongoing conflict using official government sources, create a professional position paper with flag and citations, save it as a document, open Gmail using the user's existing browser session, attach the document, and send it.

Answer: NO.

Exact failure points:

1. Official government-source research is not guaranteed. The executor searches Google only if a browser controller is available (`friday/executor.py:141`). CDP was not reachable in audit. No source-domain enforcement exists.
2. Page opening and reading are not proven in the current environment. Browser CDP on port 9222 timed out.
3. Citation extraction is not implemented as a verified requirement. Content generation can occur without gathered sources.
4. The position paper would be a basic `.docx` with paragraphs only (`friday/actions/file_tool.py:157`). No flag insertion, citation formatting, professional layout, or render verification exists.
5. Gmail opening through the user's existing browser session is unproven. `BrowserController` can fall back to fresh Chromium if CDP fails (`friday/actions/browser_controller.py:117`).
6. Attaching a document is not implemented in the active operator.
7. Sending email is not implemented in the active operator. The executor returns a placeholder for send/email capabilities (`friday/executor.py:224`).
8. Delivery verification is explicitly avoided by making delivery requirements non-blocking (`friday/operator.py:220`).
9. A targeted smoke run of this exact task with no browser/model router produced a generic temp `.docx` and reported `completed True`, even though search/read failed and delivery was only a placeholder. That is a false positive, not success.

Reality: FRIDAY can partially create a basic document file. It cannot currently complete the requested end-to-end task.
