# Implementation Plan: Universal Action Layer

## Overview

Implement `friday/actions/primitives.py` as the single entry point for all atomic actions, backed by four environment adapters resolved at runtime from the current perception state. The implementation follows a strict DAG: foundational types first, then adapters in parallel, then the resolver, then primitives, then registry wiring, and finally tests.

All primitives are async with the `_execute_with_fallback` pattern. No existing files are modified. Every primitive returns `ActionResult`.

## Tasks

- [x] 1. Implement Target dataclass
  - [x] 1.1 Create `friday/actions/target.py` with the Target dataclass
    - Define `Target` as a frozen dataclass with fields: `text: str = ""`, `role: str = ""`, `selector: str = ""`, `automation_id: str = ""`, `window_title: str = ""`, `coordinates: Optional[Tuple[int, int]] = None`, `index: int = 0`
    - Implement `__post_init__` validation that raises `ValueError` if no identifying field is set
    - Implement `has_semantic_hint` property returning `True` if text, role, selector, or automation_id is set
    - Add `from __future__ import annotations` and proper type imports
    - _Requirements: 1.2, 1.3, 3.3_

  - [x]* 1.2 Write unit tests for Target in `tests/friday/actions/test_target.py`
    - Test valid construction with each field individually
    - Test `ValueError` when no identifying field is set (empty Target)
    - Test `has_semantic_hint` returns True for text/role/selector/automation_id
    - Test `has_semantic_hint` returns False when only coordinates are set
    - Test frozen immutability (assignment raises `FrozenInstanceError`)
    - Test `index` disambiguation field defaults to 0
    - _Requirements: 1.2, 3.3_

- [x] 2. Implement Adapter Protocol and package structure
  - [x] 2.1 Create `friday/actions/adapters/__init__.py` with re-exports
    - Export `AdapterProtocol` from `.base`
    - Export all adapter classes and `AdapterResolver` (these will be added as files are created)
    - _Requirements: 2.1_

  - [x] 2.2 Create `friday/actions/adapters/base.py` with `AdapterProtocol`
    - Define `AdapterProtocol` as a `@runtime_checkable` `typing.Protocol`
    - Define `name` property returning `str`
    - Define `priority` property returning `int`
    - Define `can_handle(target: Target, world_state: WorldState) -> bool`
    - Define `resolve_element(target: Target, world_state: WorldState) -> Optional[ResolvedElement]`
    - Define async action methods: `click`, `double_click`, `right_click`, `type_text`, `press_key`, `press_hotkey`, `scroll`, `drag`, `focus_window`
    - All async methods accept `ResolvedElement` (or text/keys) and return `ActionResult`
    - Import from `friday.actions.result`, `friday.actions.target`, `friday.perception.world_state`, `friday.perception.priority`
    - _Requirements: 2.1, 5.1, 13.1_

