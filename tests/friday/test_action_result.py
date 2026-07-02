"""Tests for friday.actions.result — ActionResult contract."""

import time
import pytest

from friday.actions.result import (
    ActionEvidence,
    ActionResult,
    ActionStatus,
    ActionTimer,
)


class TestActionResult:
    """Test ActionResult factory methods and properties."""

    def test_success_factory(self):
        """ActionResult.success creates proper success result."""
        evidence = ActionEvidence(
            before_hash="aaa",
            after_hash="bbb",
            state_changed=True,
            url_changed=True,
        )
        result = ActionResult.success(
            action="navigate",
            target="https://google.com",
            message="Navigated to Google",
            evidence=evidence,
        )

        assert result.status == ActionStatus.SUCCESS
        assert result.is_success is True
        assert result.verified is True
        assert result.action_type == "navigate"
        assert result.target == "https://google.com"
        assert result.error is None

    def test_success_without_evidence_is_unverified(self):
        """Success without evidence is not verified."""
        result = ActionResult.success(
            action="click",
            target="button",
        )

        assert result.is_success is True
        assert result.verified is False  # No evidence!

    def test_failed_factory(self):
        """ActionResult.failed creates proper failure result."""
        result = ActionResult.failed(
            action="click",
            error="Element not found",
            target="Submit button",
            error_category="element_not_found",
            repair_hints=["scroll_down", "wait_for_element"],
        )

        assert result.status == ActionStatus.FAILED
        assert result.is_success is False
        assert result.verified is False
        assert result.error == "Element not found"
        assert result.error_category == "element_not_found"
        assert "scroll_down" in result.repair_hints

    def test_timeout_factory(self):
        """ActionResult.timeout creates proper timeout result."""
        result = ActionResult.timeout(
            action="wait_for_element",
            target="loading spinner",
            duration_ms=5000.0,
        )

        assert result.status == ActionStatus.TIMEOUT
        assert result.is_success is False
        assert result.duration_ms == 5000.0
        assert "retry" in result.repair_hints

    def test_blocked_factory(self):
        """ActionResult.blocked creates proper blocked result."""
        result = ActionResult.blocked(
            action="fill_form",
            reason="Login dialog appeared",
            target="email field",
        )

        assert result.status == ActionStatus.BLOCKED
        assert result.is_success is False
        assert "Login dialog" in result.message

    def test_needs_repair_property(self):
        """needs_repair correctly identifies repairable failures."""
        result = ActionResult(
            status=ActionStatus.NEEDS_REPAIR,
            action_type="click",
            target="button",
            error="State unchanged after click",
            repair_hints=["retry_click", "alternative_element"],
        )

        assert result.needs_repair is True
        assert result.is_success is False

    def test_to_dict_serialization(self):
        """ActionResult serializes to dict for API/logging."""
        evidence = ActionEvidence(
            before_hash="hash1",
            after_hash="hash2",
            state_changed=True,
        )
        result = ActionResult.success(
            action="type",
            target="search box",
            evidence=evidence,
        )
        d = result.to_dict()

        assert d["status"] == "success"
        assert d["action_type"] == "type"
        assert d["target"] == "search box"
        assert d["success"] is True
        assert d["verified"] is True
        assert d["evidence"]["state_changed"] is True
        assert d["evidence"]["has_evidence"] is True


class TestActionEvidence:
    """Test ActionEvidence properties."""

    def test_empty_evidence_has_no_evidence(self):
        """Empty evidence reports no evidence."""
        evidence = ActionEvidence()
        assert evidence.has_evidence is False

    def test_state_changed_is_evidence(self):
        """State change counts as evidence."""
        evidence = ActionEvidence(state_changed=True)
        assert evidence.has_evidence is True

    def test_hash_difference_is_evidence(self):
        """Different before/after hashes count as evidence."""
        evidence = ActionEvidence(before_hash="aaa", after_hash="bbb")
        assert evidence.has_evidence is True

    def test_same_hashes_no_evidence(self):
        """Same before/after hashes with no other signals = no evidence."""
        evidence = ActionEvidence(before_hash="aaa", after_hash="aaa")
        assert evidence.has_evidence is False

    def test_text_appeared_is_evidence(self):
        """Text appearing counts as evidence."""
        evidence = ActionEvidence(text_appeared="Success")
        assert evidence.has_evidence is True

    def test_url_changed_is_evidence(self):
        """URL change counts as evidence."""
        evidence = ActionEvidence(url_changed=True)
        assert evidence.has_evidence is True


class TestActionTimer:
    """Test ActionTimer context manager."""

    def test_timer_measures_duration(self):
        """Timer correctly measures elapsed time."""
        with ActionTimer() as timer:
            time.sleep(0.01)  # 10ms minimum

        assert timer.started_at > 0
        assert timer.completed_at > timer.started_at
        assert timer.duration_ms >= 10  # At least 10ms

    def test_timer_without_sleep(self):
        """Timer works even for instant operations."""
        with ActionTimer() as timer:
            pass

        assert timer.duration_ms >= 0
        assert timer.completed_at >= timer.started_at
