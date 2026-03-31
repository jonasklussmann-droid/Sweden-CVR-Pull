"""Swedish XBRL taxonomy concept mapping.

Maps Swedish iXBRL taxonomy concepts (from SE-GEN-BASE / K2 / K3 taxonomies)
to normalized financial field names. The mapping covers the most common concept
names used in Swedish annual reports filed with Bolagsverket.

Concept names in Swedish iXBRL filings typically appear as:
  - Namespace-prefixed: se-gen-base:Nettoomsattning
  - Local name only: Nettoomsattning

This module handles both forms and provides case-insensitive matching.
"""

# Maps normalized lowercase concept names -> FinancialData field name
# Covers K2, K3, and SE-GEN-BASE taxonomy variants
CONCEPT_TO_FIELD: dict[str, str] = {
    # ── Net Sales / Revenue ──────────────────────────────────────
    "nettoomsattning": "net_sales",
    "nettoomsättning": "net_sales",
    "netrevenue": "net_sales",
    "netsales": "net_sales",
    "omsattning": "revenue",
    "omsättning": "revenue",
    "revenue": "revenue",
    "rorelseintakter": "revenue",
    "rörelseintäkter": "revenue",
    "summarorelseintakter": "revenue",

    # ── Other Operating Income ───────────────────────────────────
    "ovrigarorelseintakter": "other_operating_income",
    "övrigarörelseintäkter": "other_operating_income",
    "ovrigaintakter": "other_operating_income",
    "otheroperatingincome": "other_operating_income",

    # ── Change in Inventory ──────────────────────────────────────
    "forandringavlagerprodukteriarbetefardigavarorochpagaendearbete": "change_in_inventory",
    "forandringavlager": "change_in_inventory",
    "lagerforandring": "change_in_inventory",
    "changeinventories": "change_in_inventory",

    # ── Raw Materials and Consumables ────────────────────────────
    "ravarorochfornodenheter": "raw_materials_and_consumables",
    "råvarorochförnödenheter": "raw_materials_and_consumables",
    "rawmaterialsandconsumables": "raw_materials_and_consumables",
    "ravarorochformaterialkostnader": "raw_materials_and_consumables",

    # ── Trade Goods / COGS ───────────────────────────────────────
    "handelsvaror": "trade_goods",
    "kostnadforhandelsvaror": "trade_goods",
    "kostnadsaldavaror": "trade_goods",
    "kostnadförsåldavaror": "trade_goods",
    "costofsales": "trade_goods",
    "costofgoodssold": "trade_goods",
    "handelsvara": "trade_goods",
    "inkopavaror": "trade_goods",
    "inköpavaror": "trade_goods",

    # ── Other External Costs ─────────────────────────────────────
    "ovrigaexternakostnader": "other_external_costs",
    "övrigaexternakostnader": "other_external_costs",
    "otherexternalcosts": "other_external_costs",

    # ── Personnel Costs ──────────────────────────────────────────
    "personalkostnader": "personnel_costs",
    "personalcosts": "personnel_costs",
    "employeebenefitexpense": "personnel_costs",

    # ── Depreciation & Amortization ──────────────────────────────
    "avskrivningar": "depreciation_amortization",
    "avochnedskrivningaravmateriellaochimateriella": "depreciation_amortization",
    "avskrivningarochnedskrivningar": "depreciation_amortization",
    "depreciationamortisation": "depreciation_amortization",
    "depreciationandamortisation": "depreciation_amortization",
    "avskrivningaravmateriellaochimmateriellaanlaggningstillgangar": "depreciation_amortization",

    # ── Other Operating Expenses ─────────────────────────────────
    "ovrigarorelsekostnader": "other_operating_expenses",
    "övrigarörelsekostnader": "other_operating_expenses",
    "otheroperatingexpenses": "other_operating_expenses",

    # ── Operating Profit (EBIT) ──────────────────────────────────
    "rorelseresultat": "operating_profit",
    "rörelseresultat": "operating_profit",
    "operatingprofit": "operating_profit",
    "operatingresult": "operating_profit",
    "rorseleresultat": "operating_profit",  # common typo in filings

    # ── Financial Income ─────────────────────────────────────────
    "finansiellaintakter": "financial_income",
    "ovrigafinansiellaIntakter": "financial_income",
    "financialincome": "financial_income",
    "ranteinkomster": "financial_income",
    "ränteintäkter": "financial_income",
    "ranteintakterochliknanderesultatposter": "financial_income",

    # ── Financial Costs ──────────────────────────────────────────
    "finansiellakostnader": "financial_costs",
    "financialcosts": "financial_costs",
    "rantekostnader": "financial_costs",
    "räntekostnader": "financial_costs",
    "rantekostnaderochliknanderesultatposter": "financial_costs",

    # ── Result After Financial Items ─────────────────────────────
    "resultatefterfinansiellaposter": "result_after_financial_items",
    "resultatefterfinansnetto": "result_after_financial_items",
    "profitbeforetax": "result_after_financial_items",

    # ── Tax ───────────────────────────────────────────────────────
    "skattepaarsresultat": "tax",
    "skattpååretsresultat": "tax",
    "incometax": "tax",
    "skattpaarsresultat": "tax",
    "skatt": "tax",

    # ── Net Income ────────────────────────────────────────────────
    "arsresultat": "net_income",
    "årsresultat": "net_income",
    "aretsresultat": "net_income",
    "åretsresultat": "net_income",
    "netincome": "net_income",
    "profitfortheyear": "net_income",
    "resultat": "net_income",
}


def normalize_concept_name(concept: str) -> str:
    """Normalize an XBRL concept name for lookup.

    Strips namespace prefix, removes common separators, and lowercases.
    """
    # Remove namespace prefix (e.g., "se-gen-base:Nettoomsattning" -> "Nettoomsattning")
    if ":" in concept:
        concept = concept.split(":")[-1]

    # Remove hyphens, underscores, spaces
    concept = concept.replace("-", "").replace("_", "").replace(" ", "")

    return concept.lower()


def map_concept_to_field(concept: str) -> str | None:
    """Map an XBRL concept name to a FinancialData field name.

    Returns the field name if found, None otherwise.
    """
    normalized = normalize_concept_name(concept)
    return CONCEPT_TO_FIELD.get(normalized)


def get_all_mapped_concepts() -> list[str]:
    """Return all concept names that have a mapping."""
    return sorted(CONCEPT_TO_FIELD.keys())


def get_fields_for_concept(concept: str) -> str | None:
    """Get the FinancialData field name for a given concept."""
    return map_concept_to_field(concept)
