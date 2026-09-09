import re
import logging
from decimal import Decimal, InvalidOperation
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)

# Base domain constants for SSRF prevention
CBE_BASE_DOMAIN = "mbreciept.cbe.com.et"
CBE_BASE_URL = f"https://{CBE_BASE_DOMAIN}"
CBE_API_BASE = "https://mb.cbe.com.et/api/v1/transactions/public/transaction-detail"

TELEBIRR_BASE_DOMAIN = "transactioninfo.ethiotelecom.et"
TELEBIRR_BASE_URL = f"https://{TELEBIRR_BASE_DOMAIN}"


class CBEBaseException(Exception):
    """Base exception for payment verification scraper errors."""
    pass


class CBEReceiptNotFoundException(CBEBaseException):
    """Raised when the receipt does not exist or returns 404 / Not Found."""
    pass


class CBEScraperFetchException(CBEBaseException):
    """Raised when network, connection, timeout, or server status issues occur."""
    pass


class CBEParseException(CBEBaseException):
    """Raised when parsing receipt HTML/JSON content fails unexpectedly."""
    pass


def clean_val(val_str):
    """Clean string values and return None if empty, dash, or N/A."""
    if val_str is None:
        return None
    cleaned = str(val_str).strip()
    if cleaned in ['-', 'N/A', 'null', 'None', '']:
        return None
    return cleaned


def extract_decimal(val_str):
    """Extract decimal monetary amount from strings like '130.00 ETB', '3 Birr', 'ETB0.50', or '130.00'."""
    if not val_str:
        return None
    cleaned = str(val_str).strip()
    if cleaned in ['-', 'N/A', 'null', 'None', '']:
        return None
    
    # Match number with optional decimal places
    match = re.search(r'([0-9]+(?:\.[0-9]+)?)', cleaned.replace(',', ''))
    if match:
        try:
            return str(Decimal(match.group(1)))
        except (InvalidOperation, ValueError):
            return None
    return None


def extract_currency(val_str):
    """Extract currency code from string like '130.00 ETB' or '3 Birr'."""
    if not val_str:
        return 'ETB'
    match = re.search(r'([A-Za-z]{3,4})', str(val_str))
    if match:
        code = match.group(1).upper()
        if code in ['BIRR', 'ETB']:
            return 'ETB'
        return code
    return 'ETB'


