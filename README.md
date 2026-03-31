# Sweden-CVR-Pull

A Python tool for retrieving and structuring company financial data in Sweden using Bolagsverket's APIs and deterministic iXBRL parsing.

## Features

- **Company lookup** by Swedish organization number
- **Industry search** by NACE/SNI code — retrieve all matching companies
- **Local iXBRL parsing** — parse annual report files directly without API access
- **Deterministic extraction** of financial facts from iXBRL filings (no LLM-based summarization)
- **Swedish number format handling** — spaces as thousands separators, comma decimals, parenthetical negatives, scale factors
- **80+ taxonomy mappings** covering K2, K3, and SE-GEN-BASE Swedish XBRL taxonomies
- **Calculated fields** — COGS, gross profit, EBIT, EBITDA derived from extracted data
- **Full traceability** — every value links back to its XBRL concept, context, unit, and source file
- **Dual export** — JSON (with fact-level detail) and formatted Excel
- **Rate limiting and retry logic** with exponential backoff on all API calls

## Installation

```bash
git clone https://github.com/jonasklussmann-droid/Sweden-CVR-Pull.git
cd Sweden-CVR-Pull
pip install -r requirements.txt
```

### Optional dependency

The `ixbrlparse` library can be used as a fallback parser. It requires `word2number`, which may fail to build on some systems. The tool works without it using its built-in BeautifulSoup/lxml parser.

```bash
pip install ixbrlparse  # optional
```

## Configuration

The tool uses OAuth2 Client Credentials to authenticate with Bolagsverket's API. Default credentials are built in, but you can override them:

```bash
python main.py --org-number 5560001234 \
    --client-id YOUR_CLIENT_ID \
    --client-secret YOUR_CLIENT_SECRET
```

| Parameter        | Default                           |
|------------------|-----------------------------------|
| Token endpoint   | `https://portal.api.bolagsverket.se/oauth2/token` |
| Client ID        | Built-in (from Bolagsverket)      |
| Client Secret    | Built-in (from Bolagsverket)      |
| Rate limit       | 15 requests/second                |

## Usage

### Look up a company by organization number

```bash
python main.py --org-number 5560001234
```

### Search by NACE/SNI industry code

```bash
python main.py --nace-code 62010 --max-companies 50
```

### Specify a fiscal year

```bash
python main.py --org-number 5560001234 --fiscal-year 2024
```

### Parse a local iXBRL file

```bash
python main.py --ixbrl-file path/to/annual_report.xhtml
```

### All CLI options

| Flag                | Short | Description                                      | Default              |
|---------------------|-------|--------------------------------------------------|----------------------|
| `--org-number`      | `-o`  | Swedish organization number                      | —                    |
| `--nace-code`       | `-n`  | NACE/SNI industry code                           | —                    |
| `--ixbrl-file`      | `-f`  | Path to a local iXBRL file                       | —                    |
| `--fiscal-year`     | `-y`  | Fiscal year filter (e.g., 2024)                  | All available        |
| `--max-companies`   | `-m`  | Max companies for NACE search                    | 100                  |
| `--output-dir`      | `-d`  | Output directory                                 | `output`             |
| `--output-name`     |       | Base filename for exports                        | `swedish_financials` |
| `--client-id`       |       | OAuth2 client ID override                        | Built-in             |
| `--client-secret`   |       | OAuth2 client secret override                    | Built-in             |
| `--verbose`         | `-v`  | Enable debug logging                             | Off                  |
| `--json-only`       |       | Skip Excel export                                | Off                  |

## Output

The tool produces two output files in the `output/` directory:

- **`swedish_financials.json`** — full data with fact-level traceability
- **`swedish_financials.xlsx`** — formatted Excel workbook with headers, filters, and number formatting

### Sample JSON structure

```json
{
  "metadata": {
    "total_records": 1,
    "export_format": "json",
    "schema_version": "1.0"
  },
  "data": [
    {
      "company_name": "Example AB",
      "org_number": "5560001234",
      "nace_code": "62010",
      "fiscal_year": "2024",
      "period_start": "2024-01-01",
      "period_end": "2024-12-31",
      "currency": "SEK",
      "net_sales": 15000000,
      "operating_profit": 2500000,
      "ebit": 2500000,
      "ebitda": 3200000,
      "net_income": 1900000,
      "source_filing": "12345",
      "_facts": [
        {
          "concept": "se-gen-base:Nettoomsattning",
          "value": 15000000,
          "context_id": "period0",
          "unit": "SEK",
          "period_start": "2024-01-01",
          "period_end": "2024-12-31",
          "scale": 0
        }
      ]
    }
  ]
}
```

## Architecture

