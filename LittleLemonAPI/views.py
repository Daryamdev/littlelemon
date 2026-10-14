from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth.models import User, Group
from django.shortcuts import get_object_or_404
from .models import Category, MenuItem, Cart, Order, OrderItem
from .serializers import CategorySerializer, MenuItemSerializer, UserSerializer, CartSerializer, OrderSerializer
import datetime

# Categories & Menu Items
class CategoriesView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAdminUser()]

class MenuItemsView(generics.ListCreateAPIView):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    search_fields = ['title', 'category__title']
    ordering_fields = ['price', 'category']

    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        return [IsAdminUser()]

class SingleMenuItemView(generics.RetrieveUpdateDestroyAPIView):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return []
        if self.request.user.groups.filter(name='Manager').exists():
            return [IsAuthenticated()]
        return [IsAdminUser()]

# User Group Management
class ManagersView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(groups__name='Manager')

    def post(self, request):
        username = request.data.get('username')
        if username:
            user = get_object_or_404(User, username=username)
            managers = Group.objects.get(name='Manager')
            managers.user_set.add(user)
            return Response({'message': 'User added to Manager group'}, status=status.HTTP_201_CREATED)
        return Response({'message': 'Username required'}, status=status.HTTP_400_BAD_REQUEST)

class DeliveryCrewView(generics.ListCreateAPIView):
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.request.user.groups.filter(name='Manager').exists() or self.request.user.is_staff:
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def get_queryset(self):
        return User.objects.filter(groups__name='Delivery Crew')

    def post(self, request):
        username = request.data.get('username')
        if username:
            user = get_object_or_404(User, username=username)
            crew = Group.objects.get(name='Delivery Crew')
            crew.user_set.add(user)
            return Response({'message': 'User added to Delivery Crew'}, status=status.HTTP_201_CREATED)
        return Response({'message': 'Username required'}, status=status.HTTP_400_BAD_REQUEST)

# Cart
#  class CartView(generics.ListCreateDestroyAPIView):

class CartView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        menuitem = serializer.validated_data['menuitem']
        quantity = serializer.validated_data['quantity']
        unit_price = menuitem.price
        price = unit_price * quantity
        serializer.save(user=self.request.user, unit_price=unit_price, price=price)

    def delete(self, request):
        Cart.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Orders
class OrderView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        user = self.request.user
        if user.groups.filter(name='Manager').exists() or user.is_staff:
            return Order.objects.all()
        elif user.groups.filter(name='Delivery Crew').exists():
            return Order.objects.filter(delivery_crew=user)
        return Order.objects.filter(user=user)

    def create(self, request, *args, **kwargs):
        cart_items = Cart.objects.filter(user=request.user)
        if not cart_items.exists():
            return Response({'message': 'Cart is empty'}, status=status.HTTP_400_BAD_REQUEST)

        total = sum([item.price for item in cart_items])
        order = Order.objects.create(user=request.user, total=total, date=datetime.date.today())

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                menuitem=item.menuitem,
                quantity=item.quantity,
                unit_price=item.unit_price,
                price=item.price
            )
        cart_items.delete()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

class SingleOrderView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    queryset = Order.objects.all()

    def patch(self, request, *args, **kwargs):
        order = self.get_object()
        user = request.user

        if user.groups.filter(name='Manager').exists() or user.is_staff:
            if 'delivery_crew' in request.data:
                crew_user = get_object_or_404(User, id=request.data['delivery_crew'])
                order.delivery_crew = crew_user
            if 'status' in request.data:
                order.status = request.data['status']
            order.save()
            return Response(OrderSerializer(order).data)

        if user.groups.filter(name='Delivery Crew').exists():
            if 'status' in request.data:
                order.status = request.data['status']
                order.save()
                return Response(OrderSerializer(order).data)

        return Response(status=status.HTTP_403_FORBIDDEN)