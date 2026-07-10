"""站内通知 WebSocket Consumer。"""

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from notifications.realtime import user_notification_group_name


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """当前登录用户的站内通知实时推送 Consumer。"""

    async def connect(self):
        """校验登录状态并加入用户专属通知频道组。"""

        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        self.group_name = user_notification_group_name(self.user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        """断开连接时退出用户专属通知频道组。"""

        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_created(self, event):
        """把新通知事件发送给当前 WebSocket 客户端。"""

        await self.send_json(
            {
                "type": "notification.created",
                "notification": event["notification"],
                "unread_count": event["unread_count"],
            }
        )
