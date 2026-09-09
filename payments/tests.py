from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from payments.models import PaymentVerification
from payments.scraper import (
    CBEReceiptScraper,
    TelebirrReceiptScraper,
    CBEReceiptNotFoundException,
    CBEScraperFetchException,
)

RAW_CBE_API_JSON_SAMPLE = {
    "id": "FT262535PZWX",
    "transactionType": "ACNX",
    "debitAccountNo": "1********3718",
    "currencyMktDr": "1",
    "debitCurrency": "ETB",
    "debitAmount": "10000.00",
    "debitValueDate": "20260910",
    "debitTheirRef": "MB Transfer",
    "creditTheirRef": "MB Transfer",
    "creditAccountNo": "1********8597",
    "creditCurrency": "ETB",
    "creditValueDate": "20260910",
    "processingDate": "20260910",
    "paymentDetails": [
        "MB Transfer"
    ],
    "chargeComDisplay": "NO",
    "commissionCode": "Debit Plus Charges",
    "commissionTypes": [
        {
            "commissionType": "COMFTMB",
            "commissionAmt": "ETB2.00"
        },
        {
            "commissionType": "DISASRECOV",
            "commissionAmt": "ETB0.10"
        }
    ],
    "chargeCode": "WAIVE",
    "positionType": "TR",
    "taxTypes": [
        {
            "taxType": "15",
            "taxAmt": "ETB0.30"
        }
    ],
    "amountDebitedWithCurrency": "ETB10002.40",
    "amountCreditedWithCurrency": "ETB10000.00",
    "totalChargeAmountWithCurrency": "ETB2.40",
    "totalTaxAmountWithCurrency": "ETB0.30",
    "amountDebited": "10002.40",
    "amountCredited": "10000.00",
    "totalChargeAmount": "2.40",
    "totalTaxAmount": "0.30",
    "totRecComm": "0",
    "totRecCommLcl": "0",
    "totRecChg": "0",
    "totRecChgLcl": "0",
    "rateFixing": "NO",
    "authDate": "20260910",
    "roundType": "NATURAL",
    "currNo": "1",
    "dateTimes": [
        "2026-09-09T18:22:00Z"
    ],
    "creditAccountHolder": "Beimnet Melese Kebede",
    "debitAccountHolder": "Robel Seifu Sima",
    "encodedReceipt": "https://mbreciept.cbe.com.et/v2-hfHCxGWmb5NOD1F7CVxh",
    "isPlatformTransaction": True,
    "channel": "ANDROID",
    "platformTransactionType": "A2A",
    "isOtherBank": False,
    "description": "MB Transfer",
    "serviceChargeValue": "ETB 2.00",
    "vatValue": "ETB 0.30",
    "drCharge": "ETB 0.10",
    "chargeDescription": "Service charge of ETB 2.00 and VAT(15%) of ETB 0.30 and Disaster Recovery(5%) of ETB 0.10 with total charge of ETB 2.40.",
    "status": "COMPLETED"
}

SAMPLE_CBE_RECEIPT_DATA = {
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
        "customer_name": "Robel Seifu Sima",
        "region": None,
        "city": None,
        "sub_city": None,
        "wereda_kebele": None,
        "vat_registration_no": None,
        "vat_registration_date": None,
        "tin": None,
        "branch": None
    },
    "transaction": {
        "payer": "Robel Seifu Sima",
        "payer_account": "1****3718",
        "receiver": "Beimnet Melese Kebede",
        "receiver_account": "1********3718",
        "payment_type": "A2A",
        "payment_date_time": "2026-09-09T18:22:00Z",
        "reference_no": "FT26251VNGGM",
        "reason": "MB Transfer",
        "transferred_amount": "130.00",
        "service_charge": "2.00",
        "vat": "0.30",
        "disaster_risk_response_fund": "0.10",
        "total_amount_debited": "132.40",
        "currency": "ETB"
    }
}

