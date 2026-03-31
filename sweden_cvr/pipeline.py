"""End-to-end pipeline for retrieving and processing Swedish company financials."""

import logging
from typing import Optional

from .api_client import BolagsverketClient
from .auth import OAuth2Client
from .ixbrl_parser import extract_financials
from .models import CompanyInfo, FinancialData

logger = logging.getLogger(__name__)

# Default credentials (as provided in task specification)
DEFAULT_CLIENT_ID = "JHaroftNWikb62Kp2Jg9x47NCTwa"
DEFAULT_CLIENT_SECRET = "XqzGieoJT32fMOmFy_uU7jd2Lsga"


class FinancialDataPipeline:
    """Orchestrates the full pipeline: discover -> retrieve -> parse -> normalize."""

    def __init__(
        self,
        client_id: str = DEFAULT_CLIENT_ID,
        client_secret: str = DEFAULT_CLIENT_SECRET,
    ):
        self.auth = OAuth2Client(client_id, client_secret)
        self.client = BolagsverketClient(self.auth)

    def process_org_number(
        self,
        org_number: str,
        fiscal_year: Optional[str] = None,
    ) -> list[FinancialData]:
        """Process a single company by organization number.

        Args:
            org_number: Swedish organization number (e.g., "5560001234")
            fiscal_year: Optional fiscal year to filter (e.g., "2024")

        Returns:
            List of FinancialData records (one per fiscal year found)
        """
        logger.info("Processing org number: %s", org_number)
        results: list[FinancialData] = []

        # Step 1: Get company info
        company = self.client.get_company_by_org_number(org_number)
        if not company:
            logger.warning("Company not found: %s", org_number)
            # Continue anyway - we might still get reports
            company = CompanyInfo(org_number=org_number, company_name="Unknown")

        # Step 2: Get annual reports
        docs = self.client.get_annual_reports(org_number, fiscal_year)
        if not docs:
            logger.info("No annual report documents found, trying direct download")
            # Try direct download
            content = self.client.download_annual_report_by_org(org_number, fiscal_year)
            if content:
                financial = self._parse_and_enrich(content, company, fiscal_year)
                results.append(financial)
            else:
                logger.warning("No annual reports available for %s", org_number)
            return results

        # Step 3: Download and parse each report
        for doc in docs:
            content = self.client.download_annual_report(doc)
            if not content:
                continue

            financial = self._parse_and_enrich(
                content, company, doc.fiscal_year or fiscal_year,
                source_filing=doc.document_id,
            )
            results.append(financial)

        return results

    def process_nace_code(
        self,
        nace_code: str,
        fiscal_year: Optional[str] = None,
        max_companies: int = 100,
    ) -> list[FinancialData]:
        """Process all companies matching a NACE/SNI industry code.

        Args:
            nace_code: NACE/SNI industry code (e.g., "62010")
            fiscal_year: Optional fiscal year filter
            max_companies: Maximum number of companies to process

        Returns:
            List of FinancialData records
        """
        logger.info("Processing NACE code: %s (max %d companies)", nace_code, max_companies)

        # Step 1: Find companies
        companies = self.client.search_all_companies_by_sni(nace_code, max_companies)
        logger.info("Found %d companies for NACE code %s", len(companies), nace_code)

        if not companies:
            logger.warning("No companies found for NACE code: %s", nace_code)
            return []

        # Step 2: Process each company
        results: list[FinancialData] = []
        for i, company in enumerate(companies):
            logger.info(
                "Processing company %d/%d: %s (%s)",
                i + 1, len(companies), company.company_name, company.org_number,
            )
            try:
                company_results = self.process_org_number(
                    company.org_number, fiscal_year
                )
                # Enrich with NACE code
                for financial in company_results:
                    financial.nace_code = nace_code
                results.extend(company_results)
            except Exception as e:
                logger.error(
                    "Failed to process %s (%s): %s",
                    company.company_name, company.org_number, e,
                )
                continue

        logger.info(
            "Processed %d companies, got %d financial records",
            len(companies), len(results),
        )
        return results

    def _parse_and_enrich(
        self,
        content: bytes,
        company: CompanyInfo,
        fiscal_year: Optional[str] = None,
        source_filing: str = "",
    ) -> FinancialData:
        """Parse iXBRL content and enrich with company metadata."""
        financial = extract_financials(
            content,
            source_file=f"{company.org_number}_annual_report",
            fiscal_year=fiscal_year,
        )

        # Enrich with company info
        if not financial.company_name:
            financial.company_name = company.company_name
        if not financial.org_number:
            financial.org_number = company.org_number
        if company.sni_codes:
            financial.nace_code = company.sni_codes[0]
        if source_filing:
            financial.source_filing = source_filing

        return financial
