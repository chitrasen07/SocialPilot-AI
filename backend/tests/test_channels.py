"""Multi-channel inbox. Drafts stay inside the app and nothing is delivered."""

import hashlib
import hmac
import json

import pytest

from app.channels import PROVIDERS
from app.channels.base import ChannelSendBlocked
from app.models import AIReplyDraft, Role
from app.models.channel import ChannelType
from tests.conftest import add_instagram_account, deliver, dm_payload, member_headers
from tests.test_inbox_api import seed

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _headers(db, verifier, role: Role = Role.ADMIN):
    auth, organization = member_headers(db, verifier, role)
    return {**auth, "X-Organization-Id": str(organization.id)}, organization


def _sign(secret: str, body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"x-channel-signature": f"sha256={digest}", "content-type": "application/json"}


def test_channel_interface_refuses_to_send():
    for channel in ChannelType:
        provider = PROVIDERS[channel]
        assert provider.channel == channel
        with pytest.raises(ChannelSendBlocked):
            import asyncio

            asyncio.run(provider.send_message("person", "hello"))


def test_instagram_adapter_reads_the_existing_webhook_shape():
    payload = dm_payload("user_123", "price kya hai?", "mid_ig", 1790000200000)
    messages = PROVIDERS[ChannelType.INSTAGRAM].receive_message(payload)
    assert messages[0].text == "price kya hai?"
    assert messages[0].sender_id == "user_123"


def test_whatsapp_messenger_and_email_normalize_into_the_inbox(api, db, verifier):
    headers, _organization = _headers(db, verifier)
    created = {}
    for channel, payload in (
        (
            "whatsapp",
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "100"},
                                    "contacts": [{"wa_id": "1555", "profile": {"name": "Rahul"}}],
                                    "messages": [
                                        {
                                            "from": "1555",
                                            "id": "wamid.1",
                                            "timestamp": "1790000200",
                                            "type": "text",
                                            "text": {"body": "price kya hai?"},
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ]
            },
        ),
        (
            "messenger",
            {
                "entry": [
                    {
                        "id": "page",
                        "messaging": [
                            {
                                "sender": {"id": "psid"},
                                "recipient": {"id": "page"},
                                "timestamp": 1790000200000,
                                "message": {"mid": "m1", "text": "price kya hai?"},
                            }
                        ],
                    }
                ]
            },
        ),
        (
            "email",
            {
                "message_id": "<price@shop>",
                "from": "rahul@example.com",
                "to": "shop@example.com",
                "subject": "Price",
                "text": "price kya hai?",
            },
        ),
    ):
        connected = api.post(
            "/api/channels/connect",
            json={"channel_type": channel, "display_name": channel},
            headers=headers,
        )
        assert connected.status_code == 201, connected.text
        created[channel] = connected.json()
        raw, signed = _sign(connected.json()["setup_token"], payload)
        response = api.post(
            f"/api/channels/webhook/{connected.json()['id']}",
            content=raw,
            headers=signed,
        )
        assert response.status_code == 200, response.text
        assert response.json()["received"] == 1
        bad = api.post(
            f"/api/channels/webhook/{connected.json()['id']}",
            content=raw,
            headers={"x-channel-signature": "sha256=nope", "content-type": "application/json"},
        )
        assert bad.status_code == 401

    listed = api.get("/api/conversations?channel=whatsapp", headers=headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 1
    assert listed.json()["items"][0]["channel_type"] == "whatsapp"
    assert api.get("/api/conversations?channel=messenger", headers=headers).json()["items"]
    email_rows = api.get("/api/conversations?channel=email", headers=headers).json()["items"]
    assert email_rows
    assert db.count(AIReplyDraft) >= 1
    settings = api.get("/api/channels/settings", headers=headers)
    assert settings.status_code == 200
    assert "setup_token" not in settings.text
    assert "webhook_secret" not in settings.text


def test_webchat_creates_a_conversation_and_a_draft(api, db, verifier):
    headers, _organization = _headers(db, verifier)
    connected = api.post(
        "/api/channels/connect",
        json={"channel_type": "webchat", "display_name": "Site"},
        headers=headers,
    )
    assert connected.status_code == 201, connected.text
    channel_id = connected.json()["id"]
    token = connected.json()["setup_token"]
    widget = {"x-widget-token": token}
    created = api.post(
        f"/api/channels/webchat/{channel_id}/messages",
        json={"visitor_id": "visitor-1", "message_id": "c1", "text": "price kya hai?"},
        headers=widget,
    )
    assert created.status_code == 201, created.text
    history = api.get(
        f"/api/channels/webchat/{channel_id}/messages",
        params={"visitor_id": "visitor-1"},
        headers=widget,
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["text"] == "price kya hai?"
    assert history.json()["handoff"] is False
    assert api.get("/api/conversations?channel=webchat", headers=headers).json()["items"]
    assert db.count(AIReplyDraft) == 1
    queue = api.get("/api/ai/review-queue", headers=headers)
    assert queue.json()["items"][0]["sent"] is False


def test_instagram_messages_remain_in_the_inbox(api, db, verifier):
    headers, _organization = seed(db, verifier)
    deliver(db, dm_payload("user_789", "hello there", "mid_keep", 1790000300000))
    body = api.get("/api/conversations?channel=instagram", headers=headers)
    assert body.status_code == 200, body.text
    assert body.json()["items"]
    assert all(item["channel_type"] == "instagram" for item in body.json()["items"])
    assert api.get("/api/conversations?priority=medium", headers=headers).json()["items"]


def test_channel_rbac_and_isolation(api, db, verifier):
    admin, organization = _headers(db, verifier, Role.ADMIN)
    viewer, _ = _headers(db, verifier, Role.VIEWER)
    other, _ = _headers(db, verifier, Role.OWNER)
    add_instagram_account(db, organization)
    forbidden = api.post("/api/channels/connect", json={"channel_type": "email"}, headers=viewer)
    assert forbidden.status_code == 403
    assert api.get("/api/channels", headers=viewer).status_code == 200
    created = api.post("/api/channels/connect", json={"channel_type": "email"}, headers=admin)
    assert created.status_code == 201, created.text
    channel_id = created.json()["id"]
    assert api.get("/api/channels", headers=other).json()["items"] == []
    missing = api.patch(
        f"/api/channels/{channel_id}", json={"status": "disconnected"}, headers=other
    )
    assert missing.status_code == 404
    assert api.get("/api/analytics/channels", headers=other).json()["channels"] == []
    own = api.get("/api/analytics/channels", headers=admin)
    assert own.status_code == 200