- [x] 3. Implement BrowserAdapter
  - [x] 3.1 Create `friday/actions/adapters/browser.py` with `BrowserAdapter`
    - Set `name = "browser"` and `priority = 100`
    - Implement `can_handle`: return `True` when `world_state.browser_connected is True` AND target has text, selector, or role
    - Implement `resolve_element`: search `world_state.browser_elements` by target.text (case-insensitive), target.selector (exact match on element.selector), or target.role (match element.role). Return `ResolvedElement` with `source=PerceptionSource.BROWSER`, `priority=100`, `confidence=0.95`
    - Implement `click`: delegate to `BrowserController.click(element.text)` via `_submit()`, wrap result dict into `ActionResult.success`/`.failed`
    - Implement `type_text`: delegate to `BrowserController.type_text(text, selector)` via `_submit()`
    - Implement `double_click`, `right_click`: use Playwright `dblclick`/right-click via `_submit()` with `self._controller._page`
    - Implement `press_key`, `press_hotkey`: delegate to Playwright `keyboard.press()` / `keyboard.press()` with `+`-joined keys
    - Implement `scroll`: use `page.mouse.wheel()` via `_submit()`
    - Implement `drag`: use Playwright drag between two element bboxes
    - Implement `focus_window`: return `ActionResult.failed` (browser doesn't switch OS windows)
    - All methods wrap execution in try/except, returning `ActionResult.failed` with error_category `"adapter_failed"` or `"browser_unavailable"` on exception
    - Capture `ActionEvidence` with `before_hash` (page URL) and `after_hash` (page URL after action)
    - Constructor accepts `BrowserController` instance
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 4.1, 5.1, 5.2, 13.3_

  - [x]* 3.2 Write unit tests for BrowserAdapter in `tests/friday/actions/adapters/test_browser_adapter.py`
    - Mock `BrowserController` and `_submit()` method
    - Test `can_handle` returns True when browser_connected and target has text
    - Test `can_handle` returns False when browser not connected
    - Test `resolve_element` finds element by text in `world_state.browser_elements`
    - Test `click` delegates to controller and returns ActionResult.success
    - Test `click` returns ActionResult.failed on exception
    - Test `type_text` delegates correctly
    - Test evidence captures URL before/after
    - _Requirements: 2.1, 5.1, 5.2, 13.3_

- [x] 4. Implement DesktopAdapter
  - [x] 4.1 Create `friday/actions/adapters/desktop.py` with `DesktopAdapter`
    - Set `name = "desktop"` and `priority = 80`
    - Implement `can_handle`: return `True` when `world_state.ui_elements` contains a match for target (by text, control_type matching role, or automation_id)
    - Implement `resolve_element`: search `world_state.ui_elements` for match. Return `ResolvedElement` with `source=PerceptionSource.UIA`, `priority=80`, `confidence=element.confidence`, `bbox=element.bbox`, `raw_element=element`
    - Implement `click`: extract `element.raw_element.bbox.center` coordinates, call `pyautogui.click(x, y)`
    - Implement `double_click`: call `pyautogui.doubleClick(x, y)`
    - Implement `right_click`: call `pyautogui.rightClick(x, y)`
    - Implement `type_text`: call `pyautogui.write(text, interval=0.02)` or `pyautogui.typewrite` for ASCII, handle Unicode via `pyperclip` + `Ctrl+V`
    - Implement `press_key`: call `pyautogui.press(key)`
    - Implement `press_hotkey`: call `pyautogui.hotkey(*keys)`
    - Implement `scroll`: call `pyautogui.scroll(amount)` (negative for down) at element center or screen center
    - Implement `drag`: call `pyautogui.moveTo(src)` then `pyautogui.drag(dx, dy)` or `pyautogui.click(src)` + `pyautogui.drag`
    - Implement `focus_window`: use `pyautogui.getWindowsWithTitle(target.window_title)`, activate/restore first match
    - All methods wrapped in try/except returning `ActionResult.failed` with `error_category="adapter_failed"`
    - Capture `ActionEvidence` with `state_changed=True` on success, `window_changed` for focus
    - _Requirements: 2.1, 2.4, 3.1, 3.3, 5.1, 5.2, 14.3_

  - [x]* 4.2 Write unit tests for DesktopAdapter in `tests/friday/actions/adapters/test_desktop_adapter.py`
    - Mock `pyautogui` to avoid real mouse/keyboard
    - Test `can_handle` returns True when ui_elements match target text
    - Test `can_handle` returns False when no ui_elements match
    - Test `resolve_element` returns ResolvedElement with correct source and bbox
    - Test `click` calls `pyautogui.click` with correct coordinates
    - Test `type_text` calls `pyautogui.write`
    - Test `focus_window` activates matching window
    - _Requirements: 2.1, 5.1, 14.3_

- [x] 5. Implement DesktopActionsAdapter
  - [x] 5.1 Create `friday/actions/adapters/desktop_actions.py` with `DesktopActionsAdapter`
    - Set `name = "desktop_actions"` and `priority = 60`
    - Implement `can_handle`: return `True` when target has `window_title`, `coordinates`, or when action is OS-level (hotkeys without specific element target)
    - Implement `resolve_element`: if target has coordinates, create `ResolvedElement` with those coordinates and `source=PerceptionSource.UIA`, `priority=60`. If target has window_title, find window and create element. Return None otherwise.
    - Implement `click`: call `pyautogui.click(x, y)` using resolved coordinates
    - Implement `double_click`, `right_click`: same pattern with `pyautogui.doubleClick` / `pyautogui.rightClick`
    - Implement `type_text`: call `pyautogui.write(text)` (types into whatever is focused)
    - Implement `press_key`: call `pyautogui.press(key)`
    - Implement `press_hotkey`: call `pyautogui.hotkey(*keys)` — primary use case for OS-level shortcuts
    - Implement `scroll`: call `pyautogui.scroll(amount)` at coordinates or screen center
    - Implement `drag`: `pyautogui.moveTo(src)` + `pyautogui.mouseDown()` + `pyautogui.moveTo(dest)` + `pyautogui.mouseUp()`
    - Implement `focus_window`: use `pyautogui.getWindowsWithTitle()`, activate window via win32 if needed
    - All methods wrapped in try/except, return `ActionResult.failed` on error
    - _Requirements: 2.1, 2.4, 4.4, 5.1, 14.3_

  - [x]* 5.2 Write unit tests for DesktopActionsAdapter in `tests/friday/actions/adapters/test_desktop_actions_adapter.py`
    - Mock `pyautogui`
    - Test `can_handle` returns True for targets with coordinates or window_title
    - Test `can_handle` returns False for targets with only text/role/selector
    - Test `press_hotkey` dispatches correct key combination
    - Test `click` with explicit coordinates
    - Test `focus_window` delegates correctly
    - _Requirements: 2.1, 4.4, 5.1_

- [x] 6. Implement VisionAdapter
  - [x] 6.1 Create `friday/actions/adapters/vision.py` with `VisionAdapter`
    - Set `name = "vision"` and `priority = 30`
    - Implement `can_handle`: return `True` when `world_state.ocr_regions` contains a text match for target OR target has explicit coordinates
    - Implement `resolve_element`: search `world_state.ocr_regions` by target.text (case-insensitive). If found, return `ResolvedElement` with `source=PerceptionSource.OCR`, `priority=30`, `confidence=ocr_region.confidence`, `bbox=ocr_region.bbox`. If target has coordinates, create element with `source=PerceptionSource.SCREEN`, `priority=10`.
    - Implement `click`: extract bbox center from resolved OCRRegion, call `pyautogui.click(x, y)`
    - Implement `double_click`, `right_click`: same with `pyautogui.doubleClick`/`pyautogui.rightClick`
    - Implement `type_text`: call `pyautogui.write(text)` (types into focused element)
    - Implement `press_key`, `press_hotkey`: delegate to `pyautogui.press` / `pyautogui.hotkey`
    - Implement `scroll`: call `pyautogui.scroll(amount)` at OCR region center
    - Implement `drag`: coordinate-based drag via pyautogui
    - Implement `focus_window`: return `ActionResult.failed` (vision adapter cannot switch windows semantically)
    - Evidence: `state_changed=True` on success, `screenshot_changed=True` expected
    - _Requirements: 2.4, 3.1, 3.4, 5.1, 5.2_

  - [x]* 6.2 Write unit tests for VisionAdapter in `tests/friday/actions/adapters/test_vision_adapter.py`
    - Mock `pyautogui`
    - Test `can_handle` returns True when ocr_regions match target text
    - Test `can_handle` returns True when target has explicit coordinates
    - Test `can_handle` returns False for empty world state with text-only target
    - Test `resolve_element` returns correct coordinates from OCRRegion bbox center
    - Test `click` calls pyautogui with OCR-derived coordinates
    - _Requirements: 2.4, 3.4, 5.1_

- [x] 7. Checkpoint - Core adapters complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement AdapterResolver
  - [x] 8.1 Create `friday/actions/adapters/resolver.py` with `AdapterResolver`
    - Constructor accepts `List[AdapterProtocol]`, sorts by priority descending
    - Implement `resolve(target, world_state, exclude=None) -> Optional[Tuple[AdapterProtocol, ResolvedElement]]`
    - Iterate sorted adapters, skip those in `exclude` set
    - For each eligible adapter: check `can_handle(target, world_state)`, then call `resolve_element(target, world_state)`
    - Return first `(adapter, element)` where element is not None
    - Return `None` if no adapter can handle the target
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 4.1, 4.3_

  - [x]* 8.2 Write unit tests for AdapterResolver in `tests/friday/actions/test_resolver.py`
    - Create mock adapters with configurable `can_handle`, `resolve_element`, `priority`, `name`
    - Test highest-priority adapter is selected when multiple can handle
    - Test lower-priority adapter is selected when higher ones cannot handle
    - Test exclusion list skips named adapters
    - Test returns None when no adapter can handle
    - Test all adapters remain in candidate list regardless of world state
    - Test priority ordering is descending
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x]* 8.3 Write property test for AdapterResolver in `tests/friday/actions/test_primitives_properties.py`
    - **Property 1: Priority Resolution** — For any Target and WorldState where more than one adapter can handle, resolver selects the highest-priority adapter
    - **Property 2: All Adapters Remain Candidates** — Every registered adapter remains eligible regardless of WorldState
    - **Property 3: Fallback to Lower-Priority Adapter** — If highest cannot resolve but lower can, lower is selected
    - **Property 4: Exhaustion Produces FAILED** — When no adapter can resolve, resolver returns None
    - **Validates: Requirements 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 4.3, 4.4**

