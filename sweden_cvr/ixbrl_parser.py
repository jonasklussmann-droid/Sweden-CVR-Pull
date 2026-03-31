"""Deterministic iXBRL parser for Swedish annual reports.

Parses inline XBRL (iXBRL) documents and extracts structured financial facts.
Handles both the ixbrlparse library approach and direct BeautifulSoup/lxml
parsing as fallback.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import FinancialData, XBRLFact
from .taxonomy import map_concept_to_field

logger = logging.getLogger(__name__)

# iXBRL namespace prefixes
IX_NS = "http://www.xbrl.org/2013/inlineXBRL"
XBRLI_NS = "http://www.xbrl.org/2003/instance"
LINK_NS = "http://www.xbrl.org/2003/linkbase"

# Scale factor map: iXBRL scale attribute -> multiplier
SCALE_FACTORS = {
    "-6": 0.000001,
    "-3": 0.001,
    "-2": 0.01,
    "-1": 0.1,
    "0": 1,
    "1": 10,
    "2": 100,
    "3": 1000,
    "4": 10000,
    "5": 100000,
    "6": 1000000,
    "9": 1000000000,
}

# iXBRL format patterns for parsing formatted numbers
# Swedish number format: 1 234 567 or 1.234.567 (thousands separator)
# Negative: -1 234 or (1 234)
NUMBER_CLEANUP_RE = re.compile(r"[^\d,.\-]")


def parse_ixbrl_number(text: str, scale: int = 0, sign: str = "") -> Optional[float]:
    """Parse a number from iXBRL text content, applying scale and sign.

    Swedish iXBRL filings may use:
    - Space as thousands separator: "1 234 567"
    - Period as thousands separator: "1.234.567"
    - Comma as decimal separator: "1234,56"
    - Parentheses for negative: "(1234)"
    - Dash for zero: "-" or "–"
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Handle dash/en-dash meaning zero
    if text in ("-", "–", "—", "−"):
        return 0.0

    # Handle parenthetical negatives: (1234) -> -1234
    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1]

    if sign == "-":
        is_negative = True

    # Remove whitespace (Swedish thousands separator)
    text = text.replace(" ", "").replace("\xa0", "").replace("\u2009", "")

    # Determine decimal separator
    # If both . and , exist, the last one is the decimal separator
    has_comma = "," in text
    has_period = "." in text

    if has_comma and has_period:
        # Both present: last occurrence is decimal
        last_comma = text.rfind(",")
        last_period = text.rfind(".")
        if last_comma > last_period:
            # Comma is decimal: 1.234,56
            text = text.replace(".", "").replace(",", ".")
        else:
            # Period is decimal: 1,234.56
            text = text.replace(",", "")
    elif has_comma:
        # Only comma: it's the decimal separator (Swedish standard)
        text = text.replace(",", ".")
    # If only period, it's already correct for float parsing

    # Remove any remaining non-numeric chars except . and -
    text = re.sub(r"[^\d.\-]", "", text)

    if not text:
        return None

    try:
        value = float(text)
    except ValueError:
        logger.warning("Could not parse number: %s", text)
        return None

    # Apply scale factor
    scale_multiplier = SCALE_FACTORS.get(str(scale), 10 ** scale)
    value *= scale_multiplier

    if is_negative:
        value = -abs(value)

    return value


