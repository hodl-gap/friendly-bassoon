"""
LangGraph State Definitions for Variable Mapper

Defines the state schema used to pass data between function modules.
Keep states minimal - add fields as needed during development.
"""

from typing import TypedDict, List, Optional, Dict, Any


class VariableMapperState(TypedDict, total=False):
    """Main state for the variable mapping workflow."""

    # Input
    synthesis_input: str  # Raw synthesis text from database_retriever
    data_temporal_context: Dict[str, Any]  # Optional: temporal context from retriever (data_years, etc.)

    # Step 1: Variable Extraction
    extracted_variables: List[Dict[str, Any]]  # Variables found in text
    # Example: [{"name": "TGA", "context": "TGA drawdown", "threshold": null}]

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
