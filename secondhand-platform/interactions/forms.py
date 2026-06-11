from django import forms
from django.core.exceptions import ValidationError
from interactions.models import Comment


class CommentForm(forms.ModelForm):
    """留言表单"""

    class Meta:
        model = Comment
        fields = ["content"]
        error_messages = {
            "content": {
                "required": "留言内容不能为空",
                "max_length": "留言内容不能超过 1000 个字符",
            }
        }

    def clean_content(self):
        """去除留言内容两端空白并拒绝空内容。"""

        content: str = self.cleaned_data["content"]
        content = content.strip()
        if content == "":
            raise ValidationError("留言内容不能为空")

        return content
