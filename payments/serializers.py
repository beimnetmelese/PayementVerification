import re
from decimal import Decimal
from rest_framework import serializers


class PaymentVerificationRequestSerializer(serializers.Serializer):
    """
    Serializer to validate incoming payment verification requests.
    Supports bank selection ('cbe' or 'telebirr').
    Enforces security sanitization on reference_id and validates positive amount.
    """
    BANK_CHOICES = (
        ('cbe', 'Commercial Bank of Ethiopia (CBE)'),
        ('telebirr', 'Telebirr (Ethio Telecom)'),
    )
    bank = serializers.ChoiceField(
        choices=BANK_CHOICES,
        default='cbe',
        required=False,
        help_text="The payment provider bank ('cbe' or 'telebirr'). Default: 'cbe'"
    )
    reference_id = serializers.CharField(
        required=True,
        max_length=100,
        help_text="The payment reference / receipt ID (e.g. v2-hfHCxGVTzbgxUAOvvyEt or DI91KG3JZN)"
    )
    amount = serializers.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        help_text="The expected payment amount in ETB"
    )
    expected_receiver_account = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=100,
        help_text="Optional override for expected receiver account (e.g. 1********3718 or 2519****4233)"
    )

    def validate_bank(self, value):
        if not value:
            return 'cbe'
        clean_bank = str(value).strip().lower()
        if clean_bank not in ['cbe', 'telebirr']:
            raise serializers.ValidationError("Unsupported bank provider. Allowed choices: 'cbe', 'telebirr'.")
        return clean_bank

    def validate_reference_id(self, value):
        if not isinstance(value, str):
            raise serializers.ValidationError("reference_id must be a string.")
        
        value = value.strip()
        if not value:
            raise serializers.ValidationError("reference_id cannot be empty.")
        
        # SSRF and path sanitization: allow alphanumeric, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9_\-]+$', value):
            raise serializers.ValidationError(
                "Invalid reference ID format. Only alphanumeric characters, hyphens, and underscores are allowed."
            )
        return value

    def validate_amount(self, value):
        if value is None:
            raise serializers.ValidationError("amount is required.")
        if value <= Decimal('0'):
            raise serializers.ValidationError("amount must be a positive number.")
        return value
