#!/usr/bin/env python3
"""Swedish Company Financial Data Tool.

Retrieves and structures company financial data from Bolagsverket's APIs
and iXBRL filings.

Usage:
    # Look up a single company by org number
    python main.py --org-number 5560001234

    # Search by NACE/SNI code
    python main.py --nace-code 62010

    # Specify fiscal year
    python main.py --org-number 5560001234 --fiscal-year 2024

    # Custom output directory
    python main.py --org-number 5560001234 --output-dir results

    # Parse a local iXBRL file directly
    python main.py --ixbrl-file report.xhtml
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from sweden_cvr.export import export_all
from sweden_cvr.ixbrl_parser import extract_financials
from sweden_cvr.pipeline import FinancialDataPipeline


def setup_logging(verbose: bool = False):
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Reduce noise from urllib3
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def parse_local_ixbrl(file_path: str, fiscal_year: str | None = None):
    """Parse a local iXBRL file and return financial data."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    content = path.read_bytes()
    financial = extract_financials(content, source_file=path.name, fiscal_year=fiscal_year)
    return [financial]


def main():
    parser = argparse.ArgumentParser(
        description="Swedish Company Financial Data Tool - Bolagsverket API & iXBRL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--org-number", "-o",
        help="Swedish organization number (e.g., 5560001234)",
    )
    input_group.add_argument(
        "--nace-code", "-n",
        help="NACE/SNI industry code (e.g., 62010)",
    )
    input_group.add_argument(
        "--ixbrl-file", "-f",
        help="Path to a local iXBRL file to parse directly",
    )

    # Options
    parser.add_argument(
        "--fiscal-year", "-y",
        help="Fiscal year to retrieve (e.g., 2024)",
    )
    parser.add_argument(
        "--max-companies", "-m",
        type=int, default=100,
        help="Maximum companies to process for NACE code search (default: 100)",
    )
    parser.add_argument(
        "--output-dir", "-d",
        default="output",
        help="Output directory (default: output)",
    )
    parser.add_argument(
        "--output-name",
        default="swedish_financials",
        help="Base name for output files (default: swedish_financials)",
    )
    parser.add_argument(
        "--client-id",
        help="OAuth2 client ID (default: built-in credentials)",
    )
    parser.add_argument(
        "--client-secret",
        help="OAuth2 client secret (default: built-in credentials)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Output JSON only (skip Excel)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger(__name__)

    # Handle local iXBRL file parsing
    if args.ixbrl_file:
        logger.info("Parsing local iXBRL file: %s", args.ixbrl_file)
        results = parse_local_ixbrl(args.ixbrl_file, args.fiscal_year)
    else:
        # Build pipeline with API credentials
        kwargs = {}
        if args.client_id:
            kwargs["client_id"] = args.client_id
        if args.client_secret:
            kwargs["client_secret"] = args.client_secret

        pipeline = FinancialDataPipeline(**kwargs)

        if args.org_number:
            results = pipeline.process_org_number(args.org_number, args.fiscal_year)
        else:
            results = pipeline.process_nace_code(
                args.nace_code,
                fiscal_year=args.fiscal_year,
                max_companies=args.max_companies,
            )

    if not results:
        logger.warning("No financial data retrieved.")
        print("No financial data was retrieved. Check the logs for details.")
        sys.exit(1)

    # Export results
    if args.json_only:
        from sweden_cvr.export import export_to_json
        json_path = export_to_json(results, f"{args.output_dir}/{args.output_name}.json")
        print(f"\nExported {len(results)} record(s) to: {json_path}")
    else:
        paths = export_all(results, args.output_dir, args.output_name)
        print(f"\nExported {len(results)} record(s):")
        for fmt, path in paths.items():
            print(f"  {fmt.upper()}: {path}")

    # Print summary to stdout
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"\n  Company: {r.company_name or 'N/A'}")
        print(f"  Org Number: {r.org_number or 'N/A'}")
        print(f"  Fiscal Year: {r.fiscal_year or 'N/A'}")
        print(f"  Period: {r.period_start} to {r.period_end}")
        print(f"  Currency: {r.currency}")
        if r.net_sales is not None:
            print(f"  Net Sales: {r.net_sales:,.0f} {r.currency}")
        if r.revenue is not None:
            print(f"  Revenue: {r.revenue:,.0f} {r.currency}")
        if r.operating_profit is not None:
            print(f"  Operating Profit: {r.operating_profit:,.0f} {r.currency}")
        if r.ebit is not None:
            print(f"  EBIT: {r.ebit:,.0f} {r.currency}")
        if r.ebitda is not None:
            print(f"  EBITDA: {r.ebitda:,.0f} {r.currency}")
        if r.gross_profit is not None:
            print(f"  Gross Profit: {r.gross_profit:,.0f} {r.currency}")
        if r.net_income is not None:
            print(f"  Net Income: {r.net_income:,.0f} {r.currency}")
    print(f"\n{'='*60}")


if __name__ == "__main__":
    main()