```
sweden_cvr/
├── __init__.py         Package init
├── models.py           Data models: CompanyInfo, XBRLFact, FinancialData, DocumentInfo
├── auth.py             OAuth2 Client Credentials with token caching and retry
├── api_client.py       Bolagsverket API wrapper (company search + document retrieval)
├── taxonomy.py         Swedish XBRL concept → normalized field mapping (80+ entries)
├── ixbrl_parser.py     Deterministic iXBRL parser with Swedish number handling
├── pipeline.py         End-to-end orchestration: discover → retrieve → parse → normalize
└── export.py           JSON and Excel export with formatting and traceability
main.py                 CLI entry point
requirements.txt        Python dependencies
```

### Pipeline flow

```
Input (org number / NACE code)
  │
  ├─ Company Discovery (Bolagsverket API)
  │    └─ search by org number or SNI code
  │
  ├─ Document Retrieval
  │    └─ fetch annual report metadata and iXBRL content
  │
  ├─ iXBRL Parsing
  │    ├─ extract contexts (periods, entities)
  │    ├─ extract units (currencies)
  │    └─ extract numeric facts (concept, value, scale, sign)
  │
  ├─ Taxonomy Mapping
  │    └─ map XBRL concepts → normalized financial fields
  │
  ├─ Normalization
  │    ├─ apply scale factors to get absolute SEK values
  │    └─ calculate derived fields (COGS, gross profit, EBITDA)
  │
  └─ Export (JSON + Excel)
```

## Financial Fields

| Field                          | Swedish Term                                        | XBRL Concept Examples                |
|--------------------------------|-----------------------------------------------------|--------------------------------------|
| `net_sales`                    | Nettoomsättning                                     | Nettoomsattning                      |
| `revenue`                      | Omsättning / Rörelseintäkter                        | Omsattning, Rorelseintakter          |
| `other_operating_income`       | Övriga rörelseintäkter                              | OvrigaRorelseintakter                |
| `change_in_inventory`          | Förändring av lager                                 | ForandringAvLager                    |
| `raw_materials_and_consumables`| Råvaror och förnödenheter                           | RavarorOchFornodenheter              |
| `trade_goods` (COGS)           | Handelsvaror                                        | Handelsvaror, KostnadForHandelsvaror |
| `other_external_costs`         | Övriga externa kostnader                            | OvrigaExternaKostnader               |
| `personnel_costs`              | Personalkostnader                                   | Personalkostnader                    |
| `depreciation_amortization`    | Avskrivningar                                       | Avskrivningar                        |
| `other_operating_expenses`     | Övriga rörelsekostnader                             | OvrigaRorelsekostnader               |
| `operating_profit`             | Rörelseresultat (= EBIT)                            | Rorelseresultat                      |
| `financial_income`             | Finansiella intäkter                                | FinansiellaIntakter                  |
| `financial_costs`              | Finansiella kostnader                               | FinansiellaKostnader                 |
| `result_after_financial_items` | Resultat efter finansiella poster                   | ResultatEfterFinansiellaPoster       |
| `tax`                          | Skatt på årets resultat                             | SkattPaArsResultat                   |
| `net_income`                   | Årets resultat                                      | ArsResultat, AretsResultat           |
| `cogs` (calculated)            | Kostnad sålda varor                                 | Derived from raw materials + trade goods |
| `gross_profit` (calculated)    | Bruttovinst                                         | net_sales + cogs                     |
| `ebit` (calculated)            | EBIT                                                | = operating_profit                   |
| `ebitda` (calculated)          | EBITDA                                              | ebit - depreciation                  |

## Taxonomy Mapping

The `taxonomy.py` module maps over 80 XBRL concept name variants to normalized fields. It handles:

- **Namespace stripping**: `se-gen-base:Nettoomsattning` → `nettoomsattning`
- **Swedish character variants**: both `ö/ä/å` and ASCII-equivalent forms
- **Multiple taxonomy sources**: K2, K3, and SE-GEN-BASE
- **Case-insensitive matching**

To add new concept mappings, edit the `CONCEPT_TO_FIELD` dictionary in `sweden_cvr/taxonomy.py`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `401 Unauthorized` from API | Check client ID/secret. Token may have expired — the tool auto-refreshes. |
| `404 Not Found` for a company | The org number may be invalid or the company may not have digital filings. |
| No financial data extracted | The filing may use non-standard XBRL concepts. Run with `--verbose` and check which concepts were found. |
| `ixbrlparse` install fails | This is optional. The built-in parser handles Swedish filings. Skip it. |
| Values seem too large/small | Check the `scale` field in the JSON `_facts` array. Scale 3 = thousands, 6 = millions. |
| Empty Excel file | Ensure the API returned iXBRL content, not PDF. Check logs with `--verbose`. |
