# CBE Payment Verification API (Django REST Framework)

A complete **Django REST Framework (DRF)** payment verification API for verifying Commercial Bank of Ethiopia (CBE) payment receipts.

The API dynamically visits the CBE receipt website at `https://mbreciept.cbe.com.et/{reference_id}`, extracts the receipt information, and verifies that the requested reference number and transferred amount match the external receipt.

---

## Features

- **Dynamic CBE Receipt Scraping**: Retrieves receipt data using direct REST API calls with fallback to Playwright headless browser for JavaScript execution.
- **One-Time Verification & Duplicate Prevention**: A receipt reference can only be verified ONCE. Registrations ONLY occur when verification completely succeeds (`verified == true`). Failed attempts (e.g. bank down, wrong amount, not found) are NOT marked as used.
- **Strict Amount Verification**: Matches requested amount against **Transferred Amount** (`transferred_amount`), avoiding service charges or total debited amounts.
- **Monetary Precision**: Uses Python `Decimal` for currency precision.
- **Detailed Verification Flags**: Returns distinct `reference_verified`, `amount_verified`, and `already_used` indicators.
- **Robust Exception Handling**: Gracefully handles network timeouts, missing fields, non-existent references, and parsing edge cases without exposing internal stack traces.
- **DRF Browsable API**: Fully interactive test UI accessible via web browser.
- **Security & SSRF Prevention**: Restricts target domain strictly to `mbreciept.cbe.com.et` and sanitizes input reference IDs against path traversal.

---

## Requirements & Prerequisites

- Python 3.10+
- Django 6.x / 5.x
- Django REST Framework
- Requests
- BeautifulSoup4
- Playwright

---

## Installation & Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd PaymentVerification
   ```

2. **Activate your virtual environment**:
   - On Windows (PowerShell):
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - On Linux/macOS:
     ```bash
     source venv/bin/activate
     ```

3. **Install Dependencies**:
   ```bash
   pip install django djangorestframework requests beautifulsoup4 playwright
   playwright install chromium
   ```

4. **Run Database Migrations**:
   ```bash
   python manage.py makemigrations payments
   python manage.py migrate
   ```

5. **Verify System Setup**:
   ```bash
   python manage.py check
   ```

6. **Start the Django Development Server**:
   ```bash
   python manage.py runserver
   ```

---

## Testing via DRF Browsable API

Open your web browser and navigate to:

`http://127.0.0.1:8000/api/payments/verify/`

The **Django REST Framework Browsable API** interface will load.

In the raw data / HTML form box at the bottom of the page, enter:

```json
{
    "reference_id": "v2-hfHCxGVTzbgxUAOvvyEt",
    "amount": 130.00
}
```

Click **POST** to execute the request.

---

## API Usage & Examples

### Endpoint

- **URL**: `/api/payments/verify/`
- **Method**: `POST`
- **Content-Type**: `application/json`

### Example Request (`curl`)

```bash
curl -X POST http://127.0.0.1:8000/api/payments/verify/ \
  -H "Content-Type: application/json" \
  -d '{
    "reference_id": "v2-hfHCxGVTzbgxUAOvvyEt",
    "amount": 130.00
  }'
```

### 1. Successful First Verification Response (HTTP 200)

```json
{
    "success": true,
    "verified": true,
    "already_used": false,
    "reference_id": "v2-hfHCxGVTzbgxUAOvvyEt",
    "reference_verified": true,
    "amount_verified": true,
    "requested_amount": "130.00",
    "verified_amount": "130.00",
    "currency": "ETB",
    "receipt": {
        "status": "COMPLETED",
        "company": {
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
            "vat_receipt_no": "FT26251VNGGM",
            "vat_registration_no": "011140",
            "vat_registration_date": "01/01/2003"
        },
        "customer": {
            "customer_name": "Beimnet Melese Kebede",
            "region": null,
            "city": null,
            "sub_city": null,
            "wereda_kebele": null,
            "vat_registration_no": null,
            "vat_registration_date": null,
            "tin": null,
            "branch": null
        },
        "transaction": {
            "payer": "Beimnet Melese Kebede",
            "payer_account": "1****3718",
            "receiver": "Fasika Addis Wubet",
            "receiver_account": "1****3937",
            "payment_type": "A2A",
            "payment_date_time": "20260908",
            "reference_no": "FT26251VNGGM",
            "reason": "MB Transfer",
            "transferred_amount": "130.00",
            "service_charge": "0.50",
            "vat": "0.08",
            "disaster_risk_response_fund": "0.03",
            "total_amount_debited": "130.61",
            "currency": "ETB"
        }
    }
}
```

### 2. Duplicate / Already Verified Response (HTTP 200)

If the user attempts to send the same reference number a 2nd time:

```json
{
    "success": true,
    "verified": false,
    "already_used": true,
    "reference_id": "v2-hfHCxGVTzbgxUAOvvyEt",
    "reference_verified": true,
    "amount_verified": false,
    "requested_amount": "130.00",
    "verified_amount": "130.00",
    "currency": "ETB",
    "message": "This receipt reference has already been used and verified."
}
```

### 3. Mismatched Amount Response (HTTP 200)

```json
{
    "success": true,
    "verified": false,
    "already_used": false,
    "reference_id": "v2-hfHCxGVTzbgxUAOvvyEt",
    "reference_verified": true,
    "amount_verified": false,
    "requested_amount": "150.00",
    "verified_amount": "130.00",
    "currency": "ETB",
    "message": "Payment amount does not match the receipt."
}
```

### 4. Receipt Not Found Response (HTTP 404)

```json
{
    "success": false,
    "verified": false,
    "already_used": false,
    "reference_id": "nonexistent-id",
    "message": "Unable to find or retrieve the CBE receipt."
}
```

---

## Running Automated Tests

Run the test suite:

```bash
python manage.py test payments
```

The test suite covers:
1. Valid reference + correct amount.
2. Valid reference + incorrect amount.
3. Invalid reference ID.
4. Missing reference ID.
5. Missing amount.
6. Invalid / negative amount.
7. CBE receipt server failure / network timeout.
8. Receipt with missing optional fields.
9. Decimal / monetary precision logic (`transferred_amount` vs `total_amount_debited`).
10. Complete verification JSON response structure compliance.
11. One-time verification & duplicate payment prevention (`already_used: true`).
12. Verification catch test (ensuring failed / un-responded attempts are NOT marked as used).
