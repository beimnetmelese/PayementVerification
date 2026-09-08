from django.db import models


class PaymentVerification(models.Model):
    """
    Model to record payment verification attempts and results for duplicate payment protection
    and audit tracking, separated by bank provider.
    """
    BANK_CHOICES = (
        ('cbe', 'Commercial Bank of Ethiopia'),
        ('telebirr', 'Telebirr'),
    )
    bank = models.CharField(max_length=20, choices=BANK_CHOICES, default='cbe', db_index=True)
    reference_id = models.CharField(max_length=100, db_index=True)
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)
    verified_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default='ETB')
    reference_verified = models.BooleanField(default=False)
    amount_verified = models.BooleanField(default=False)
    receiver_verified = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    status = models.CharField(max_length=50, null=True, blank=True)
    receipt_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment Verification'
        verbose_name_plural = 'Payment Verifications'

    def __str__(self):
        return f"[{self.bank.upper()}] {self.reference_id} - Verified: {self.is_verified}"
