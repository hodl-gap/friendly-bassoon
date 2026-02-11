"""
Centralized path definitions for the project.

Provides PROJECT_ROOT and SUBPROJECTS dict so all modules use consistent paths.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

SUBPROJECTS = {
    "database_manager": PROJECT_ROOT / "subproject_database_manager",
    "database_retriever": PROJECT_ROOT / "subproject_database_retriever",
    "variable_mapper": PROJECT_ROOT / "subproject_variable_mapper",
    "data_collection": PROJECT_ROOT / "subproject_data_collection",
    "risk_intelligence": PROJECT_ROOT / "subproject_risk_intelligence",
}
