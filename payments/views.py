from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, parsers, renderers
from payments.serializers import PaymentVerificationRequestSerializer
from payments.services import PaymentVerificationService


class VerifyPaymentView(APIView):
    """
    API Endpoint to verify payment receipts from Commercial Bank of Ethiopia (CBE) or Telebirr.

    POST /api/payments/verify/

    Accepts:
    - bank: string ('cbe' or 'telebirr', default: 'cbe')
    - reference_id: string (e.g. "v2-hfHCxGVTzbgxUAOvvyEt" or "DI91KG3JZN")
    - amount: positive decimal number (e.g. 130.00 or 3.00)

    Returns verification results along with complete receipt metadata.
    """
    serializer_class = PaymentVerificationRequestSerializer
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]
    renderer_classes = [renderers.JSONRenderer, renderers.BrowsableAPIRenderer]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "verified": False,
                "errors": serializer.errors,
                "message": "Invalid request payload."
            }, status=status.HTTP_400_BAD_REQUEST)

        bank = serializer.validated_data.get('bank', 'cbe')
        reference_id = serializer.validated_data['reference_id']
        amount = serializer.validated_data['amount']
        expected_account = serializer.validated_data.get('expected_receiver_account')

        service = PaymentVerificationService()
        result_data, http_status = service.verify_payment(
            reference_id,
            amount,
            bank=bank,
            expected_receiver_account=expected_account
        )

        return Response(result_data, status=http_status)