class CBEReceiptScraper:
    """
    Direct REST API client service for retrieving and parsing CBE receipt details from
    https://mb.cbe.com.et/api/v1/transactions/public/transaction-detail/{reference_id}.
    """

    def __init__(self, timeout=15):
        self.timeout = timeout

    def build_api_url(self, reference_id: str) -> str:
        """Construct target API URL."""
        clean_ref = reference_id.strip()
        return f"{CBE_API_BASE}/{clean_ref}"

    def scrape(self, reference_id: str) -> dict:
        """
        Fetch transaction detail directly from CBE Public API and parse response.
        Raises CBEReceiptNotFoundException if receipt is missing or not found.
        Raises CBEScraperFetchException if network or server error occurs.
        """
        clean_ref = reference_id.strip()
        api_data = self._fetch_via_cbe_api(clean_ref)
        return self._parse_api_response(api_data, clean_ref)

    def _fetch_via_cbe_api(self, reference_id: str) -> dict:
        api_url = self.build_api_url(reference_id)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://mbreciept.cbe.com.et/",
            "Origin": "https://mbreciept.cbe.com.et",
            "x-app-id": "d1292e42-7400-49de-a2d3-9731caa4c819",
            "x-app-version": "0a01980b-9859-1369-8198-59f403820000"
        }
        try:
            response = requests.get(api_url, headers=headers, timeout=self.timeout, verify=False)
            if response.status_code in [404, 400]:
                raise CBEReceiptNotFoundException(f"Receipt '{reference_id}' not found on CBE server.")
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception as json_err:
                    raise CBEParseException(f"Invalid JSON response from CBE server: {json_err}")

                if isinstance(data, dict):
                    if data.get("error") in ["Not Found", "Bad Request"] or data.get("status") in [404, 400]:
                        raise CBEReceiptNotFoundException(f"Receipt '{reference_id}' not found.")
                    if "debitAmount" in data or "amountCredited" in data or "id" in data:
                        return data
                raise CBEReceiptNotFoundException(f"Receipt '{reference_id}' data incomplete or not found.")
            
            raise CBEScraperFetchException(f"CBE server returned HTTP status code {response.status_code}.")
        except (CBEReceiptNotFoundException, CBEScraperFetchException, CBEParseException):
            raise
        except requests.RequestException as req_err:
            logger.error(f"Network error while connecting to CBE API for '{reference_id}': {req_err}")
            raise CBEScraperFetchException(f"Unable to reach CBE API server: {req_err}")
        except Exception as err:
            logger.error(f"Unexpected error calling CBE API for '{reference_id}': {err}")
            raise CBEScraperFetchException(f"Unexpected error during CBE API call: {err}")

    def _parse_api_response(self, data: dict, reference_id: str) -> dict:
        status_val = clean_val(data.get("status")) or "COMPLETED"
        ref_id = clean_val(data.get("id")) or reference_id

        company_data = {
            "name": "Commercial Bank of Ethiopia",
            "country": "Ethiopia",
            "city": "Addis Ababa",
            "address": "Ras Desta Damtew St, 01, Kirkos",
            "postal_code": "255",
            "swift_code": "CBETETAA",
            "email": "info@cbe.com.et",
            "telephone": "+251-551-50-04",
            "fax": "+251-551-45-22",
            "tin": "0000006966",
            "vat_receipt_no": ref_id,
            "vat_registration_no": "011140",
            "vat_registration_date": "01/01/2003",
        }

        customer_data = {
            "customer_name": clean_val(data.get("debitAccountHolder")),
            "region": None,
            "city": None,
            "sub_city": None,
            "wereda_kebele": None,
            "vat_registration_no": None,
            "vat_registration_date": None,
            "tin": None,
            "branch": None,
        }

        transferred_amt = extract_decimal(data.get("amountCredited") or data.get("debitAmount"))
        total_debited = extract_decimal(data.get("amountDebited") or data.get("amountDebitedWithCurrency"))
        service_charge = extract_decimal(data.get("serviceChargeValue") or data.get("totalChargeAmount"))
        vat = extract_decimal(data.get("vatValue") or data.get("totalTaxAmount"))
        disaster_fund = extract_decimal(data.get("drCharge"))
        currency = extract_currency(data.get("creditCurrency") or data.get("debitCurrency") or "ETB")

        # Extract date/time from dateTimes list or authDate / processingDate
        date_times_list = data.get("dateTimes")
        date_time_val = None
        if isinstance(date_times_list, list) and len(date_times_list) > 0 and date_times_list[0]:
            date_time_val = clean_val(date_times_list[0])
        if not date_time_val:
            date_time_val = clean_val(data.get("authDate") or data.get("processingDate"))

        # Extract payment reason / description
        payment_details = data.get("paymentDetails")
        reason_val = clean_val(data.get("description"))
        if not reason_val and isinstance(payment_details, list) and len(payment_details) > 0:
            reason_val = clean_val(payment_details[0])

        receiver_val = clean_val(
            data.get("creditAccountHolder") or
            data.get("receiver") or
            data.get("creditAccountName") or
            data.get("receiverName") or
            data.get("beneficiaryName")
        )

        payer_val = clean_val(data.get("debitAccountHolder") or data.get("payer"))

        transaction_data = {
            "payer": payer_val,
            "payer_account": clean_val(data.get("debitAccountNo")),
            "receiver": receiver_val,
            "receiver_account": clean_val(data.get("creditAccountNo")),
            "payment_type": clean_val(data.get("platformTransactionType") or data.get("transactionType")),
            "payment_date_time": date_time_val,
            "reference_no": ref_id,
            "reason": reason_val,
            "transferred_amount": transferred_amt,
            "service_charge": service_charge,
            "vat": vat,
            "disaster_risk_response_fund": disaster_fund,
            "total_amount_debited": total_debited,
            "currency": currency,
        }

        return {
            "status": status_val,
            "company": company_data,
            "customer": customer_data,
            "transaction": transaction_data,
        }


