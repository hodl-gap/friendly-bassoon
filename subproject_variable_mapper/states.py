"""
LangGraph State Definitions for Variable Mapper

Defines the state schema used to pass data between function modules.
Keep states minimal - add fields as needed during development.
"""

from typing import TypedDict, List, Optional, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.schemas import LogicChain


class VariableMapperState(TypedDict, total=False):
    """Main state for the variable mapping workflow."""

    # Input
    synthesis: str  # Raw synthesis text from database_retriever (renamed from synthesis_input)
    data_temporal_context: Dict[str, Any]  # Optional: temporal context from retriever (data_years, etc.)
    logic_chains: List[LogicChain]  # Optional: structured logic_chains from retriever

    # Step 1: Variable Extraction
    extracted_variables: List[Dict[str, Any]]  # Variables found in text
    # Example: [{"name": "TGA", "context": "TGA drawdown", "threshold": null}]
    implicit_variables: List[Dict[str, Any]]  # Variables extracted from chain structure
    skip_step3: bool  # Flag to skip Step 3 if combined extraction was used

    # Step 2: Normalization
    normalized_variables: List[Dict[str, Any]]  # Variables with canonical names
    # Example: [{"raw_name": "Treasury General Account", "normalized_name": "TGA", "category": "direct"}]

    # Step 3: Missing Variable Detection
    missing_variables: List[str]  # Variables required but not provided
    chain_dependencies: List[Dict[str, Any]]  # Variable dependencies in logic chains

    # Step 4: Data ID Mapping (LATER)
    mapped_variables: List[Dict[str, Any]]  # Variables with Data IDs
    unmapped_variables: List[str]  # Variables without Data IDs

    # Output
    final_output: Dict[str, Any]  # Structured JSON output