class IXBRLParser:
    """Parser for iXBRL (inline XBRL) documents."""

    def __init__(self):
        self.facts: list[XBRLFact] = []
        self.contexts: dict[str, dict] = {}
        self.units: dict[str, str] = {}

    def parse(self, content: bytes | str, source_file: str = "") -> list[XBRLFact]:
        """Parse iXBRL content and extract all facts.

        Args:
            content: Raw iXBRL/XHTML content (bytes or string)
            source_file: Name of the source file for traceability

        Returns:
            List of extracted XBRLFact objects
        """
        self.facts = []
        self.contexts = {}
        self.units = {}

        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        logger.info("Parsing iXBRL document (%d chars) from %s", len(content), source_file)

        soup = BeautifulSoup(content, "lxml")

        # First pass: extract contexts and units
        self._extract_contexts(soup)
        self._extract_units(soup)

        # Second pass: extract facts from ix:nonFraction, ix:nonNumeric, ix:fraction
        self._extract_numeric_facts(soup, source_file)
        self._extract_nonnumeric_facts(soup, source_file)

        logger.info("Extracted %d facts from %s", len(self.facts), source_file)
        return self.facts

    def _extract_contexts(self, soup: BeautifulSoup):
        """Extract XBRL context definitions (periods and entities)."""
        # Find context elements: <xbrli:context> or <context>
        for ctx in soup.find_all(re.compile(r"(?:xbrli:)?context", re.I)):
            ctx_id = ctx.get("id", "")
            if not ctx_id:
                continue

            context_data: dict = {"id": ctx_id}

            # Extract entity identifier
            entity = ctx.find(re.compile(r"(?:xbrli:)?identifier", re.I))
            if entity:
                context_data["entity"] = entity.get_text(strip=True)

            # Extract period
            period = ctx.find(re.compile(r"(?:xbrli:)?period", re.I))
            if period:
                start = period.find(re.compile(r"(?:xbrli:)?startdate", re.I))
                end = period.find(re.compile(r"(?:xbrli:)?enddate", re.I))
                instant = period.find(re.compile(r"(?:xbrli:)?instant", re.I))

                if start:
                    context_data["startDate"] = start.get_text(strip=True)
                if end:
                    context_data["endDate"] = end.get_text(strip=True)
                if instant:
                    context_data["instant"] = instant.get_text(strip=True)

            self.contexts[ctx_id] = context_data

        logger.debug("Extracted %d contexts", len(self.contexts))

    def _extract_units(self, soup: BeautifulSoup):
        """Extract XBRL unit definitions."""
        for unit in soup.find_all(re.compile(r"(?:xbrli:)?unit", re.I)):
            unit_id = unit.get("id", "")
            if not unit_id:
                continue

            measure = unit.find(re.compile(r"(?:xbrli:)?measure", re.I))
            if measure:
                measure_text = measure.get_text(strip=True)
                # Extract currency code: "iso4217:SEK" -> "SEK"
                if ":" in measure_text:
                    measure_text = measure_text.split(":")[-1]
                self.units[unit_id] = measure_text

        logger.debug("Extracted %d units: %s", len(self.units), self.units)

    def _extract_numeric_facts(self, soup: BeautifulSoup, source_file: str):
        """Extract numeric facts from ix:nonFraction elements."""
        # Match ix:nonFraction, ix:nonfraction, nonfraction
        for elem in soup.find_all(re.compile(r"(?:ix:)?nonfraction", re.I)):
            fact = self._parse_numeric_element(elem, source_file)
            if fact:
                self.facts.append(fact)

    def _extract_nonnumeric_facts(self, soup: BeautifulSoup, source_file: str):
        """Extract non-numeric facts from ix:nonNumeric elements."""
        for elem in soup.find_all(re.compile(r"(?:ix:)?nonnumeric", re.I)):
            concept = elem.get("name", "")
            if not concept:
                continue

            ctx_ref = elem.get("contextref", elem.get("contextRef", ""))
            text_value = elem.get_text(strip=True)

            context = self.contexts.get(ctx_ref, {})

            fact = XBRLFact(
                concept=concept,
                value=None,
                text_value=text_value,
                context_id=ctx_ref,
                period_start=context.get("startDate", ""),
                period_end=context.get("endDate", ""),
                instant=context.get("instant", ""),
                entity=context.get("entity", ""),
                source_file=source_file,
            )
            self.facts.append(fact)

    def _parse_numeric_element(self, elem: Tag, source_file: str) -> Optional[XBRLFact]:
        """Parse a single ix:nonFraction element into an XBRLFact."""
        concept = elem.get("name", "")
        if not concept:
            return None

        ctx_ref = elem.get("contextref", elem.get("contextRef", ""))
        unit_ref = elem.get("unitref", elem.get("unitRef", ""))
        scale = int(elem.get("scale", "0") or "0")
        decimals_str = elem.get("decimals", "0") or "0"
        sign = elem.get("sign", "")
        fmt = elem.get("format", "")

        # Handle INF decimals
        try:
            decimals = int(decimals_str) if decimals_str != "INF" else 0
        except ValueError:
            decimals = 0

        # Get the text content
        text = elem.get_text(strip=True)

        # Check for ix:exclude children (excluded from XBRL value)
        for excluded in elem.find_all(re.compile(r"(?:ix:)?exclude", re.I)):
            excluded_text = excluded.get_text()
            text = text.replace(excluded_text, "")

        # Parse the numeric value
        value = parse_ixbrl_number(text, scale=scale, sign=sign)

        # Look up context and unit
        context = self.contexts.get(ctx_ref, {})
        unit = self.units.get(unit_ref, unit_ref)

        return XBRLFact(
            concept=concept,
            value=value,
            text_value=text,
            context_id=ctx_ref,
            unit=unit,
            decimals=decimals,
            scale=scale,
            period_start=context.get("startDate", ""),
            period_end=context.get("endDate", ""),
            instant=context.get("instant", ""),
            entity=context.get("entity", ""),
            source_file=source_file,
        )

    def parse_with_ixbrlparse(self, content: bytes | str, source_file: str = "") -> list[XBRLFact]:
        """Alternative parser using the ixbrlparse library as fallback.

        Falls back to the manual BeautifulSoup parser if ixbrlparse is not
        available or fails.
        """
        try:
            from ixbrlparse import IXBRL

            if isinstance(content, str):
                content = content.encode("utf-8")

            import io
            x = IXBRL(io.BytesIO(content))

            facts: list[XBRLFact] = []

            # Process numeric facts
            for fact in x.numeric:
                ctx = fact.context or {}
                period_start = ""
                period_end = ""
                instant = ""
                entity = ""

                if hasattr(ctx, "startdate") and ctx.startdate:
                    period_start = str(ctx.startdate)
                if hasattr(ctx, "enddate") and ctx.enddate:
                    period_end = str(ctx.enddate)
                if hasattr(ctx, "instant") and ctx.instant:
                    instant = str(ctx.instant)
                if hasattr(ctx, "entity") and ctx.entity:
                    entity = str(ctx.entity.get("identifier", ""))

                xfact = XBRLFact(
                    concept=fact.name or "",
                    value=float(fact.value) if fact.value is not None else None,
                    text_value=str(fact.value) if fact.value is not None else "",
                    context_id=getattr(ctx, "id", ""),
                    unit=str(getattr(fact, "unit", "")),
                    source_file=source_file,
                    period_start=period_start,
                    period_end=period_end,
                    instant=instant,
                    entity=entity,
                )
                facts.append(xfact)

            # Process non-numeric facts
            for fact in x.nonnumeric:
                ctx = fact.context or {}
                period_start = ""
                period_end = ""
                instant = ""
                entity = ""

                if hasattr(ctx, "startdate") and ctx.startdate:
                    period_start = str(ctx.startdate)
                if hasattr(ctx, "enddate") and ctx.enddate:
                    period_end = str(ctx.enddate)
                if hasattr(ctx, "instant") and ctx.instant:
                    instant = str(ctx.instant)
                if hasattr(ctx, "entity") and ctx.entity:
                    entity = str(ctx.entity.get("identifier", ""))

                xfact = XBRLFact(
                    concept=fact.name or "",
                    value=None,
                    text_value=str(fact.value) if fact.value else "",
                    context_id=getattr(ctx, "id", ""),
                    source_file=source_file,
                    period_start=period_start,
                    period_end=period_end,
                    instant=instant,
                    entity=entity,
                )
                facts.append(xfact)

            logger.info(
                "ixbrlparse extracted %d facts from %s", len(facts), source_file
            )
            return facts

        except ImportError:
            logger.info("ixbrlparse not available, using manual parser")
            return self.parse(content, source_file)
        except Exception as e:
            logger.warning("ixbrlparse failed (%s), falling back to manual parser", e)
            return self.parse(content, source_file)


