"""Tests for friday.planner.requirements — Requirements Discovery."""

from unittest.mock import MagicMock
import pytest

from friday.planner.requirements import (
    Requirement,
    RequirementSet,
    RequirementsDiscovery,
)


class TestRequirement:
    def test_defaults(self):
        r = Requirement(description="Info must be gathered")
        assert r.satisfied is False
        assert r.blocking is True

    def test_requirement_set_completion(self):
        rs = RequirementSet(goal="test", requirements=[
            Requirement(description="A", satisfied=True),
            Requirement(description="B", satisfied=False),
        ])
        assert rs.all_satisfied is False
        assert len(rs.unsatisfied) == 1
        assert rs.completion_ratio == 0.5

    def test_all_satisfied(self):
        rs = RequirementSet(goal="test", requirements=[
            Requirement(description="A", satisfied=True),
            Requirement(description="B", satisfied=True),
        ])
        assert rs.all_satisfied is True
        assert rs.completion_ratio == 1.0

    def test_non_blocking_ignored(self):
        rs = RequirementSet(goal="test", requirements=[
            Requirement(description="A", satisfied=True, blocking=True),
            Requirement(description="B", satisfied=False, blocking=False),
        ])
        assert rs.all_satisfied is True  # B is non-blocking


class TestRequirementsDiscovery:
    def test_fallback_without_llm(self):
        """Without LLM, produces requirement-shaped fallback."""
        discovery = RequirementsDiscovery(model_router=None)
        result = discovery.discover("Research laptops and save a report")

        assert isinstance(result, RequirementSet)
        assert result.from_llm is False
        assert len(result.requirements) >= 1
        # Should detect info-gathering + content + file requirements
        descriptions = " ".join(r.description.lower() for r in result.requirements)
        assert "information" in descriptions or "gathered" in descriptions

    def test_fallback_detects_send(self):
        discovery = RequirementsDiscovery(model_router=None)
        result = discovery.discover("Email a summary to my boss")
        descriptions = " ".join(r.description.lower() for r in result.requirements)
        assert "deliver" in descriptions or "recipient" in descriptions

    def test_llm_decomposition(self):
        """With LLM, parses requirement array."""
        router = MagicMock()
        async def fake_complete(prompt, **kwargs):
            from friday.models.router import ModelResponse
            return ModelResponse(
                text='["Information about X must be gathered", "A report must be created", "Report must be saved"]',
                model_used="m", provider="p",
            )
        router.complete = fake_complete

        discovery = RequirementsDiscovery(model_router=router)
        result = discovery.discover("Create a report about X")

        assert result.from_llm is True
        assert len(result.requirements) == 3
        assert "gathered" in result.requirements[0].description.lower()

    def test_llm_malformed_falls_back(self):
        """Malformed LLM output falls back gracefully."""
        router = MagicMock()
        async def fake_complete(prompt, **kwargs):
            from friday.models.router import ModelResponse
            return ModelResponse(text="not json at all", model_used="m", provider="p")
        router.complete = fake_complete

        discovery = RequirementsDiscovery(model_router=router)
        result = discovery.discover("Do something")
        # Falls back to generic requirements
        assert result.from_llm is False
        assert len(result.requirements) >= 1
