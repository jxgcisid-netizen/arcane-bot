"""
事件处理模块
"""

from .message_handler import setup as setup_message_handler
from .voice_handler import setup as setup_voice_handler
from .member_handler import setup as setup_member_handler

__all__ = [
    'setup_message_handler',
    'setup_voice_handler',
    'setup_member_handler',
]