SAMPLE_TELEBIRR_RECEIPT_DATA = {
    "status": "Completed",
    "company": {
        "name": "Ethio telecom Share Company",
        "country": "Ethiopia",
        "city": "Addis Ababa",
        "address": "P.O.Box 1047 Addis Ababa, Ethiopia",
        "postal_code": "1047",
        "swift_code": None,
        "email": "telebirr@ethionet.et",
        "telephone": "251(0) 115 505 678",
        "tin": "0000030603",
        "vat_receipt_no": "DI91KG3JZN",
        "vat_registration_no": "012700",
        "vat_registration_date": "01/01/2003"
    },
    "customer": {
        "customer_name": "Beimnet Melese Kebede",
        "region": None,
        "city": None,
        "sub_city": None,
        "wereda_kebele": None,
        "vat_registration_no": None,
        "vat_registration_date": None,
        "tin": None,
        "branch": None
    },
    "transaction": {
        "payer": "Abebe Bikila",
        "payer_account": "2519****9350",
        "receiver": "Beimnet Melese Kebede",
        "receiver_account": "2519****9350",
        "payment_type": "telebirr",
        "payment_date_time": "09-09-2026 01:18:26",
        "reference_no": "DI91KG3JZN",
        "reason": "CRM Buy Package Mini APP",
        "transferred_amount": "3.00",
        "service_charge": "0.00",
        "vat": "0.00",
        "disaster_risk_response_fund": None,
        "total_amount_debited": "3.00",
        "currency": "ETB"
    }
}


