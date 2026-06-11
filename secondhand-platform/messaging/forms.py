from django import forms
from django.core.exceptions import ValidationError

from messaging.services import MAX_PRIVATE_MESSAGE_LENGTH


class PrivateMessageForm(forms.Form):
    """私信发送表单。"""

    content = forms.CharField(
        label="消息内容",
        max_length=MAX_PRIVATE_MESSAGE_LENGTH,
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={
            "required": "消息内容不能为空",
            "max_length": f"消息内容不能超过 {MAX_PRIVATE_MESSAGE_LENGTH} 个字符",
        },
    )

    def clean_content(self):
        """去除私信内容两端空白并拒绝空内容。"""

        content = self.cleaned_data["content"].strip()
        if content == "":
            raise ValidationError("消息内容不能为空")
        return content
