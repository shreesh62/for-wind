"""Self-repair system for cognitive loop.

Compares before/after snapshots to identify missing conditions,
modifies task graphs, and triggers retries with adapted strategies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from awareness.perception_snapshot import PerceptionSnapshot
from automation.task_graph import TaskGraph, TaskNode, TaskStatus
from automation.semantic_actions import Action, ActionType, create_wait_action, create_dismiss_dialog_action


@dataclass
class RepairStrategy:
    """A repair strategy for a failed action."""
    
    name: str
    description: str
    actions: List[Action]
    confidence: float  # 0.0-1.0


class SelfRepairEngine:
    """Analyzes failures and generates repair strategies using diagnostic engine."""
    
    def __init__(self, automation_services=None):
        """Initialize self-repair engine.
        
        Args:
            automation_services: AutomationServices instance for executing repairs
        """
        self.automation = automation_services
        self.repair_history = []  # Track repairs for learning
    
    def attempt_repair(
        self,
        before: PerceptionSnapshot,
        after: PerceptionSnapshot,
        action,
        automation_services
    ) -> bool:
        """Attempt to repair a failed action using diagnostic-driven strategies.
        
        Args:
            before: Snapshot before action
            after: Snapshot after action
            action: Action that failed
            automation_services: AutomationServices for executing repairs
            
        Returns:
            True if repair was successful, False otherwise
        """
        from core.repair_diagnostics import diagnose_failure
        from core.repair_strategies import get_repair_strategies, describe_failure
        
        # Diagnose the failure
        diagnosis = diagnose_failure(
            before,
            after,
            action,
            expected_target=getattr(action, 'target', None)
        )
        
        # Get repair strategies
        strategies = get_repair_strategies(diagnosis)
        
        if not strategies:
            # No strategies available
            return False
        
        # Try each strategy in priority order
        for strategy in strategies:
            try:
                success = self.execute_strategy(strategy.name, action, after, automation_services)
                
                if success:
                    # 3️⃣ REPAIR TELEMETRY: Log successful repair
                    from core.repair_telemetry import log_repair_attempt
                    
                    log_repair_attempt(
                        intent=getattr(action, 'type', 'unknown'),
                        diagnosis=diagnosis,
                        strategy=strategy.name,
                        success=True,
                        state_hash_before=before.screen_hash,
                        state_hash_after=after.screen_hash,
                        action_type=getattr(action, 'type', 'unknown'),
                    )
                    
                    # Record successful repair
                    self.repair_history.append({
                        "diagnosis": diagnosis,
                        "strategy": strategy.name,
                        "action_type": getattr(action, 'type', 'unknown'),
                        "success": True,
                    })
                    return True
                    
            except Exception:
                continue
        
        # 3️⃣ REPAIR TELEMETRY: Log failed repair
        from core.repair_telemetry import log_repair_attempt
        
        # Log the last attempted strategy
        if strategies:
            log_repair_attempt(
                intent=getattr(action, 'type', 'unknown'),
                diagnosis=diagnosis,
                strategy=strategies[-1].name,
                success=False,
                state_hash_before=before.screen_hash,
                state_hash_after=after.screen_hash,
                action_type=getattr(action, 'type', 'unknown'),
                error_message="All repair strategies exhausted"
            )
        
        # All strategies failed
        return False
    
    def analyze_failure(
        self,
        failed_task: TaskNode,
        before_snapshot: PerceptionSnapshot,
        after_snapshot: PerceptionSnapshot
    ) -> Optional[RepairStrategy]:
        """Analyze a failed task and generate repair strategy (legacy interface).
        
        Args:
            failed_task: The task that failed
            before_snapshot: Snapshot before action
            after_snapshot: Snapshot after action
            
        Returns:
            RepairStrategy or None if no repair possible
        """
        from core.repair_diagnostics import diagnose_failure
        from core.repair_strategies import get_repair_strategies
        
        action = failed_task.action
        
        # Diagnose the failure
        diagnosis = diagnose_failure(
            before_snapshot,
            after_snapshot,
            action,
            expected_target=getattr(action, 'target', None)
        )
        
        # Get repair strategies
        strategies = get_repair_strategies(diagnosis)
        
        if strategies:
            # Return first strategy as RepairStrategy for compatibility
            strategy = strategies[0]
            return RepairStrategy(
                name=strategy.name,
                description=strategy.description,
                actions=self._strategy_to_actions(strategy.name, action)
            )
        
        return None
    
    def _detect_missing_conditions(
        self,
        before: PerceptionSnapshot,
        after: PerceptionSnapshot,
        action: Action
    ) -> List[str]:
        """Detect what conditions are missing for action success.
        
        Args:
            before: Snapshot before action
            after: Snapshot after action
            action: Action that was executed
            
        Returns:
            List of missing condition identifiers
        """
        conditions = []
        
        # Check if state changed at all
        if before.screen_hash == after.screen_hash:
            conditions.append("state_unchanged")
        
        # Check for blocking dialogs
        if after.browser.has_error or after.browser.has_consent_dialog:
            conditions.append("dialog_blocking")
        
        # Check if target element exists
        if action.target:
            elem = after.find_element_by_text(action.target, fuzzy=True)
            if not elem:
                conditions.append("element_not_found")
        
        # Check if focus was lost
        if action.type in (ActionType.TYPE_TEXT, ActionType.CLICK_ELEMENT):
            focused = after.find_focused_element()
            if not focused:
                conditions.append("focus_lost")
        
        # Check for login requirement
        if after.browser.has_login_form and not before.browser.has_login_form:
            conditions.append("login_required")
        
        return conditions
    
    def _repair_element_not_found(
        self,
        action: Action,
        snapshot: PerceptionSnapshot
    ) -> RepairStrategy:
        """Repair strategy for element not found.
        
        Args:
            action: Original action
            snapshot: Current snapshot
            
        Returns:
            RepairStrategy
        """
        # Strategy: Wait for UI to settle, then retry with fuzzy matching
        return RepairStrategy(
            name="wait_and_retry",
            description="Wait for UI to settle and retry with broader search",
            actions=[
                create_wait_action("ui_settled", timeout=2.0),
                action  # Retry original action
            ],
            confidence=0.6
        )
    
    def _repair_dialog_blocking(
        self,
        action: Action,
        snapshot: PerceptionSnapshot
    ) -> RepairStrategy:
        """Repair strategy for blocking dialog.
        
        Args:
            action: Original action
            snapshot: Current snapshot
            
        Returns:
            RepairStrategy
        """
        # Strategy: Dismiss dialog, then retry
        return RepairStrategy(
            name="dismiss_and_retry",
            description="Dismiss blocking dialog and retry action",
            actions=[
                create_dismiss_dialog_action(),
                create_wait_action("dialog_dismissed", timeout=1.0),
                action  # Retry original action
            ],
            confidence=0.8
        )
    
    def _repair_state_unchanged(
        self,
        action: Action,
        snapshot: PerceptionSnapshot
    ) -> RepairStrategy:
        """Repair strategy for unchanged state.
        
        Args:
            action: Original action
            snapshot: Current snapshot
            
        Returns:
            RepairStrategy
        """
        # Strategy: Wait longer and retry
        return RepairStrategy(
            name="wait_longer",
            description="Wait for state change and retry",
            actions=[
                create_wait_action("state_change", timeout=3.0),
                action  # Retry original action
            ],
            confidence=0.5
        )
    
    def _repair_focus_lost(
        self,
        action: Action,
        snapshot: PerceptionSnapshot
    ) -> RepairStrategy:
        """Repair strategy for lost focus.
        
        Args:
            action: Original action
            snapshot: Current snapshot
            
        Returns:
            RepairStrategy
        """
        # Strategy: Re-focus element and retry
        from automation.semantic_actions import create_click_element_action
        
        actions = []
        if action.target:
            # Click to focus, then retry
            actions.append(create_click_element_action(action.target))
            actions.append(create_wait_action("focus_gained", timeout=1.0))
        
        actions.append(action)  # Retry original action
        
        return RepairStrategy(
            name="refocus_and_retry",
            description="Re-establish focus and retry action",
            actions=actions,
            confidence=0.7
        )
    
    def execute_strategy(
        self,
        strategy_name: str,
        action,
        snapshot: PerceptionSnapshot,
        automation_services
    ) -> bool:
        """Execute a specific repair strategy.
        
        Args:
            strategy_name: Name of strategy to execute
            action: Original action that failed
            snapshot: Current perception snapshot
            automation_services: AutomationServices instance
            
        Returns:
            True if strategy executed successfully
        """
        try:
            if strategy_name == "dismiss_dialog":
                return self._execute_dismiss_dialog(automation_services, snapshot)
            
            elif strategy_name == "bring_browser_front":
                return self._execute_bring_browser_front(automation_services)
            
            elif strategy_name == "refocus_window":
                return self._execute_refocus_window(automation_services, snapshot)
            
            elif strategy_name == "retry_navigation":
                return self._execute_retry_navigation(automation_services, action)
            
            elif strategy_name == "refocus_and_retry":
                return self._execute_refocus_and_retry(automation_services, action, snapshot)
            
            elif strategy_name == "expand_search_scope":
                # This is handled by element resolver, just return True to retry
                return True
            
            elif strategy_name == "retype":
                return self._execute_retype(automation_services, action)
            
            elif strategy_name == "reexecute_with_delay":
                import time
                time.sleep(1.0)
                return True
            
            elif strategy_name == "wait_for_network":
                import time
                time.sleep(2.0)
                return True
            
        except Exception:
            return False
        
        return False
    
    def _execute_dismiss_dialog(self, automation, snapshot) -> bool:
        """Dismiss blocking dialog."""
        try:
            # Look for OK, Close, Cancel buttons
            for keyword in ["ok", "close", "cancel", "dismiss"]:
                elem = snapshot.find_element_by_text(keyword, fuzzy=True)
                if elem and elem.bounding_box:
                    center = elem.center()
                    if center:
                        result = automation.click(center[0], center[1])
                        return result.success
            return False
        except Exception:
            return False
    
    def _execute_bring_browser_front(self, automation) -> bool:
        """Bring Chrome to foreground."""
        try:
            result = automation.focus_window("Chrome")
            return result.success
        except Exception:
            return False
    
    def _execute_refocus_window(self, automation, snapshot) -> bool:
        """Refocus correct window."""
        try:
            # Focus the window that was active before
            if snapshot.active_window_title:
                result = automation.focus_window(snapshot.active_window_title)
                return result.success
            return False
        except Exception:
            return False
    
    def _execute_retry_navigation(self, automation, action) -> bool:
        """Retry navigation action."""
        try:
            url = getattr(action, 'url', None) or getattr(action, 'target', None)
            if url:
                result = automation.open_website(url)
                return result.success
            return False
        except Exception:
            return False
    
    def _execute_refocus_and_retry(self, automation, action, snapshot) -> bool:
        """Refocus element and retry."""
        try:
            target = getattr(action, 'target', None)
            if target:
                elem = snapshot.find_element_by_text(target, fuzzy=True)
                if elem and elem.bounding_box:
                    center = elem.center()
                    if center:
                        # Click to focus
                        automation.click(center[0], center[1])
                        return True
            return False
        except Exception:
            return False
    
    def _execute_retype(self, automation, action) -> bool:
        """Retype text."""
        try:
            text = getattr(action, 'text_content', None)
            if text:
                result = automation.type_text(text)
                return result.success
            return False
        except Exception:
            return False
    
    def _strategy_to_actions(self, strategy_name: str, action) -> List[Action]:
        """Convert strategy name to list of actions."""
        from automation.semantic_actions import (
            create_wait_action,
            create_dismiss_dialog_action,
            create_focus_window_action,
        )
        
        if strategy_name == "dismiss_dialog":
            return [
                create_dismiss_dialog_action(),
                create_wait_action("dialog_dismissed", timeout=1.0),
                action
            ]
        elif strategy_name == "reexecute_with_delay":
            return [
                create_wait_action("ui_settled", timeout=1.0),
                action
            ]
        else:
            return [action]
    
    def apply_repair_to_graph(
        self,
        graph: TaskGraph,
        failed_task: TaskNode,
        strategy: RepairStrategy
    ) -> None:
        """Apply repair strategy to task graph.
        
        Modifies the graph by inserting repair actions before retry.
        
        Args:
            graph: Task graph to modify
            failed_task: Failed task node
            strategy: Repair strategy to apply
        """
        # Find index of failed task
        failed_idx = None
        for i, node in enumerate(graph.nodes):
            if node.task_id == failed_task.task_id:
                failed_idx = i
                break
        
        if failed_idx is None:
            return
        
        # Insert repair actions before failed task
        base_id = failed_task.task_id
        prev_id = base_id
        
        for i, repair_action in enumerate(strategy.actions[:-1]):  # All except retry
            repair_id = f"{base_id}_repair_{i}"
            repair_node = TaskNode(
                task_id=repair_id,
                action=repair_action,
                status=TaskStatus.PENDING
            )
            
            # Insert after failed task
            graph.nodes.insert(failed_idx + i + 1, repair_node)
            prev_id = repair_id
        
        # Reset failed task for retry
        failed_task.status = TaskStatus.PENDING
        failed_task.error_message = None
        
        # Update dependencies to ensure repair actions run first
        if prev_id != base_id:
            failed_task.dependencies.add(prev_id)


def create_self_repair_engine() -> SelfRepairEngine:
    """Create a self-repair engine instance.
    
    Returns:
        SelfRepairEngine instance
    """
    return SelfRepairEngine()
