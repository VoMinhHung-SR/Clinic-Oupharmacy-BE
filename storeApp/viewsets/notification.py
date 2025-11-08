from rest_framework import viewsets, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from storeApp.models import Notification
from storeApp.serializers import NotificationSerializer


class NotificationViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView,
                          generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    
    @action(methods=['post'], detail=True, url_path='mark-as-read')
    def mark_as_read(self, request, pk=None):
        """Đánh dấu thông báo đã đọc"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response(NotificationSerializer(notification).data)
    
    @action(methods=['get'], detail=False, url_path='unread')
    def unread(self, request):
        """Lấy danh sách thông báo chưa đọc"""
        unread_notifications = Notification.objects.filter(is_read=False)
        serializer = self.get_serializer(unread_notifications, many=True)
        return Response(serializer.data)