- [x] 9. Implement Primitives module
  - [x] 9.1 Create `friday/actions/primitives.py` with internal `_execute_with_fallback` function
    - Import `AdapterResolver`, `Target`, `WorldState`, `ActionResult`, `ActionTimer`, `ResolvedElement`
    - Define module-level `_resolver: Optional[AdapterResolver] = None` and `init_resolver(adapters)` function
    - Implement `_execute_with_fallback(action_name, target, world_state, execute_fn, timeout_ms)`:
      - Start `ActionTimer`
      - Loop: check elapsed time against timeout_ms, return `ActionResult.timeout()` if exceeded
      - Call `resolver.resolve(target, world_state, exclude=excluded)`
      - If None returned: return `ActionResult.failed()` with `error_category="target_not_found"`, `repair_hints=["re_observe", "scroll_to_element", "wait_for_element"]`, metadata `adapters_attempted`
      - Call `execute_fn(adapter, element)` — the adapter's specific async method
      - If success: attach timing, `metadata["source"]`, `metadata["adapter"]`, return result
      - If failed: append adapter.name to excluded list, continue loop
    - _Requirements: 2.1, 2.5, 4.1, 4.2, 4.5, 5.1, 5.3, 5.4, 5.5, 5.6_

  - [x] 9.2 Implement pointer primitives in `friday/actions/primitives.py`
    - `async def click(target, world_state, *, timeout_ms=10000) -> ActionResult`: calls `_execute_with_fallback("click", target, world_state, lambda a, e: a.click(e), timeout_ms)`
    - `async def double_click(target, world_state, *, timeout_ms=10000) -> ActionResult`: same pattern with `a.double_click(e)`
    - `async def right_click(target, world_state, *, timeout_ms=10000) -> ActionResult`: same with `a.right_click(e)`
    - `async def scroll(direction, amount, world_state, *, target=None, timeout_ms=5000) -> ActionResult`: resolve target (or create a default), call `a.scroll(direction, amount, element)`
    - `async def drag(source, dest, world_state, *, timeout_ms=15000) -> ActionResult`: resolve both source and dest targets, call `a.drag(src_element, dest_element)`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 9.3 Implement keyboard primitives in `friday/actions/primitives.py`
    - `async def type_text(text, world_state, *, target=None, timeout_ms=15000) -> ActionResult`: if target provided, resolve it; check `world_state.focused_element` or target resolution; if no focus and no target, return `ActionResult.failed` with `repair_hints=["click_target_first", "focus_input"]`; else call `a.type_text(text, element)`
    - `async def press_key(key, world_state, *, timeout_ms=5000) -> ActionResult`: check focus exists (world_state.focused_element or browser_connected); call `a.press_key(key)`
    - `async def press_hotkey(keys, world_state, *, timeout_ms=5000) -> ActionResult`: call `a.press_hotkey(keys)` — hotkeys don't require focus target but need a resolved adapter
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 9.4 Implement window, observation, verification, and wait primitives in `friday/actions/primitives.py`
    - `async def switch_window(target, world_state, *, timeout_ms=10000) -> ActionResult`: resolve via `_execute_with_fallback("switch_window", ...)`, call `a.focus_window(target)`, verify evidence has `window_changed=True`
    - `async def observe(world_state) -> ActionResult`: check sources_used is non-empty; if empty, return FAILED with `repair_hints=["perception_unavailable"]`; if no semantic and no OCR/vision, return FAILED with `repair_hints=["perception_insufficient"]`; else return SUCCESS with world_state summary in metadata
    - `async def verify(condition, world_state) -> ActionResult`: use perception data to evaluate condition string (check `world_state.contains_text(condition)` or delegate to verifier pattern); return SUCCESS if met, FAILED with reason if not
    - `async def wait_for(condition, world_state, *, timeout_ms=30000, poll_interval_ms=500) -> ActionResult`: start timer; loop polling at `poll_interval_ms`; call observe/verify each iteration; if condition met return SUCCESS; if timeout exceeded return TIMEOUT
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 11.1, 11.2, 11.3_