class TelebirrReceiptScraper:
    """
    Scraper service for retrieving and parsing Telebirr receipts from https://transactioninfo.ethiotelecom.et/receipt/{reference_id}.
    """

    def __init__(self, timeout=15):
        self.timeout = timeout

    def build_url(self, reference_id: str) -> str:
        clean_ref = reference_id.strip()
        return f"{TELEBIRR_BASE_URL}/receipt/{clean_ref}"

    def scrape(self, reference_id: str) -> dict:
        target_url = self.build_url(reference_id)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            response = requests.get(target_url, headers=headers, timeout=self.timeout, verify=False)
            if response.status_code == 404:
                raise CBEReceiptNotFoundException(f"Telebirr receipt '{reference_id}' was not found (HTTP 404).")
            if response.status_code == 200:
                return self.parse_receipt(response.text, reference_id)
            raise CBEScraperFetchException(f"Telebirr server returned HTTP status {response.status_code}.")
        except CBEReceiptNotFoundException:
            raise
        except CBEScraperFetchException:
            raise
        except Exception as err:
            logger.warning(f"Direct requests fetch failed for {target_url}: {err}. Trying Playwright fallback...")
            return self._fetch_with_playwright(reference_id)

    def _fetch_with_playwright(self, reference_id: str) -> dict:
        target_url = self.build_url(reference_id)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    ignore_https_errors=True
                )
                page = context.new_page()
                try:
                    res = page.goto(target_url, timeout=self.timeout * 1000, wait_until="networkidle")
                    if res and res.status == 404:
                        raise CBEReceiptNotFoundException(f"Telebirr receipt '{reference_id}' not found (HTTP 404).")
                    content = page.content()
                    if "404" in page.title() or "not found" in content.lower():
                        raise CBEReceiptNotFoundException(f"Telebirr receipt '{reference_id}' not found.")
                    return self.parse_receipt(content, reference_id)
                finally:
                    browser.close()
        except CBEReceiptNotFoundException:
            raise
        except Exception as e:
            raise CBEScraperFetchException(f"Unable to retrieve Telebirr receipt from server: {str(e)}")

    def parse_receipt(self, html_content: str, reference_id: str) -> dict:
        if not html_content or len(html_content.strip()) == 0:
            raise CBEParseException("Received empty HTML content from Telebirr receipt server.")

        soup = BeautifulSoup(html_content, 'html.parser')
        page_text = soup.get_text(separator="\n")

        kv_pairs = {}

        # 1. Parse 2-column or 3-column table rows
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                cols = [col.get_text().strip() for col in row.find_all(['td', 'th'])]
                if len(cols) == 2:
                    k = cols[0].split('/')[-1].rstrip(':').strip().lower()
                    v = cols[1].strip()
                    if k:
                        kv_pairs[k] = v

        # 2. Specific extraction for Telebirr 3-column invoice details table
        for row in soup.find_all('tr'):
            text = row.get_text()
            if reference_id in text or 'Birr' in text or '09-09-20' in text:
                cols = [col.get_text().strip() for col in row.find_all(['td', 'th']) if col.get_text().strip()]
                if len(cols) >= 3 and ('Birr' in cols[2] or re.search(r'\d', cols[2])):
                    kv_pairs['invoice no.'] = cols[0]
                    kv_pairs['payment date'] = cols[1]
                    kv_pairs['settled amount'] = cols[2]

        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        for i in range(len(lines)):
            line = lines[i]
            if '/' in line or ':' in line:
                key = line.split('/')[-1].rstrip(':').strip().lower()
                if i + 1 < len(lines):
                    val = lines[i+1].strip()
                    if key not in kv_pairs and not ('/' in val or ':' in val):
                        kv_pairs[key] = val

        def lookup(possible_keys, default=None):
            for k in possible_keys:
                k_lower = k.lower()
                for key_in_map, val in kv_pairs.items():
                    if k_lower in key_in_map:
                        return val
            return default

        settled_amt_raw = lookup(['settled amount', 'total paid amount'])
        payer_raw = lookup(['payer name'])

        # If essential transaction fields (settled amount or payer) are completely missing, the receipt does not exist
        if not settled_amt_raw and not payer_raw and not lookup(['invoice no.']):
            raise CBEReceiptNotFoundException(f"Telebirr receipt '{reference_id}' was not found.")

        status_val = clean_val(lookup(['transaction status', 'status'])) or "Completed"

        company_data = {
            "name": "Ethio telecom Share Company",
            "country": "Ethiopia",
            "city": "Addis Ababa",
            "address": clean_val(lookup(['p.o.box']) or "P.O.Box 1047 Addis Ababa, Ethiopia"),
            "postal_code": "1047",
            "swift_code": None,
            "email": "telebirr@ethionet.et",
            "telephone": clean_val(lookup(['tel .', 'tel']) or "251(0) 115 505 678"),
            "tin": clean_val(lookup(['tin no.']) or "0000030603"),
            "vat_receipt_no": reference_id,
            "vat_registration_no": clean_val(lookup(['vat reg. no.']) or "012700"),
            "vat_registration_date": clean_val(lookup(['vat reg. date']) or "01/01/2003"),
        }

        customer_data = {
            "customer_name": clean_val(payer_raw),
            "region": None,
            "city": None,
            "sub_city": None,
            "wereda_kebele": None,
            "vat_registration_no": clean_val(lookup(['payer vat reg. no'])),
            "vat_registration_date": clean_val(lookup(['payer vat reg. date'])),
            "tin": clean_val(lookup(['payer tin no'])),
            "branch": None,
        }

        service_fee_raw = lookup(['service fee'])
        vat_raw = lookup(['15% vat', '15% ተ.እ.ታ/vat'])

        transaction_data = {
            "payer": clean_val(payer_raw),
            "payer_account": clean_val(lookup(['payer telebirr no.'])),
            "receiver": clean_val(lookup(['credited party name', 'credited party', 'receiver', 'receiver name', 'recipient', 'beneficiary'])),
            "receiver_account": clean_val(lookup(['credited party account no'])),
            "payment_type": clean_val(lookup(['payment mode']) or "telebirr"),
            "payment_date_time": clean_val(lookup(['payment date'])),
            "reference_no": clean_val(lookup(['invoice no.'])) or reference_id,
            "reason": clean_val(lookup(['payment reason'])),
            "transferred_amount": extract_decimal(settled_amt_raw),
            "service_charge": extract_decimal(service_fee_raw) or "0.00",
            "vat": extract_decimal(vat_raw) or "0.00",
            "disaster_risk_response_fund": None,
            "total_amount_debited": extract_decimal(lookup(['total paid amount']) or settled_amt_raw),
            "currency": "ETB",
        }

        return {
            "status": status_val,
            "company": company_data,
            "customer": customer_data,
            "transaction": transaction_data,
        }


def get_scraper_for_bank(bank_code: str):
    """Factory helper returning appropriate scraper class for given bank code."""
    clean_bank = (bank_code or 'cbe').lower().strip()
    if clean_bank == 'telebirr':
        return TelebirrReceiptScraper()
    return CBEReceiptScraper()
