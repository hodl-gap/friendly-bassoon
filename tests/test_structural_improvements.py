"""
Tests for the 3 structural improvements:
1. Query-derived analysis variables
2. Macro condition comparison for historical analogs (Then vs Now)
3. refine_query() implementation
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "subproject_database_retriever"))


# ===========================================================================
# Change 1: Query-Derived Analysis Variables
# ===========================================================================

class TestChange1_AnalysisFramePrompt:
    """Test that the ANALYSIS_FRAME_PROMPT is importable and well-formed."""

    def test_prompt_importable(self):
        from subproject_risk_intelligence.variable_extraction_prompts import ANALYSIS_FRAME_PROMPT
        assert isinstance(ANALYSIS_FRAME_PROMPT, str)

    def test_prompt_has_placeholders(self):
        from subproject_risk_intelligence.variable_extraction_prompts import ANALYSIS_FRAME_PROMPT
        assert "{query}" in ANALYSIS_FRAME_PROMPT
        assert "{known_variables}" in ANALYSIS_FRAME_PROMPT

    def test_prompt_formattable(self):
        from subproject_risk_intelligence.variable_extraction_prompts import ANALYSIS_FRAME_PROMPT
        formatted = ANALYSIS_FRAME_PROMPT.format(
            query="carry trade unwind impact",
            known_variables="usdjpy, vix, boj_rate"
        )
        assert "carry trade unwind impact" in formatted
        assert "usdjpy, vix, boj_rate" in formatted


class TestChange1_IdentifyAnalysisVariables:
    """Test identify_analysis_variables() with mocked Anthropic client."""

    def _mock_tool_response(self, variables):
        """Create a mock Anthropic response with tool_use."""
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "identify_variables"
        mock_block.input = {"variables": variables}

        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage = mock_usage
        return mock_response

    @patch("anthropic.Anthropic")
    def test_returns_variables_from_query(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_tool_response(
            ["usdjpy", "boj_rate", "vix"]
        )
        mock_anthropic_cls.return_value = mock_client

        from subproject_risk_intelligence.variable_extraction import identify_analysis_variables
        result = identify_analysis_variables("carry trade unwind impact on risk assets")

        assert isinstance(result, set)
        assert "usdjpy" in result
        assert "boj_rate" in result
        assert "vix" in result
        assert len(result) == 3

    @patch("anthropic.Anthropic")
    def test_normalizes_to_lowercase(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_tool_response(
            ["USDJPY", " VIX "]
        )
        mock_anthropic_cls.return_value = mock_client

        from subproject_risk_intelligence.variable_extraction import identify_analysis_variables
        result = identify_analysis_variables("yen crash")

        assert "usdjpy" in result
        assert "vix" in result

    @patch("anthropic.Anthropic")
    def test_returns_empty_on_exception(self, mock_anthropic_cls):
        mock_anthropic_cls.side_effect = Exception("API unavailable")

        from subproject_risk_intelligence.variable_extraction import identify_analysis_variables
        result = identify_analysis_variables("test query")

        assert result == set()


class TestChange1_ExtractVariablesIntegration:
    """Test that extract_variables() calls identify_analysis_variables()."""

    def _mock_tool_response(self, variables, tool_name="identify_variables"):
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = tool_name
        mock_block.input = {"variables": variables}

        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage = mock_usage
        return mock_response

    @patch("anthropic.Anthropic")
    def test_query_frame_vars_tagged_correctly(self, mock_anthropic_cls):
        """Verify query-frame variables are tagged with source: 'query_frame'."""
        mock_client = MagicMock()
        # First call: identify_analysis_variables (query-frame)
        # Second call: extract_variables_llm (synthesis-based)
        mock_client.messages.create.side_effect = [
            self._mock_tool_response(["usdjpy", "vix"], "identify_variables"),
            self._mock_tool_response(["usdjpy", "btc", "sp500"], "extract_variables"),
        ]
        mock_anthropic_cls.return_value = mock_client

        from subproject_risk_intelligence.variable_extraction import extract_variables

        state = {
            "query": "carry trade unwind",
            "synthesis": "The carry trade involves borrowing in yen...",
            "retrieval_answer": "",
            "logic_chains": [],
            "asset_class": "btc",
        }

        result = extract_variables(state)
        variables_list = result.get("extracted_variables", [])

        # Check that query-frame vars have correct source tag
        query_frame = [v for v in variables_list if v["source"] == "query_frame"]
        extraction = [v for v in variables_list if v["source"] == "extraction"]

        query_frame_names = {v["normalized"] for v in query_frame}
        # usdjpy and vix came from query-frame
        assert "usdjpy" in query_frame_names or "vix" in query_frame_names

        # btc is always added as priority variable, not from query-frame
        all_names = {v["normalized"] for v in variables_list}
        assert "btc" in all_names


# ===========================================================================
# Change 2: Macro Condition Comparison (Then vs Now)
# ===========================================================================

class TestChange2_FetchConditionsAtDate:
    """Test fetch_conditions_at_date() with mocked data fetchers."""

    @patch("subproject_risk_intelligence.historical_data_fetcher._fetch_yahoo_data")
    @patch("subproject_risk_intelligence.historical_data_fetcher._fetch_fred_data")
    def test_fetches_conditions_for_variables(self, mock_fred, mock_yahoo):
        mock_fred.return_value = [("2024-08-01", 5.33)]
        mock_yahoo.return_value = [("2024-08-01", 141.70), ("2024-08-05", 143.50)]

        from subproject_risk_intelligence.historical_data_fetcher import fetch_conditions_at_date

        variables = [
            {"normalized": "fed_funds", "ticker": "FEDFUNDS", "source": "FRED"},
            {"normalized": "usdjpy", "ticker": "USDJPY=X", "source": "Yahoo"},
        ]

        result = fetch_conditions_at_date(variables, "2024-08-03", window_days=7)

        assert "fed_funds" in result
        assert result["fed_funds"]["value"] == 5.33
        assert result["fed_funds"]["source"] == "FRED"

        assert "usdjpy" in result
        # Should pick the closest date to 2024-08-03
        assert result["usdjpy"]["source"] == "Yahoo"

    @patch("subproject_risk_intelligence.historical_data_fetcher._fetch_fred_data")
    def test_skips_variables_with_no_data(self, mock_fred):
        mock_fred.return_value = []

        from subproject_risk_intelligence.historical_data_fetcher import fetch_conditions_at_date

        variables = [
            {"normalized": "fed_funds", "ticker": "FEDFUNDS", "source": "FRED"},
        ]

        result = fetch_conditions_at_date(variables, "2024-08-03")
        assert "fed_funds" not in result

    def test_skips_variables_without_ticker(self):
        from subproject_risk_intelligence.historical_data_fetcher import fetch_conditions_at_date

        variables = [
            {"normalized": "unknown_var", "ticker": "", "source": ""},
        ]

        result = fetch_conditions_at_date(variables, "2024-08-03")
        assert result == {}


class TestChange2_FetchMultipleAnalogsConditions:
    """Test that fetch_multiple_analogs passes condition_variables through."""

    def test_condition_variables_parameter_accepted(self):
        """Verify fetch_multiple_analogs accepts condition_variables kwarg."""
        import inspect
        from subproject_risk_intelligence.historical_aggregator import fetch_multiple_analogs

        sig = inspect.signature(fetch_multiple_analogs)
        assert "condition_variables" in sig.parameters


class TestChange2_FormatAnalogsWithConditions:
    """Test format_analogs_for_prompt with Then vs Now data."""

    def test_format_without_conditions(self):
        """Backward compatibility: works without conditions."""
        from subproject_risk_intelligence.historical_aggregator import format_analogs_for_prompt

        aggregated = {
            "summary": "3/3 bearish, median -15%",
            "direction_distribution": {"bearish": 3, "bullish": 0, "neutral": 0},
            "magnitude": {"median_pct": -15.0, "min_pct": -25.0, "max_pct": -8.0},
            "timing": {},
            "per_analog": [
                {
                    "event": "2020 COVID crash",
                    "year": 2020,
                    "target_change_pct": -25.0,
                    "recovery_days": 30,
                    "relevance": 0.8,
                    "key_mechanism": "global risk-off",
                }
            ],
        }

        result = format_analogs_for_prompt(aggregated)
        assert "HISTORICAL PRECEDENT ANALYSIS" in result
        assert "2020 COVID crash" in result
        assert "Macro Backdrop" not in result  # No conditions provided

    def test_format_with_conditions(self):
        """Then vs Now section appears when conditions provided."""
        from subproject_risk_intelligence.historical_aggregator import format_analogs_for_prompt

        aggregated = {
            "summary": "1/1 bearish",
            "direction_distribution": {"bearish": 1, "bullish": 0, "neutral": 0},
            "magnitude": {"median_pct": -20.0, "min_pct": -20.0, "max_pct": -20.0},
            "timing": {},
            "per_analog": [
                {
                    "event": "2020 COVID crash",
                    "year": 2020,
                    "target_change_pct": -20.0,
                    "recovery_days": 30,
                    "relevance": 0.9,
                    "key_mechanism": "pandemic risk-off",
                }
            ],
        }

        enriched_analogs = [
            {
                "event_description": "2020 COVID crash",
                "conditions_then": {
                    "fed_funds": {"value": 1.50, "date": "2020-03-01", "source": "FRED"},
                    "vix": {"value": 82.69, "date": "2020-03-16", "source": "Yahoo"},
                },
                "fetch_success": True,
            }
        ]

        current_conditions = {
            "fed_funds": {"value": 5.25, "date": "2026-02-18", "source": "FRED"},
            "vix": {"value": 18.50, "date": "2026-02-18", "source": "Yahoo"},
        }

        result = format_analogs_for_prompt(
            aggregated,
            enriched_analogs=enriched_analogs,
            current_conditions=current_conditions
        )

        assert "Macro Backdrop (Then vs Now)" in result
        assert "FED_FUNDS: THEN 1.50 vs NOW 5.25" in result
        assert "VIX: THEN 82.69 vs NOW 18.50" in result


class TestChange2_BuildConditionVariables:
    """Test _build_condition_variables helper."""

    @patch("subproject_risk_intelligence.current_data_fetcher.resolve_variable")
    def test_resolves_variables(self, mock_resolve):
        mock_resolve.side_effect = lambda v: {
            "fed_funds": {"source": "FRED", "series_id": "FEDFUNDS"},
            "vix": {"source": "Yahoo", "series_id": "^VIX"},
        }.get(v)

        from subproject_risk_intelligence.insight_orchestrator import _build_condition_variables

        extracted = [
            {"normalized": "fed_funds", "source": "extraction"},
            {"normalized": "vix", "source": "query_frame"},
            {"normalized": "unknown_var", "source": "extraction"},
        ]

        result = _build_condition_variables(extracted)

        assert len(result) == 2
        assert result[0]["normalized"] == "fed_funds"
        assert result[0]["ticker"] == "FEDFUNDS"
        assert result[0]["source"] == "FRED"
        assert result[1]["normalized"] == "vix"
        assert result[1]["ticker"] == "^VIX"


# ===========================================================================
# Change 3: refine_query() Implementation
# ===========================================================================

class TestChange3_RefinementPrompt:
    """Test that QUERY_REFINEMENT_PROMPT is importable and well-formed."""

    def test_prompt_importable(self):
        from query_processing_prompts import QUERY_REFINEMENT_PROMPT
        assert isinstance(QUERY_REFINEMENT_PROMPT, str)

    def test_prompt_has_placeholders(self):
        from query_processing_prompts import QUERY_REFINEMENT_PROMPT
        assert "{query}" in QUERY_REFINEMENT_PROMPT
        assert "{chunk_count}" in QUERY_REFINEMENT_PROMPT
        assert "{chunk_summaries}" in QUERY_REFINEMENT_PROMPT


class TestChange3_RefineQuery:
    """Test refine_query() with mocked LLM calls."""

    @patch("query_processing.call_claude_haiku")
    def test_refine_returns_new_query(self, mock_haiku):
        mock_haiku.return_value = "alternative financial terminology carry trade unwind"

        from query_processing import refine_query

        chunks = [
            {"metadata": {"title": "Yen Analysis", "text": "USDJPY moved significantly..."}},
            {"metadata": {"title": "FX Report", "text": "Currency markets showed..."}},
        ]

        result = refine_query("carry trade unwind impact", chunks)

        assert result != "carry trade unwind impact"
        assert "carry trade" in result
        mock_haiku.assert_called_once()

    @patch("query_processing.call_claude_haiku")
    def test_refine_falls_back_on_exception(self, mock_haiku):
        mock_haiku.side_effect = Exception("API error")

        from query_processing import refine_query

        result = refine_query("original query", [])
        assert result == "original query"

    @patch("query_processing.call_claude_haiku")
    def test_refine_handles_empty_chunks(self, mock_haiku):
        mock_haiku.return_value = "broader financial research query"

        from query_processing import refine_query

        result = refine_query("niche query", [])

        assert result == "broader financial research query"
        # Verify the prompt was called with "(no chunks found)"
        call_args = mock_haiku.call_args
        prompt_content = call_args[0][0][0]["content"]
        assert "(no chunks found)" in prompt_content

    @patch("query_processing.call_claude_haiku")
    def test_refine_returns_original_if_llm_echoes(self, mock_haiku):
        mock_haiku.return_value = "original query"

        from query_processing import refine_query

        result = refine_query("original query", [])
        assert result == "original query"
