"""Data models for Swedish company financial data."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompanyInfo:
    """Basic company information from Bolagsverket."""
    org_number: str
    company_name: str
    legal_form: str = ""
    sni_codes: list[str] = field(default_factory=list)
    address: str = ""
    postal_code: str = ""
    city: str = ""
    status: str = ""
    registration_date: str = ""


@dataclass
class XBRLFact:
    """A single fact extracted from an iXBRL document."""
    concept: str           # XBRL element/tag name
    value: Optional[float] # Numeric value (None for non-numeric)
    text_value: str = ""   # Raw text value
    context_id: str = ""   # Context reference
    unit: str = ""         # e.g. "SEK", "shares"
    decimals: int = 0      # Decimal precision
    scale: int = 0         # Scale factor (power of 10)
    period_start: str = "" # Period start date (YYYY-MM-DD)
    period_end: str = ""   # Period end date (YYYY-MM-DD)
    instant: str = ""      # Instant date for balance sheet items
    entity: str = ""       # Entity identifier (org number)
    source_file: str = ""  # Source iXBRL filename


@dataclass
class FinancialData:
    """Normalized financial data for a company and fiscal year."""
    company_name: str = ""
    org_number: str = ""
    nace_code: str = ""
    fiscal_year: str = ""
    period_start: str = ""
    period_end: str = ""
    currency: str = "SEK"

    # Income statement
    revenue: Optional[float] = None
    net_sales: Optional[float] = None
    other_operating_income: Optional[float] = None
    change_in_inventory: Optional[float] = None
    raw_materials_and_consumables: Optional[float] = None
    trade_goods: Optional[float] = None  # Handelsvaror / COGS
    other_external_costs: Optional[float] = None
    personnel_costs: Optional[float] = None
    depreciation_amortization: Optional[float] = None
    other_operating_expenses: Optional[float] = None
    operating_profit: Optional[float] = None  # Rörelseresultat / EBIT
    financial_income: Optional[float] = None
    financial_costs: Optional[float] = None
    result_after_financial_items: Optional[float] = None
    tax: Optional[float] = None
    net_income: Optional[float] = None  # Årets resultat

    # Calculated fields
    cogs: Optional[float] = None
    gross_profit: Optional[float] = None
    ebit: Optional[float] = None
    ebitda: Optional[float] = None

    # Traceability
    source_filing: str = ""
    source_file: str = ""
    facts: list[XBRLFact] = field(default_factory=list)

    def calculate_derived_fields(self):
        """Calculate COGS, gross profit, EBIT, EBITDA from extracted data."""
        # COGS = raw materials + trade goods (if available)
        cogs_components = [
            self.raw_materials_and_consumables,
            self.trade_goods,
        ]
        non_none = [c for c in cogs_components if c is not None]
        if non_none:
            self.cogs = sum(non_none)

        # Gross profit = net_sales - COGS (or revenue - COGS)
        sales = self.net_sales if self.net_sales is not None else self.revenue
        if sales is not None and self.cogs is not None:
            self.gross_profit = sales + self.cogs  # COGS is negative

        # EBIT = operating_profit
        if self.operating_profit is not None:
            self.ebit = self.operating_profit

        # EBITDA = EBIT + depreciation (depreciation is negative, so subtract)
        if self.ebit is not None and self.depreciation_amortization is not None:
            self.ebitda = self.ebit - self.depreciation_amortization

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/Excel export."""
        return {
            "company_name": self.company_name,
            "org_number": self.org_number,
            "nace_code": self.nace_code,
            "fiscal_year": self.fiscal_year,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "currency": self.currency,
            "revenue": self.revenue,
            "net_sales": self.net_sales,
            "other_operating_income": self.other_operating_income,
            "change_in_inventory": self.change_in_inventory,
            "raw_materials_and_consumables": self.raw_materials_and_consumables,
            "trade_goods_cogs": self.trade_goods,
            "other_external_costs": self.other_external_costs,
            "personnel_costs": self.personnel_costs,
            "depreciation_amortization": self.depreciation_amortization,
            "other_operating_expenses": self.other_operating_expenses,
            "operating_profit": self.operating_profit,
            "financial_income": self.financial_income,
            "financial_costs": self.financial_costs,
            "result_after_financial_items": self.result_after_financial_items,
            "tax": self.tax,
            "net_income": self.net_income,
            "cogs": self.cogs,
            "gross_profit": self.gross_profit,
            "ebit": self.ebit,
            "ebitda": self.ebitda,
            "source_filing": self.source_filing,
            "source_file": self.source_file,
        }


@dataclass
class DocumentInfo:
    """Metadata about an annual report document from Bolagsverket."""
    org_number: str = ""
    fiscal_year: str = ""
    document_id: str = ""
    document_type: str = ""
    filing_date: str = ""
    status: str = ""
    download_url: str = ""
    format: str = ""  # "ixbrl", "xhtml", "pdf"