- [x] 10. Checkpoint - Primitives module complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement Tool Registry integration
  - [x] 11.1 Create registration function in `friday/actions/primitives.py` or a new `friday/actions/register_primitives.py`
    - Define `register_primitives(registry: ToolRegistry)` function
    - Register `click` as `Tool(name="universal.click", capabilities=[ToolCapability.CLICK_ELEMENT], environment="any", priority=10, handler=click)`
    - Register `type_text` as `Tool(name="universal.type_text", capabilities=[ToolCapability.TYPE_TEXT], environment="any", priority=10, handler=type_text)`
    - Register `scroll` as `Tool(name="universal.scroll", capabilities=[ToolCapability.SCROLL], environment="any", priority=10, handler=scroll)`
    - Register `switch_window` as `Tool(name="universal.switch_window", capabilities=[ToolCapability.SWITCH_WINDOW], environment="any", priority=10, handler=switch_window)`
    - Register `verify` as `Tool(name="universal.verify", capabilities=[ToolCapability.VERIFY_RESULT], environment="any", priority=10, handler=verify)`
    - Priority 10 ensures universal primitives are preferred over environment-specific tools
    - _Requirements: 12.1, 12.2, 12.3_

  - [x]* 11.2 Write unit tests for registry integration in `tests/friday/actions/test_registry_integration.py`
    - Test `register_primitives` registers all expected tools
    - Test `find_tools(ToolCapability.CLICK_ELEMENT)` returns universal.click with highest priority
    - Test `find_tools(ToolCapability.TYPE_TEXT)` returns universal.type_text
    - Test `find_tools(ToolCapability.SWITCH_WINDOW)` returns universal.switch_window
    - Test `find_tools(ToolCapability.VERIFY_RESULT)` returns universal.verify
    - Test that handler references point to the correct primitive functions
    - _Requirements: 12.1, 12.2, 12.3_

