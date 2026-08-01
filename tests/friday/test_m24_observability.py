"""M24 — FailureLogSubscriber tests (observability as an event consumer).

Feature: m24-structured-failure-recovery-activation

Property 5: the subscriber emits exactly one structured log record per failure
event (verification.completed failure / recovery.proposed), carrying subsystem,
goal id, correlation id, logical time, and domain; level derives from severity;
it never raises into the bus.
"""

from __future__ import annotations

import logging
from typing import List

from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel
from friday.observability.failure_log import FailureLogSubscriber


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: List[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


def _attach_capture():
    logger = logging.getLogger("friday.observability.failure")
    logger.setLevel(logging.DEBUG)
    handler = _CaptureHandler()
    logger.addHandler(handler)
    return logger, handler


def test_p5_logs_failure_verdict(tmp_path):
    # Feature: m24-structured-failure-recovery-activation, Property 5:
    # a verification.completed FAILURE yields exactly one structured record.
    # Validates: Requirements 4.1, 4.2
    logger, handler = _attach_capture()
    try:
        kernel = CognitiveKernel(store_path=str(tmp_path / "obs.jsonl"))
        sub = FailureLogSubscriber(logger=logger)
        sub.attach(kernel)
        kernel.publish_event(make_event(
            event_type="verification.completed",
            source="verification",
            logical_time=int(kernel.health()["tick"]) + 1,
            payload={"goal_id": "g9", "satisfied": False, "requirement": "gather X"},
        ))
        assert sub.records_emitted == 1
        assert len(handler.records) == 1
        rec = handler.records[0]
        assert rec.levelno == logging.WARNING  # HIGH severity
        assert rec.goal_id == "g9"
        assert rec.failure_domain == "verification"
        assert rec.event_type == "verification.completed"
        assert rec.correlation_id  # non-empty
        assert isinstance(rec.logical_time, int)
    finally:
        logger.removeHandler(handler)


def test_p5_satisfied_verdict_is_not_logged(tmp_path):
    # Feature: m24-structured-failure-recovery-activation, Property 5:
    # a SATISFIED verdict is not a failure -> no record. Validates: Requirements 4.1
    logger, handler = _attach_capture()
    try:
        kernel = CognitiveKernel(store_path=str(tmp_path / "obs2.jsonl"))
        sub = FailureLogSubscriber(logger=logger)
        sub.attach(kernel)
        kernel.publish_event(make_event(
            event_type="verification.completed", source="verification",
            logical_time=int(kernel.health()["tick"]) + 1,
            payload={"goal_id": "g", "satisfied": True, "requirement": "r"},
        ))
        assert sub.records_emitted == 0
    finally:
        logger.removeHandler(handler)


def test_p5_logs_recovery_proposed(tmp_path):
    # Feature: m24-structured-failure-recovery-activation, Property 5:
    # a recovery.proposed event yields one record. Validates: Requirements 4.1, 4.2
    logger, handler = _attach_capture()
    try:
        kernel = CognitiveKernel(store_path=str(tmp_path / "obs3.jsonl"))
        sub = FailureLogSubscriber(logger=logger)
        sub.attach(kernel)
        kernel.publish_event(make_event(
            event_type="recovery.proposed", source="recovery",
            logical_time=int(kernel.health()["tick"]) + 1,
            payload={"goal_id": "g", "failure_class": "precondition", "level": 1},
        ))
        assert sub.records_emitted == 1
        assert handler.records[0].failure_class == "precondition"
    finally:
        logger.removeHandler(handler)


def test_p5_never_raises_on_malformed_event():
    # Feature: m24-structured-failure-recovery-activation, Property 5:
    # a malformed event must not raise into the bus. Validates: Requirements 4.3
    sub = FailureLogSubscriber()
    sub._on_event(object())  # no event_type/payload attributes
    sub._on_event(None)
    assert sub.records_emitted == 0
