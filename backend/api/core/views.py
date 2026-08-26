from rest_framework import viewsets

from repositories.core import RoleRepository, UserRepository
from schemas.core import RoleSerializer, UserSerializer


class RoleViewSet(viewsets.ModelViewSet):
    serializer_class = RoleSerializer

    def get_queryset(self):
        return RoleRepository.all()


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer

    def get_queryset(self):
        return UserRepository.all()
