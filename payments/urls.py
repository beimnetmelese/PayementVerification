from django.urls import path
from payments.views import VerifyPaymentView

app_name = 'payments'

urlpatterns = [
    path('verify/', VerifyPaymentView.as_view(), name='verify-payment'),
]