def extract_financials(
    content: bytes | str,
    source_file: str = "",
    fiscal_year: Optional[str] = None,
) -> FinancialData:
    """Extract and normalize financial data from iXBRL content.

    This is the main entry point for iXBRL parsing. It:
    1. Parses the iXBRL document
    2. Maps XBRL concepts to normalized financial fields
    3. Filters by fiscal year if specified
    4. Calculates derived fields (COGS, gross profit, EBITDA)

    Args:
        content: Raw iXBRL/XHTML content
        source_file: Source filename for traceability
        fiscal_year: Optional fiscal year filter (e.g., "2024")

    Returns:
        FinancialData with extracted and normalized values
    """
    parser = IXBRLParser()

    # Try ixbrlparse first, fall back to manual
    facts = parser.parse_with_ixbrlparse(content, source_file)
    if not facts:
        facts = parser.parse(content, source_file)

    financial = FinancialData(source_file=source_file)
    financial.facts = facts

    # Determine the primary currency from units
    currencies = set()
    for fact in facts:
        if fact.unit and fact.unit.upper() in ("SEK", "EUR", "USD", "GBP", "DKK", "NOK"):
            currencies.add(fact.unit.upper())
    if currencies:
        financial.currency = "SEK" if "SEK" in currencies else currencies.pop()

    # Determine fiscal year period from contexts
    _set_period_from_facts(financial, facts, fiscal_year)

    # Map facts to financial fields
    for fact in facts:
        if fact.value is None:
            # Check for company name in non-numeric facts
            concept_lower = fact.concept.lower()
            if "foretagsnamn" in concept_lower or "companyname" in concept_lower or "entityname" in concept_lower:
                financial.company_name = fact.text_value
            elif "organisationsnummer" in concept_lower or "orgnr" in concept_lower:
                financial.org_number = fact.text_value
            continue

        # Only use facts that match our target period
        if financial.period_start and fact.period_start:
            if fact.period_start != financial.period_start:
                continue
        if financial.period_end and fact.period_end:
            if fact.period_end != financial.period_end:
                continue

        field_name = map_concept_to_field(fact.concept)
        if field_name and hasattr(financial, field_name):
            current = getattr(financial, field_name)
            # Only set if not already set (first match wins for the period)
            if current is None:
                setattr(financial, field_name, fact.value)
                logger.debug(
                    "Mapped %s -> %s = %s", fact.concept, field_name, fact.value
                )

    # Calculate derived fields
    financial.calculate_derived_fields()

    return financial


def _set_period_from_facts(
    financial: FinancialData,
    facts: list[XBRLFact],
    fiscal_year: Optional[str],
):
    """Determine the primary reporting period from extracted facts."""
    # Collect all unique duration periods (start-end pairs)
    periods: dict[tuple[str, str], int] = {}
    for fact in facts:
        if fact.period_start and fact.period_end and fact.value is not None:
            key = (fact.period_start, fact.period_end)
            periods[key] = periods.get(key, 0) + 1

    if not periods:
        return

    # If fiscal_year specified, try to find matching period
    if fiscal_year:
        for (start, end), count in periods.items():
            if fiscal_year in end or fiscal_year in start:
                financial.period_start = start
                financial.period_end = end
                financial.fiscal_year = fiscal_year
                return

    # Otherwise, pick the period with the most facts (likely the current year)
    best_period = max(periods, key=periods.get)  # type: ignore[arg-type]
    financial.period_start = best_period[0]
    financial.period_end = best_period[1]

    # Extract year from end date
    if best_period[1]:
        financial.fiscal_year = best_period[1][:4]
