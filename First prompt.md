You are tasked with designing and implementing a production-quality Python tool for retrieving and structuring company financial data in Sweden using Bolagsverket’s APIs and iXBRL filings.
Objective
Build a robust Python application that allows a user to input either:
a NACE industry code, or
a Swedish organization number
and returns all matching companies in Sweden, along with structured financial data extracted from their annual reports.
The system must prioritize accurate, deterministic extraction of financial data from iXBRL filings, not LLM-based summarization.
Data Access & Authentication
Use Bolagsverket’s APIs for “värdefulla datamängder”.
OAuth2 Client Credentials Grant:
https://datatracker.ietf.org/doc/html/rfc6749#section-4.4
Token endpoint:
https://portal.api.bolagsverket.se/oauth2/token
API documentation:
https://portal.api.bolagsverket.se/devportal/apis
Credentials:
Client ID: JHaroftNWikb62Kp2Jg9x47NCTwa
Client Secret: XqzGieoJT32fMOmFy_uU7jd2Lsga
Core Workflow
Your system should implement the following pipeline:
Company Discovery
If input is a NACE code:
Retrieve all companies in Sweden matching that industry classification
If input is company name or org number:
Resolve to a specific company
Document Retrieval
For each company:
Retrieve available documents from Bolagsverket
Identify annual reports for a requested fiscal year
Document Processing
Download the relevant filing package
Inspect contents and detect format:
Prefer iXBRL/XHTML
Handle fallback formats if needed
iXBRL Parsing (Critical Component)
Parse iXBRL using deterministic logic
Extract financial facts with:
concept/tag
context (period)
unit
value
source reference
Data Normalization
Map extracted taxonomy concepts into a normalized schema
It is very important we consider the relevant taxonomy / methodology. Ideally, we want to extract fianncails from the reports similarily across all companies, so we follow the same structured method.
We should also make sure we consider scale and currency for all, so we get the financial values in absolute values and in SEK.
Required Output Schema
For each company and fiscal year, return structured data including as many of the following fields as possible:
company_name
org_number
nace_code
fiscal_year
period_start
period_end
currency
Financials:
revenue
net_sales
other_operating_income
operating_profit
EBIT
EBITDA
COGS ("Handelsvarer" or other relevant categories in sweden)
Gross profit which we can calculate ourselves
(Design the system to be extensible for additional fields.)
Output Formats
Primary: JSON
An excel file containing all the financials
Each record must preserve full traceability, including:
original filing reference
XBRL concept/tag
context ID
unit
source file
Technical Requirements
Use Python
Modular architecture (API client, parsing engine, data model, pipeline)
Robust error handling (missing filings, malformed iXBRL, API failures)
Rate limiting and retry logic
Logging for traceability and debugging
Configurable inputs (year, NACE code, etc.)