- [x] 12. Write primitive unit tests and property tests
  - [x]* 12.1 Write unit tests for primitives in `tests/friday/actions/test_primitives.py`
    - Mock adapters and resolver
    - Test `click` happy path: adapter resolves and returns success
    - Test `click` re-routing: first adapter fails, second succeeds
    - Test `click` all fail: returns FAILED with adapters_attempted
    - Test `type_text` with no focus returns FAILED with repair hints
    - Test `press_hotkey` dispatches correct keys
    - Test `switch_window` returns evidence with window_changed
    - Test `observe` with empty WorldState returns FAILED
    - Test `verify` with matching condition returns SUCCESS
    - Test `verify` with unmet condition returns FAILED
    - Test `wait_for` returns SUCCESS when condition met before timeout
    - Test `wait_for` returns TIMEOUT when condition never met
    - Test timeout behavior: elapsed exceeds timeout_ms returns TIMEOUT
    - Test metadata includes source and adapter name on success
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.1, 9.6, 10.4, 11.1, 11.3_

  - [x]* 12.2 Write property-based tests in `tests/friday/actions/test_primitives_properties.py`
    - **Property 5: Semantic-First Execution** — For any Target resolving to semantic source, resolved element has `is_semantic == True`
    - **Validates: Requirements 3.3**
    - **Property 6: Source Recorded in Metadata** — Any completed invocation has `"source"` key in metadata
    - **Validates: Requirements 3.5**
    - **Property 7: Re-Routing on Adapter Failure** — If first adapter fails, system re-invokes with that adapter excluded
    - **Validates: Requirements 4.1, 4.2**
    - **Property 8: ActionResult Contract Invariant** — Return value is ActionResult with valid ActionStatus and non-empty action_type
    - **Validates: Requirements 5.1, 13.1**
    - **Property 9: Success Implies Evidence** — State-changing primitive returning SUCCESS has evidence.has_evidence == True
    - **Validates: Requirements 5.2**
    - **Property 10: Failure Implies Error Category and Repair Hints** — FAILED result has non-None error_category and at least one repair_hint
    - **Validates: Requirements 5.3**
    - **Property 11: Timing Fields Populated** — started_at > 0 and duration_ms >= 0
    - **Validates: Requirements 5.4**
    - **Property 12: Timeout Biconditional** — Status TIMEOUT iff duration exceeds timeout_ms
    - **Validates: Requirements 5.5, 5.6, 8.4**
    - **Property 13: Verify Condition Evaluation** — verify returns SUCCESS iff condition is satisfied
    - **Validates: Requirements 7.2, 7.3**
    - **Property 14: Wait Polling Terminates Correctly** — wait_for returns SUCCESS if condition met before timeout, TIMEOUT otherwise
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
    - **Property 15: Pointer Dispatch Correctness** — click dispatches exactly one click call to adapter
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**
    - **Property 16: Keyboard Dispatch Correctness** — type_text passes exact text, press_key passes exact key
    - **Validates: Requirements 10.1, 10.2, 10.3**
    - **Property 17: No Focus Means Keyboard Fails** — type_text with no focused_element and no adapter returns FAILED with "focus" hint
    - **Validates: Requirements 10.4**
    - **Property 18: Switch Window Success Evidence** — Successful switch_window has window_changed=True in evidence
    - **Validates: Requirements 11.1, 11.2**
    - **Property 19: Registry Discoverability** — Querying registry for CLICK_ELEMENT returns universal primitive
    - **Validates: Requirements 12.2**

