"""Tests for focused search query extraction + spreadsheet output.

Covers the owner-reported bug: FRIDAY searched the WHOLE goal string
("research best gaming laptop and make a spreadsheet") into the search
engine instead of searching the topic ("best gaming laptop"). Also proves
spreadsheet goals now produce real tabular files.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from friday.planner.query_extractor import extract_search_query
from friday.actions.file_tool import FileTool


class TestQueryExtraction:
    def test_strips_research_verb_and_output_clause(self):
        q = extract_search_query("research best gaming laptop and make a spreadsheet")
        assert q == "best gaming laptop"

    def test_strips_find_and_save_clause(self):
        q = extract_search_query("find the top 5 ML papers and save to a file")
        assert "top 5 ML papers" in q
        assert "save" not in q.lower()

    def test_strips_lookup_and_email_clause(self):
        q = extract_search_query("look up France's GDP and email it to my boss")
        assert "france's gdp" in q.lower()
        assert "email" not in q.lower()

    def test_plain_topic_unchanged(self):
        q = extract_search_query("weather in Tokyo")
        assert q == "weather in Tokyo"

    def test_create_clause_dropped(self):
        q = extract_search_query("research electric cars and create a comparison report")
        assert "electric cars" in q.lower()
        assert "report" not in q.lower()

    def test_never_empty(self):
        # Pathological: only a verb
        q = extract_search_query("research")
        assert q.strip() != ""

    def test_whole_sentence_not_used_as_query(self):
        goal = "research best gaming laptop and make a spreadsheet"
        q = extract_search_query(goal)
        assert q != goal  # the bug was q == goal
        assert "spreadsheet" not in q.lower()


class TestPlannerUsesFocusedQuery:
    def test_fallback_search_target_is_focused(self):
        from friday.planner.operator_planner import OperatorPlanner
        from friday.tools.registry import build_default_registry, ToolCapability

        planner = OperatorPlanner(registry=build_default_registry(), model_router=None)
        plan = planner.plan("research best gaming laptop and make a spreadsheet")

        search_steps = [s for s in plan.steps if s.capability == ToolCapability.SEARCH_WEB]
        assert search_steps, "expected a search step"
        # The search target must be the topic, not the whole instruction.
        assert "spreadsheet" not in search_steps[0].target.lower()
        assert "best gaming laptop" in search_steps[0].target.lower()


class TestSpreadsheetOutput:
    def test_csv_is_real_tabular_file(self, tmp_path):
        tool = FileTool()
        path = tmp_path / "laptops.csv"
        content = "Model | Price | GPU\nAcer Nitro | 75000 | RTX 4050\nLenovo LOQ | 80000 | RTX 4060"
        result = tool.create_file(str(path), content)
        assert result.is_success
        assert path.exists()

        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["Model", "Price", "GPU"]
        assert rows[1][0] == "Acer Nitro"
        assert len(rows) == 3

    def test_comma_separated_content_parses(self, tmp_path):
        tool = FileTool()
        path = tmp_path / "data.csv"
        result = tool.create_file(str(path), "a,b,c\n1,2,3")
        assert result.is_success
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["a", "b", "c"]
        assert rows[1] == ["1", "2", "3"]

    def test_markdown_separator_row_skipped(self, tmp_path):
        tool = FileTool()
        path = tmp_path / "t.csv"
        content = "| Name | Score |\n|------|-------|\n| Alice | 90 |"
        tool.create_file(str(path), content)
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        # separator row must NOT appear
        assert rows[0] == ["Name", "Score"]
        assert rows[1] == ["Alice", "90"]
        assert len(rows) == 2


class TestSpreadsheetFilenameInference:
    def test_spreadsheet_goal_infers_csv(self):
        from friday.executor import GoalExecutor, ExecutionContext
        ex = GoalExecutor(model_router=None, browser_controller=None)
        ctx = ExecutionContext(goal="research best gaming laptop and make a spreadsheet")
        name = ex._infer_filename("make a spreadsheet", ctx)
        assert name.endswith(".csv")
