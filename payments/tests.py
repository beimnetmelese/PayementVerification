from decimal import Decimal
from unittest.mock import patch
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
        "payer_account": "1****3718",
        "receiver": "Beimnet Melese Kebede",
        "receiver_account": "1****3937",
        "payment_type": "A2A",
        "payment_date_time": "Sep 8, 2026, 7:48 PM",
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
        "receiver_account": "111222",
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

    # Test Case 1: Valid CBE reference + correct amount + matching receiver
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
        self.assertTrue(data['receiver_verified'])
        self.assertEqual(data['expected_receiver'], "Beimnet Melese Kebede")
        self.assertEqual(data['verified_receiver'], "Beimnet Melese Kebede")
        self.assertEqual(data['requested_amount'], "130.00")
        self.assertEqual(data['verified_amount'], "130.00")

    # Test Case 2: Valid Telebirr reference + correct amount + matching credited party
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
        self.assertTrue(data['receiver_verified'])
        self.assertEqual(data['requested_amount'], "3.00")
        self.assertEqual(data['verified_amount'], "3.00")
        self.assertEqual(data['receipt']['company']['name'], "Ethio telecom Share Company")

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
        self.assertIn("receipt", data)

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
        self.assertFalse(data['receiver_verified'])
        self.assertIn("Receiver name does not match expected", data['message'])

    # Test Case 5: Telebirr Credited Party Name Mismatch
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
        self.assertTrue(data['reference_verified'])
        self.assertTrue(data['amount_verified'])
        self.assertFalse(data['receiver_verified'])
        self.assertIn("Credited Party name does not match expected", data['message'])

    # Test Case 6: Case-Insensitive Receiver Name Matching
    @patch.object(CBEReceiptScraper, 'scrape')
    def test_case_insensitive_receiver_matching(self, mock_scrape):
        case_var_data = {
            **SAMPLE_CBE_RECEIPT_DATA,
            "transaction": {
                **SAMPLE_CBE_RECEIPT_DATA["transaction"],
                "receiver": "BEIMNET melese KEBEDE"
            }
        }
        mock_scrape.return_value = case_var_data

        response = self.client.post(self.url, self.valid_cbe_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertTrue(data['verified'])
        self.assertTrue(data['receiver_verified'])

    # Test Case 7: Separate Bank Duplicate Protection
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

    # Test Case 8: Missing or Invalid Bank Parameter Validation
    def test_invalid_bank_parameter(self):
        payload = {"bank": "invalid_bank", "reference_id": "REF123", "amount": 100.00}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('bank', data['errors'])