- [x] 13. Update `friday/actions/adapters/__init__.py` with final re-exports
  - [x] 13.1 Finalize `friday/actions/adapters/__init__.py`
    - Re-export: `AdapterProtocol`, `BrowserAdapter`, `DesktopAdapter`, `DesktopActionsAdapter`, `VisionAdapter`, `AdapterResolver`
    - Ensure clean public API for the adapters package
    - _Requirements: 1.1, 2.1_

- [x] 14. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All adapters mock `pyautogui` and `BrowserController` in tests — no real I/O during test runs
- The 381 existing tests must continue passing — no existing files are modified
- Python 3.12, Windows-only target environment
- All primitives are async; sync callers can use `asyncio.run()` or the existing event loop pattern

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.2"] },
    { "id": 1, "tasks": ["1.2", "3.1", "4.1", "5.1", "6.1"] },
    { "id": 2, "tasks": ["3.2", "4.2", "5.2", "6.2"] },
    { "id": 3, "tasks": ["8.1"] },
    { "id": 4, "tasks": ["8.2", "8.3"] },
    { "id": 5, "tasks": ["9.1"] },
    { "id": 6, "tasks": ["9.2", "9.3", "9.4"] },
    { "id": 7, "tasks": ["11.1", "13.1"] },
    { "id": 8, "tasks": ["11.2", "12.1", "12.2"] }
  ]
}
```
