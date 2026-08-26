from rest_framework import viewsets

from repositories.procurement import ApprovalRepository, QuoteRepository
from schemas.procurement import ApprovalSerializer, QuoteSerializer


class QuoteViewSet(viewsets.ModelViewSet):
    serializer_class = QuoteSerializer

    def get_queryset(self):
        return QuoteRepository.all()


class ApprovalViewSet(viewsets.ModelViewSet):
    serializer_class = ApprovalSerializer

    def get_queryset(self):
        return ApprovalRepository.all()
