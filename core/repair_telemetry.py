"""Repair telemetry logging system.

Logs every repair attempt to logs/repair.log for analysis and debugging.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional


REPAIR_LOG_PATH = Path("logs/repair.log")


def log_repair_attempt(
    intent: str,
    diagnosis: Dict[str, bool],
    strategy: str,
    success: bool,
    state_hash_before: str,
    state_hash_after: str,
    action_type: str = "",
    error_message: str = ""
) -> None:
    """Log a repair attempt to telemetry.
    
    Args:
        intent: User intent/goal
        diagnosis: Failure diagnosis dict
        strategy: Repair strategy name
        success: Whether repair succeeded
        state_hash_before: State hash before repair
        state_hash_after: State hash after repair
        action_type: Type of action being repaired
        error_message: Error message if failed
    """
    # Ensure logs directory exists
    REPAIR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Build log entry
    timestamp = time.time()
    
    # Extract detected failures from diagnosis
    detected_failures = [key for key, value in diagnosis.items() if value]
    
    log_entry = {
        "timestamp": timestamp,
        "intent": intent,
        "diagnosis": detected_failures,
        "strategy": strategy,
        "success": success,
        "state_hash_before": state_hash_before,
        "state_hash_after": state_hash_after,
        "action_type": action_type,
        "error_message": error_message,
    }
    
    # Append to log file
    try:
        with open(REPAIR_LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass


def get_repair_stats() -> Dict[str, any]:
    """Get repair statistics from log.
    
    Returns:
        Dict with repair statistics
    """
    if not REPAIR_LOG_PATH.exists():
        return {
            "total_repairs": 0,
            "successful_repairs": 0,
            "failed_repairs": 0,
            "strategies_used": {},
        }
    
    total = 0
    successful = 0
    failed = 0
    strategies = {}
    
    try:
        with open(REPAIR_LOG_PATH, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    total += 1
                    
                    if entry.get("success"):
                        successful += 1
                    else:
                        failed += 1
                    
                    strategy = entry.get("strategy", "unknown")
                    strategies[strategy] = strategies.get(strategy, 0) + 1
                    
                except Exception:
                    continue
    except Exception:
        pass
    
    return {
        "total_repairs": total,
        "successful_repairs": successful,
        "failed_repairs": failed,
        "success_rate": successful / total if total > 0 else 0.0,
        "strategies_used": strategies,
    }


def clear_repair_log() -> None:
    """Clear the repair log file."""
    if REPAIR_LOG_PATH.exists():
        REPAIR_LOG_PATH.unlink()
