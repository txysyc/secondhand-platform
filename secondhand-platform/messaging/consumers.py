from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import PermissionDenied, ValidationError

from messaging.selectors import get_conversation_for_user
from messaging.services import (
    create_private_message,
    get_user_by_id,
    serialize_private_message,
)


class PrivateMessageConsumer(AsyncJsonWebsocketConsumer):
    """一对一私信 WebSocket Consumer。"""

    async def connect(self):
        self.user = self.scope["user"]
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = f"private_messages_{self.conversation_id}"

        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        if not await self._can_access_conversation(self.user.pk, self.conversation_id):
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message_content = content.get("content", "")
        try:
            message = await self._create_message(
                self.user.pk,
                self.conversation_id,
                message_content,
            )
        except ValidationError as error:
            await self.send_json(
                {"type": "error", "message": _first_error_message(error, "消息发送失败")}
            )
            return
        except PermissionDenied:
            await self.send_json({"type": "error", "message": "无权访问该私信会话"})
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "private.message",
                "message": message,
            },
        )

    async def private_message(self, event):
        await self.send_json({"type": "message", "message": event["message"]})

    @database_sync_to_async
    def _can_access_conversation(self, user_id, conversation_id):
        user = get_user_by_id(user_id)
        try:
            get_conversation_for_user(user, conversation_id)
        except Exception:
            return False
        return True

    @database_sync_to_async
    def _create_message(self, user_id, conversation_id, content):
        user = get_user_by_id(user_id)
        conversation = get_conversation_for_user(user, conversation_id)
        message = create_private_message(user, conversation, content)
        return serialize_private_message(message)


def _first_error_message(error, fallback):
    messages_list = getattr(error, "messages", None)
    if messages_list:
        return messages_list[0]
    if error.args:
        return str(error.args[0])
    return fallback
