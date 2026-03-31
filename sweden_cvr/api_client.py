"""Bolagsverket API client for company search and document retrieval."""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .auth import OAuth2Client
from .models import CompanyInfo, DocumentInfo

logger = logging.getLogger(__name__)

# Bolagsverket API base URLs
API_BASE = "https://portal.api.bolagsverket.se"
COMPANY_API = f"{API_BASE}/foretagsinformation/v4"
VALUABLE_DATA_API = f"{API_BASE}/vardefulladatamangder/v1"


class RateLimiter:
    """Simple rate limiter: max N requests per second."""

    def __init__(self, max_per_second: float = 15):
        self.min_interval = 1.0 / max_per_second
        self._last_request: float = 0

    def wait(self):
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.time()


class BolagsverketClient:
    """Client for Bolagsverket's APIs (company info + valuable datasets)."""

    def __init__(self, auth: OAuth2Client):
        self.auth = auth
        self.session = requests.Session()
        self.rate_limiter = RateLimiter(max_per_second=15)

    def _headers(self) -> dict[str, str]:
        headers = self.auth.get_auth_header()
        headers["Accept"] = "application/json"
        return headers

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=16),
        reraise=True,
    )
    def _get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """Make an authenticated GET request with rate limiting and retries."""
        self.rate_limiter.wait()
        logger.debug("GET %s params=%s", url, params)
        response = self.session.get(
            url, headers=self._headers(), params=params, timeout=30
        )
        response.raise_for_status()
        return response

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=16),
        reraise=True,
    )
    def _get_binary(self, url: str) -> bytes:
        """Download binary content (iXBRL files) with retries."""
        self.rate_limiter.wait()
        logger.debug("GET (binary) %s", url)
        response = self.session.get(
            url, headers=self.auth.get_auth_header(), timeout=60
        )
        response.raise_for_status()
        return response.content

    # ── Company Search ──────────────────────────────────────────────

    def get_company_by_org_number(self, org_number: str) -> Optional[CompanyInfo]:
        """Look up a company by its Swedish organization number."""
        org_number = org_number.replace("-", "").replace(" ", "")
        logger.info("Looking up company with org number: %s", org_number)

        # Try the valuable datasets API first
        try:
            url = f"{VALUABLE_DATA_API}/organisations/{org_number}"
            resp = self._get(url)
            data = resp.json()
            return self._parse_company(data)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.warning("Company %s not found in valuable datasets", org_number)
            else:
                logger.warning("Valuable datasets API error: %s", e)

        # Fallback to company information API
        try:
            url = f"{COMPANY_API}/organisationer/{org_number}"
            resp = self._get(url)
            data = resp.json()
            return self._parse_company(data)
        except requests.HTTPError as e:
            logger.error("Failed to find company %s: %s", org_number, e)
            return None

    def search_companies_by_sni(
        self, sni_code: str, limit: int = 100, offset: int = 0
    ) -> list[CompanyInfo]:
        """Search for companies by SNI/NACE industry code."""
        logger.info("Searching companies with SNI code: %s", sni_code)
        companies = []

        try:
            url = f"{VALUABLE_DATA_API}/organisations"
            params = {
                "sniKod": sni_code,
                "limit": min(limit, 100),
                "offset": offset,
            }
            resp = self._get(url, params=params)
            data = resp.json()

            org_list = data if isinstance(data, list) else data.get("organisations", data.get("data", []))
            for item in org_list:
                company = self._parse_company(item)
                if company:
                    companies.append(company)

            logger.info("Found %d companies for SNI code %s", len(companies), sni_code)
        except requests.HTTPError as e:
            logger.error("SNI search failed: %s", e)

        return companies

    def search_all_companies_by_sni(
        self, sni_code: str, max_companies: int = 1000
    ) -> list[CompanyInfo]:
        """Paginate through all companies matching a SNI code."""
        all_companies: list[CompanyInfo] = []
        offset = 0
        page_size = 100

        while len(all_companies) < max_companies:
            batch = self.search_companies_by_sni(
                sni_code, limit=page_size, offset=offset
            )
            if not batch:
                break
            all_companies.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size

        return all_companies[:max_companies]

    def _parse_company(self, data: dict) -> Optional[CompanyInfo]:
        """Parse company data from API response into CompanyInfo model."""
        if not data:
            return None

        # Handle nested structures - the API may return data in different shapes
        org = data.get("organisation", data)

        org_number = str(
            org.get("organisationsnummer", org.get("orgnr", org.get("orgNr", "")))
        )
        name = org.get("namn", org.get("name", org.get("foretagsnamn", "")))

        sni_codes = []
        sni_data = org.get("sniKoder", org.get("sniCodes", []))
        if isinstance(sni_data, list):
            for s in sni_data:
                if isinstance(s, dict):
                    sni_codes.append(str(s.get("kod", s.get("code", ""))))
                else:
                    sni_codes.append(str(s))

        address_data = org.get("adress", org.get("address", {}))
        if isinstance(address_data, dict):
            address = address_data.get("gatuadress", address_data.get("street", ""))
            postal_code = address_data.get("postnummer", address_data.get("postalCode", ""))
            city = address_data.get("postort", address_data.get("city", ""))
        else:
            address = postal_code = city = ""

        return CompanyInfo(
            org_number=org_number,
            company_name=name,
            legal_form=org.get("foretagsform", org.get("legalForm", "")),
            sni_codes=sni_codes,
            address=address,
            postal_code=postal_code,
            city=city,
            status=org.get("status", ""),
            registration_date=org.get("registreringsdatum", org.get("registrationDate", "")),
        )

    # ── Annual Report Documents ─────────────────────────────────────

    def get_annual_reports(
        self, org_number: str, fiscal_year: Optional[str] = None
    ) -> list[DocumentInfo]:
        """Retrieve annual report metadata for a company."""
        org_number = org_number.replace("-", "").replace(" ", "")
        logger.info("Fetching annual reports for %s (year=%s)", org_number, fiscal_year)

        documents: list[DocumentInfo] = []

        # Try valuable datasets API for annual reports
        try:
            url = f"{VALUABLE_DATA_API}/organisations/{org_number}/arsredovisningar"
            resp = self._get(url)
            data = resp.json()

            report_list = data if isinstance(data, list) else data.get("arsredovisningar", data.get("data", []))
            for item in report_list:
                doc = self._parse_document(item, org_number)
                if doc:
                    if fiscal_year and doc.fiscal_year != fiscal_year:
                        continue
                    documents.append(doc)
        except requests.HTTPError as e:
            logger.warning("Valuable datasets annual reports API error: %s", e)

        # Fallback: try the annual report information API
        if not documents:
            try:
                url = f"{API_BASE}/hamta-arsredovisningsinformation/v1.1/arendestatus/{org_number}"
                resp = self._get(url)
                data = resp.json()
                report_list = data if isinstance(data, list) else data.get("arenden", data.get("data", []))
                for item in report_list:
                    doc = self._parse_document(item, org_number)
                    if doc:
                        if fiscal_year and doc.fiscal_year != fiscal_year:
                            continue
                        documents.append(doc)
            except requests.HTTPError as e:
                logger.warning("Annual report info API error: %s", e)

        logger.info("Found %d annual reports for %s", len(documents), org_number)
        return documents

    def download_annual_report(self, doc: DocumentInfo) -> Optional[bytes]:
        """Download an annual report document (iXBRL/XHTML)."""
        if not doc.download_url:
            logger.error("No download URL for document %s", doc.document_id)
            return None

        logger.info("Downloading annual report: %s", doc.download_url)
        try:
            return self._get_binary(doc.download_url)
        except requests.HTTPError as e:
            logger.error("Failed to download report: %s", e)
            return None

    def download_annual_report_by_org(
        self, org_number: str, fiscal_year: Optional[str] = None
    ) -> Optional[bytes]:
        """Download annual report iXBRL content directly."""
        org_number = org_number.replace("-", "").replace(" ", "")
        logger.info(
            "Downloading annual report for %s (year=%s)", org_number, fiscal_year
        )

        # Try direct download endpoint from valuable datasets
        try:
            url = f"{VALUABLE_DATA_API}/organisations/{org_number}/arsredovisningar"
            params = {}
            if fiscal_year:
                params["rakenskapsar"] = fiscal_year
            resp = self._get(url, params=params)
            data = resp.json()

            # If the response contains a download link, use it
            reports = data if isinstance(data, list) else data.get("arsredovisningar", data.get("data", []))
            if reports:
                report = reports[0]  # Take the most recent
                download_url = report.get("downloadUrl", report.get("url", report.get("dokumentUrl", "")))
                if download_url:
                    return self._get_binary(download_url)

                # If the report data itself contains the iXBRL content
                content = report.get("innehall", report.get("content", ""))
                if content:
                    return content.encode("utf-8") if isinstance(content, str) else content
        except requests.HTTPError as e:
            logger.warning("Direct download failed: %s", e)

        # Fallback: try fetching documents list and downloading
        docs = self.get_annual_reports(org_number, fiscal_year)
        for doc in docs:
            if doc.format in ("ixbrl", "xhtml", "xbrl"):
                content = self.download_annual_report(doc)
                if content:
                    return content

        # Try any available document
        for doc in docs:
            content = self.download_annual_report(doc)
            if content:
                return content

        logger.warning("No downloadable annual report found for %s", org_number)
        return None

    def _parse_document(self, data: dict, org_number: str) -> Optional[DocumentInfo]:
        """Parse document metadata from API response."""
        if not data:
            return None

        fiscal_year = str(
            data.get("rakenskapsar", data.get("fiscalYear", data.get("ar", "")))
        )
        doc_id = str(data.get("id", data.get("arendenummer", data.get("documentId", ""))))
        doc_type = data.get("typ", data.get("type", data.get("dokumenttyp", "arsredovisning")))
        filing_date = data.get("inlamningsdatum", data.get("filingDate", data.get("datum", "")))
        status = data.get("status", "")
        download_url = data.get("downloadUrl", data.get("url", data.get("dokumentUrl", "")))

        # Determine format from URL or metadata
        fmt = data.get("format", "")
        if not fmt and download_url:
            if ".xhtml" in download_url or ".ixbrl" in download_url:
                fmt = "ixbrl"
            elif ".pdf" in download_url:
                fmt = "pdf"

        return DocumentInfo(
            org_number=org_number,
            fiscal_year=fiscal_year,
            document_id=doc_id,
            document_type=doc_type,
            filing_date=filing_date,
            status=status,
            download_url=download_url,
            format=fmt,
        )
