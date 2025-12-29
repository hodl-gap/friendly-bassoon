"""
Metrics Mapping Prompts

Prompts for metrics dictionary management operations.
Used by metrics_mapping_utils.py for LLM-assisted normalization.
"""


def get_institution_normalization_prompt(institutions: list[str]) -> str:
    """
    Get prompt for normalizing financial institution names.

    Args:
        institutions: List of institution names to normalize

    Returns:
        Prompt string for institution normalization
    """
    institutions_list = "\n".join(f"- {inst}" for inst in institutions)

    return f"""Normalize these financial institution names to their canonical forms.

INPUT INSTITUTIONS:
{institutions_list}

NORMALIZATION RULES:
- GS, Goldman, GS FICC, GS FICC Desk, Goldman Sachs FICC, Goldman Sachs Global Investment Research → "Goldman Sachs"
- SocGen, Societe Generale, SG → "Societe Generale"
- UBS, UBS Global Research → "UBS"
- JPM, JP Morgan, JPMorgan Chase → "JPMorgan"
- MS, Morgan Stanley → "Morgan Stanley"
- BofA, Bank of America, BAML, Bank of America Merrill Lynch → "Bank of America"
- Citi, Citigroup, Citibank → "Citi"
- DB, Deutsche Bank → "Deutsche Bank"
- CS, Credit Suisse → "Credit Suisse"
- HSBC stays "HSBC"
- Barclays stays "Barclays"
- Bloomberg stays "Bloomberg"
- Franklin Templeton stays "Franklin Templeton"
- TS Lombard stays "TS Lombard"
- ICE BofA stays as data source, not institution
- For unknown institutions, keep original name

OUTPUT FORMAT (JSON):
Return a JSON object mapping each input institution to its normalized form.
Example: {{"GS FICC": "Goldman Sachs", "UBS": "UBS", "SocGen": "Societe Generale"}}

Output ONLY the JSON object, nothing else."""
