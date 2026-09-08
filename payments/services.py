import logging
from decimal import Decimal
from payments.models import PaymentVerification
from payments.scraper import (
    get_scraper_for_bank,
    CBEReceiptNotFoundException,
    CBEScraperFetchException,
    CBEParseException
)

logger = logging.getLogger(__name__)


EXPECTED_RECEIVER_NAME = "Beimnet Melese Kebede"


def is_receiver_verified(actual_receiver: str, expected_receiver: str = EXPECTED_RECEIVER_NAME) -> bool:
    """
    Check if the receipt's receiver / credited party name matches expected receiver name.
    Ignores case, normalizes whitespace, and supports title prefixes or appended details.
    """
    if not actual_receiver:
        return False
    clean_actual = ' '.join(str(actual_receiver).split()).lower()
    clean_expected = ' '.join(str(expected_receiver).split()).lower()

    if clean_actual == clean_expected:
        return True

    # Token-based match: check if all expected name words exist in actual receiver string
    expected_words = [w for w in clean_expected.split() if len(w) > 1]
    if expected_words and all(word in clean_actual for word in expected_words):
        return True

    return False


class PaymentVerificationService:
    """
    Business logic service for verifying payment receipts from CBE or Telebirr.
    Enforces One-Time Verification (duplicate payment prevention per bank provider):
    - Registers receipt ONLY when verification succeeds (bank responds, receipt exists, amount & ref match, receiver matches).
    - Checks duplicate status per bank (cbe / telebirr).
    - Accurately evaluates reference_verified, amount_verified, and receiver_verified.
    """

    def __init__(self, scraper=None):
        self._custom_scraper = scraper

    def get_scraper(self, bank: str):
        if self._custom_scraper:
            return self._custom_scraper
        return get_scraper_for_bank(bank)

    def verify_payment(self, reference_id: str, requested_amount: Decimal, bank: str = 'cbe') -> tuple[dict, int]:
        """
        Verify payment reference ID, amount, and receiver name against external bank receipt (CBE or Telebirr).
        Returns tuple of (response_dict, http_status_code).
        """
        bank_clean = (bank or 'cbe').lower().strip()
        requested_amount_dec = Decimal(str(requested_amount)).quantize(Decimal('0.01'))
        requested_amount_str = f"{requested_amount_dec:.2f}"

        # Step 1: Check if this receipt reference has ALREADY been successfully verified for THIS bank
        existing_successful_verification = PaymentVerification.objects.filter(
            bank=bank_clean,
            reference_id=reference_id,
            is_verified=True
        ).first()

        if existing_successful_verification:
            logger.info(f"Duplicate verification attempt for bank '{bank_clean}' and reference_id '{reference_id}'.")
            verified_amt_str = (
                f"{existing_successful_verification.verified_amount:.2f}"
                if existing_successful_verification.verified_amount is not None
                else None
            )

            # Accurately evaluate amount_verified for the already-used receipt
            amount_verified = False
            if existing_successful_verification.verified_amount is not None:
                amount_verified = (existing_successful_verification.verified_amount == requested_amount_dec)

            verified_receiver = None
            if existing_successful_verification.receipt_data:
                tx_data = existing_successful_verification.receipt_data.get("transaction", {})
                cust_data = existing_successful_verification.receipt_data.get("customer", {})
                verified_receiver = tx_data.get("receiver") or tx_data.get("credited_party_name") or cust_data.get("customer_name")

            receiver_verified = existing_successful_verification.receiver_verified or is_receiver_verified(verified_receiver)

            return {
                "success": True,
                "verified": False,
                "already_used": True,
                "bank": bank_clean,
                "reference_id": reference_id,
                "reference_verified": True,
                "amount_verified": amount_verified,
                "receiver_verified": receiver_verified,
                "expected_receiver": EXPECTED_RECEIVER_NAME,
                "verified_receiver": verified_receiver,
                "requested_amount": requested_amount_str,
                "verified_amount": verified_amt_str,
                "currency": existing_successful_verification.currency or "ETB",
                "message": f"This {bank_clean.upper()} receipt reference has already been used and verified.",
                "receipt": existing_successful_verification.receipt_data
            }, 200

        # Step 2: Fetch receipt from bank provider (only if not already used)
        scraper = self.get_scraper(bank_clean)
        try:
            receipt_data = scraper.scrape(reference_id)
        except CBEReceiptNotFoundException as err:
            logger.info(f"{bank_clean.upper()} receipt not found for reference_id '{reference_id}': {err}")
            return {
                "success": False,
                "verified": False,
                "already_used": False,
                "bank": bank_clean,
                "reference_id": reference_id,
                "reference_verified": False,
                "amount_verified": False,
                "receiver_verified": False,
                "expected_receiver": EXPECTED_RECEIVER_NAME,
                "verified_receiver": None,
                "message": f"Unable to find or retrieve the {bank_clean.upper()} receipt."
            }, 404
        except CBEScraperFetchException as err:
            logger.error(f"{bank_clean.upper()} scraper fetch error for reference_id '{reference_id}': {err}")
            return {
                "success": False,
                "verified": False,
                "already_used": False,
                "bank": bank_clean,
                "reference_id": reference_id,
                "reference_verified": False,
                "amount_verified": False,
                "receiver_verified": False,
                "expected_receiver": EXPECTED_RECEIVER_NAME,
                "verified_receiver": None,
                "message": f"{bank_clean.upper()} receipt service is temporarily unavailable or unreachable."
            }, 502
        except CBEParseException as err:
            logger.error(f"{bank_clean.upper()} receipt parsing error for reference_id '{reference_id}': {err}")
            return {
                "success": False,
                "verified": False,
                "already_used": False,
                "bank": bank_clean,
                "reference_id": reference_id,
                "reference_verified": False,
                "amount_verified": False,
                "receiver_verified": False,
                "expected_receiver": EXPECTED_RECEIVER_NAME,
                "verified_receiver": None,
                "message": f"Failed to parse receipt details from {bank_clean.upper()} website response."
            }, 502
        except Exception as err:
            logger.error(f"Unexpected error during verification for bank '{bank_clean}' reference_id '{reference_id}': {err}")
            return {
                "success": False,
                "verified": False,
                "already_used": False,
                "bank": bank_clean,
                "reference_id": reference_id,
                "reference_verified": False,
                "amount_verified": False,
                "receiver_verified": False,
                "expected_receiver": EXPECTED_RECEIVER_NAME,
                "verified_receiver": None,
                "message": "An error occurred while verifying the payment."
            }, 500

        # Extract parsed details
        transaction_info = receipt_data.get("transaction", {})

        transferred_amount_str = transaction_info.get("transferred_amount")
        currency = transaction_info.get("currency") or "ETB"

        verified_amount_str = None
        amount_verified = False

        if transferred_amount_str is not None:
            try:
                transferred_amount_dec = Decimal(str(transferred_amount_str)).quantize(Decimal('0.01'))
                verified_amount_str = f"{transferred_amount_dec:.2f}"
                amount_verified = (transferred_amount_dec == requested_amount_dec)
            except Exception as e:
                logger.warning(f"Error parsing transferred amount Decimal: {e}")
                amount_verified = False
        else:
            amount_verified = False

        # Evaluate receiver/credited party name
        actual_receiver_name = transaction_info.get("receiver")
        receiver_verified = is_receiver_verified(actual_receiver_name)

        # Reference verification is True ONLY IF transaction details were actually retrieved from the bank
        has_transaction_details = (
            transferred_amount_str is not None or
            transaction_info.get("payer") is not None or
            transaction_info.get("reference_no") is not None
        )
        reference_verified = has_transaction_details
        is_verified = reference_verified and amount_verified and receiver_verified

        # Step 3: ONLY register in DB when payment verification completely succeeds
        if is_verified:
            try:
                PaymentVerification.objects.create(
                    bank=bank_clean,
                    reference_id=reference_id,
                    requested_amount=requested_amount_dec,
                    verified_amount=Decimal(verified_amount_str) if verified_amount_str else None,
                    currency=currency,
                    reference_verified=True,
                    amount_verified=True,
                    receiver_verified=True,
                    is_verified=True,
                    status=receipt_data.get("status"),
                    receipt_data=receipt_data
                )
            except Exception as db_err:
                logger.warning(f"Failed to record successful PaymentVerification log: {db_err}")

            return {
                "success": True,
                "verified": True,
                "already_used": False,
                "bank": bank_clean,
                "reference_id": reference_id,
                "reference_verified": True,
                "amount_verified": True,
                "receiver_verified": True,
                "expected_receiver": EXPECTED_RECEIVER_NAME,
                "verified_receiver": actual_receiver_name,
                "requested_amount": requested_amount_str,
                "verified_amount": verified_amount_str,
                "currency": currency,
                "receipt": receipt_data
            }, 200

        # Handle Mismatch cases (Always include receipt data when found so client can inspect details)
        mismatches = []
        if not reference_verified:
            mismatches.append("Reference verification failed")
        if not amount_verified:
            mismatches.append("payment amount does not match the receipt")
        if not receiver_verified:
            recipient_label = "Credited Party name" if bank_clean == 'telebirr' else "Receiver name"
            mismatches.append(f"{recipient_label} does not match expected ('{EXPECTED_RECEIVER_NAME}')")

        if len(mismatches) == 1:
            message = f"{mismatches[0]}."
            message = message[0].upper() + message[1:]
        else:
            message = "; ".join(mismatches) + "."
            message = message[0].upper() + message[1:]

        return {
            "success": True,
            "verified": False,
            "already_used": False,
            "bank": bank_clean,
            "reference_id": reference_id,
            "reference_verified": reference_verified,
            "amount_verified": amount_verified,
            "receiver_verified": receiver_verified,
            "expected_receiver": EXPECTED_RECEIVER_NAME,
            "verified_receiver": actual_receiver_name,
            "requested_amount": requested_amount_str,
            "verified_amount": verified_amount_str,
            "currency": currency,
            "message": message,
            "receipt": receipt_data
        }, 200
