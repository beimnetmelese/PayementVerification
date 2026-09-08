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


class PaymentVerificationService:
    """
    Business logic service for verifying payment receipts from CBE or Telebirr.
    Enforces One-Time Verification (duplicate payment prevention per bank provider):
    - Registers receipt ONLY when verification succeeds (bank responds, receipt exists, amount & ref match).
    - Checks duplicate status per bank (cbe / telebirr).
    - Accurately evaluates reference_verified and amount_verified. Returns reference_verified=False when receipt is not found.
    """

    def __init__(self, scraper=None):
        self._custom_scraper = scraper

    def get_scraper(self, bank: str):
        if self._custom_scraper:
            return self._custom_scraper
        return get_scraper_for_bank(bank)

    def verify_payment(self, reference_id: str, requested_amount: Decimal, bank: str = 'cbe') -> tuple[dict, int]:
        """
        Verify payment reference ID and amount against external bank receipt (CBE or Telebirr).
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

            return {
                "success": True,
                "verified": False,
                "already_used": True,
                "bank": bank_clean,
                "reference_id": reference_id,
                "reference_verified": True,
                "amount_verified": amount_verified,
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

        # Reference verification is True ONLY IF transaction details were actually retrieved from the bank
        has_transaction_details = (
            transferred_amount_str is not None or
            transaction_info.get("payer") is not None or
            transaction_info.get("reference_no") is not None
        )
        reference_verified = has_transaction_details
        is_verified = reference_verified and amount_verified

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
                "requested_amount": requested_amount_str,
                "verified_amount": verified_amount_str,
                "currency": currency,
                "receipt": receipt_data
            }, 200

        # Handle Mismatch cases (Always include receipt data when found so client can inspect details)
        if not reference_verified and not amount_verified:
            message = "Reference verification failed and payment amount does not match the receipt."
        elif not amount_verified:
            message = "Payment amount does not match the receipt."
        else:
            message = "Reference verification failed."

        return {
            "success": True,
            "verified": False,
            "already_used": False,
            "bank": bank_clean,
            "reference_id": reference_id,
            "reference_verified": reference_verified,
            "amount_verified": amount_verified,
            "requested_amount": requested_amount_str,
            "verified_amount": verified_amount_str,
            "currency": currency,
            "message": message,
            "receipt": receipt_data
        }, 200