class CBEReceiptScraperDirectAPITests(APITestCase):

    @patch('payments.scraper.requests.get')
    def test_cbe_direct_api_success_parsing(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = RAW_CBE_API_JSON_SAMPLE
        mock_requests_get.return_value = mock_response

        scraper = CBEReceiptScraper()
        result = scraper.scrape("v2-hfHCxGWmb5NOBYpBHvct")

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["transaction"]["reference_no"], "FT262535PZWX")
        self.assertEqual(result["transaction"]["transferred_amount"], "10000.00")
        self.assertEqual(result["transaction"]["total_amount_debited"], "10002.40")
        self.assertEqual(result["transaction"]["receiver"], "Beimnet Melese Kebede")
        self.assertEqual(result["transaction"]["receiver_account"], "1********8597")
        self.assertEqual(result["transaction"]["payer"], "Robel Seifu Sima")
        self.assertEqual(result["transaction"]["payment_type"], "A2A")
        self.assertEqual(result["transaction"]["service_charge"], "2.00")
        self.assertEqual(result["transaction"]["vat"], "0.30")
        self.assertEqual(result["transaction"]["disaster_risk_response_fund"], "0.10")

    @patch('payments.scraper.requests.get')
    def test_cbe_direct_api_not_found(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_requests_get.return_value = mock_response

        scraper = CBEReceiptScraper()
        with self.assertRaises(CBEReceiptNotFoundException):
            scraper.scrape("NON_EXISTENT_REF")

    @patch('payments.scraper.requests.get')
    def test_cbe_direct_api_server_error(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_requests_get.return_value = mock_response

        scraper = CBEReceiptScraper()
        with self.assertRaises(CBEScraperFetchException):
            scraper.scrape("REF500")


class PaymentVerificationAPITests(APITestCase):

    def setUp(self):
        self.url = reverse('payments:verify-payment')
        self.valid_cbe_payload = {
            "bank": "cbe",
            "reference_id": "v2-hfHCxGVTzbgxUAOvvyEt",
            "amount": 130.00
        }
        self.valid_telebirr_payload = {
            "bank": "telebirr",
            "reference_id": "DI91KG3JZN",
            "amount": 3.00
        }

    # Test Case 1: Valid CBE reference + correct amount + matching receiver name & account
    @patch.object(CBEReceiptScraper, 'scrape', return_value=SAMPLE_CBE_RECEIPT_DATA)
    def test_valid_cbe_verification(self, mock_scrape):
        response = self.client.post(self.url, self.valid_cbe_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertTrue(data['verified'])
        self.assertFalse(data['already_used'])
        self.assertEqual(data['bank'], 'cbe')
        self.assertTrue(data['reference_verified'])
        self.assertTrue(data['amount_verified'])
        self.assertTrue(data['receiver_name_verified'])
        self.assertTrue(data['receiver_account_verified'])
        self.assertTrue(data['receiver_verified'])
        self.assertEqual(data['expected_receiver'], "Beimnet Melese Kebede")
        self.assertEqual(data['verified_receiver'], "Beimnet Melese Kebede")
        self.assertEqual(data['expected_receiver_account'], "1********3718")
        self.assertEqual(data['verified_receiver_account'], "1********3718")

    # Test Case 2: Valid Telebirr reference + correct amount + matching credited party name & account
    @patch.object(TelebirrReceiptScraper, 'scrape', return_value=SAMPLE_TELEBIRR_RECEIPT_DATA)
    def test_valid_telebirr_verification(self, mock_scrape):
        response = self.client.post(self.url, self.valid_telebirr_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertTrue(data['verified'])
        self.assertFalse(data['already_used'])
        self.assertEqual(data['bank'], 'telebirr')
        self.assertTrue(data['reference_verified'])
        self.assertTrue(data['amount_verified'])
        self.assertTrue(data['receiver_name_verified'])
        self.assertTrue(data['receiver_account_verified'])
        self.assertTrue(data['receiver_verified'])
        self.assertEqual(data['expected_receiver_account'], "2519****9350")
        self.assertEqual(data['verified_receiver_account'], "2519****9350")

    # Test Case 3: Telebirr amount mismatch
    @patch.object(TelebirrReceiptScraper, 'scrape', return_value=SAMPLE_TELEBIRR_RECEIPT_DATA)
    def test_telebirr_amount_mismatch(self, mock_scrape):
        payload = {
            "bank": "telebirr",
            "reference_id": "DI91KG3JZN",
            "amount": 50.00
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertFalse(data['verified'])
        self.assertFalse(data['amount_verified'])
        self.assertTrue(data['receiver_verified'])
        self.assertEqual(data['verified_amount'], "3.00")
        self.assertIn("expected '50.00', got '3.00'", data['message'])

    # Test Case 4: CBE Receiver Name Mismatch
    @patch.object(CBEReceiptScraper, 'scrape')
    def test_cbe_receiver_name_mismatch(self, mock_scrape):
        wrong_receiver_data = {
            **SAMPLE_CBE_RECEIPT_DATA,
            "transaction": {
                **SAMPLE_CBE_RECEIPT_DATA["transaction"],
                "receiver": "Fasika Addis Wubet"
            }
        }
        mock_scrape.return_value = wrong_receiver_data

        response = self.client.post(self.url, self.valid_cbe_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertFalse(data['verified'])
        self.assertTrue(data['reference_verified'])
        self.assertTrue(data['amount_verified'])
        self.assertFalse(data['receiver_name_verified'])
        self.assertFalse(data['receiver_verified'])
        self.assertIn("Receiver name mismatch (expected 'Beimnet Melese Kebede', got 'Fasika Addis Wubet')", data['message'])

    # Test Case 5: CBE Receiver Account Mismatch
    @patch.object(CBEReceiptScraper, 'scrape')
    def test_cbe_receiver_account_mismatch(self, mock_scrape):
        wrong_account_data = {
            **SAMPLE_CBE_RECEIPT_DATA,
            "transaction": {
                **SAMPLE_CBE_RECEIPT_DATA["transaction"],
                "receiver_account": "1********9999"
            }
        }
        mock_scrape.return_value = wrong_account_data

        response = self.client.post(self.url, self.valid_cbe_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertFalse(data['verified'])
        self.assertTrue(data['receiver_name_verified'])
        self.assertFalse(data['receiver_account_verified'])
        self.assertFalse(data['receiver_verified'])
        self.assertIn("Receiver account mismatch (expected '1********3718', got '1********9999')", data['message'])

    # Test Case 6: Telebirr Credited Party Name Mismatch
    @patch.object(TelebirrReceiptScraper, 'scrape')
    def test_telebirr_credited_party_mismatch(self, mock_scrape):
        wrong_receiver_data = {
            **SAMPLE_TELEBIRR_RECEIPT_DATA,
            "transaction": {
                **SAMPLE_TELEBIRR_RECEIPT_DATA["transaction"],
                "receiver": "Ethio telecom"
            }
        }
        mock_scrape.return_value = wrong_receiver_data

        response = self.client.post(self.url, self.valid_telebirr_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertFalse(data['verified'])
        self.assertFalse(data['receiver_name_verified'])
        self.assertFalse(data['receiver_verified'])
        self.assertIn("Credited Party name mismatch (expected 'Beimnet Melese Kebede', got 'Ethio telecom')", data['message'])

    # Test Case 7: Case-Insensitive Receiver Name & Masked Account Matching
    @patch.object(CBEReceiptScraper, 'scrape')
    def test_case_insensitive_receiver_matching(self, mock_scrape):
        case_var_data = {
            **SAMPLE_CBE_RECEIPT_DATA,
            "transaction": {
                **SAMPLE_CBE_RECEIPT_DATA["transaction"],
                "receiver": "BEIMNET melese KEBEDE",
                "receiver_account": "1********3718"
            }
        }
        mock_scrape.return_value = case_var_data

        response = self.client.post(self.url, self.valid_cbe_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertTrue(data['verified'])
        self.assertTrue(data['receiver_verified'])

    # Test Case 8: Custom expected_receiver_account override
    @patch.object(CBEReceiptScraper, 'scrape')
    def test_custom_expected_receiver_account_override(self, mock_scrape):
        custom_account_data = {
            **SAMPLE_CBE_RECEIPT_DATA,
            "transaction": {
                **SAMPLE_CBE_RECEIPT_DATA["transaction"],
                "receiver_account": "1********8597"
            }
        }
        mock_scrape.return_value = custom_account_data

        payload = {
            **self.valid_cbe_payload,
            "expected_receiver_account": "1********8597"
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertTrue(data['verified'])
        self.assertTrue(data['receiver_account_verified'])
        self.assertEqual(data['expected_receiver_account'], "1********8597")

    # Test Case 9: Separate Bank Duplicate Protection
    @patch.object(CBEReceiptScraper, 'scrape', return_value=SAMPLE_CBE_RECEIPT_DATA)
    @patch.object(TelebirrReceiptScraper, 'scrape', return_value=SAMPLE_TELEBIRR_RECEIPT_DATA)
    def test_per_bank_duplicate_separation(self, mock_telebirr_scrape, mock_cbe_scrape):
        same_ref = "SHARED-REF-100"
        cbe_req = {"bank": "cbe", "reference_id": same_ref, "amount": 130.00}
        tele_req = {"bank": "telebirr", "reference_id": same_ref, "amount": 3.00}

        # Verify CBE first
        res_cbe1 = self.client.post(self.url, cbe_req, format='json')
        self.assertTrue(res_cbe1.json()['verified'])

        # Verify Telebirr with SAME reference ID -> MUST STILL SUCCEED because bank is different!
        res_tele1 = self.client.post(self.url, tele_req, format='json')
        self.assertTrue(res_tele1.json()['verified'])

        # Re-submitting CBE -> MUST BE REJECTED AS ALREADY USED
        res_cbe2 = self.client.post(self.url, cbe_req, format='json')
        self.assertTrue(res_cbe2.json()['already_used'])

    # Test Case 10: Missing or Invalid Bank Parameter Validation
    def test_invalid_bank_parameter(self):
        payload = {"bank": "invalid_bank", "reference_id": "REF123", "amount": 100.00}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('bank', data['errors'])


