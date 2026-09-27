"""Channel providers. Instagram's existing webhook route is not replaced."""

from app.channels.base import ChannelProvider, ChannelSendBlocked
from app.channels.email import EmailChannel
from app.channels.instagram import InstagramChannel
from app.channels.messenger import MessengerChannel
from app.channels.webchat import WebChatChannel
from app.channels.whatsapp import WhatsAppChannel
from app.models.channel import ChannelType

PROVIDERS: dict[ChannelType, ChannelProvider] = {
    ChannelType.INSTAGRAM: InstagramChannel(),
    ChannelType.WHATSAPP: WhatsAppChannel(),
    ChannelType.MESSENGER: MessengerChannel(),
    ChannelType.EMAIL: EmailChannel(),
    ChannelType.WEBCHAT: WebChatChannel(),
}

__all__ = ["PROVIDERS", "ChannelProvider", "ChannelSendBlocked"]
