"""Tests for the Bitbucket Cloud webhook route."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from server.routes.integration.bitbucket import (
    BitbucketResourceIdentifier,
    BitbucketWebhookRequest,
    bitbucket_events,
    get_bitbucket_resources,
    reinstall_bitbucket_webhook,
    uninstall_bitbucket_webhook,
)

from openhands.app_server.integrations.service_types import ProviderType, Repository


def _signed(body: bytes, secret: str = 'shared-secret') -> str:
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _request_with_body(body: bytes) -> MagicMock:
    request = MagicMock()
    request.body = AsyncMock(return_value=body)
    return request


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.IS_LOCAL_DEPLOYMENT', False)
@patch('server.routes.integration.bitbucket.webhook_store')
@patch('server.routes.integration.bitbucket.bitbucket_manager')
@patch('server.routes.integration.bitbucket.get_redis_client_async')
async def test_missing_hook_uuid_header_rejected_with_403(
    mock_get_redis_client_async, mock_manager, mock_store
):
    mock_store.get_webhook_secret = AsyncMock(return_value='shared-secret')
    mock_manager.receive_message = AsyncMock()
    mock_get_redis_client_async.return_value = AsyncMock()
    body = json.dumps({'pullrequest': {'id': 1}}).encode()

    with pytest.raises(HTTPException) as exc:
        await bitbucket_events(
            request=_request_with_body(body),
            x_hub_signature=_signed(body),
            x_event_key='pullrequest:comment_created',
            x_request_uuid='req-1',
            x_hook_uuid=None,
        )

    assert exc.value.status_code == 403
    mock_manager.receive_message.assert_not_called()


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.IS_LOCAL_DEPLOYMENT', False)
@patch('server.routes.integration.bitbucket.webhook_store')
@patch('server.routes.integration.bitbucket.bitbucket_manager')
@patch('server.routes.integration.bitbucket.get_redis_client_async')
async def test_signature_verification_rejects_bad_signature_with_403(
    mock_get_redis_client_async, mock_manager, mock_store
):
    mock_store.get_webhook_secret = AsyncMock(return_value='shared-secret')
    mock_manager.receive_message = AsyncMock()
    mock_get_redis_client_async.return_value = AsyncMock()
    body = json.dumps({'pullrequest': {'id': 1}}).encode()

    with pytest.raises(HTTPException) as exc:
        await bitbucket_events(
            request=_request_with_body(body),
            x_hub_signature='sha256=deadbeef',
            x_event_key='pullrequest:comment_created',
            x_request_uuid='req-1',
            x_hook_uuid='install-uuid',
        )

    assert exc.value.status_code == 403
    mock_manager.receive_message.assert_not_called()


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.IS_LOCAL_DEPLOYMENT', False)
@patch('server.routes.integration.bitbucket.webhook_store')
@patch('server.routes.integration.bitbucket.bitbucket_manager')
@patch('server.routes.integration.bitbucket.get_redis_client_async')
async def test_duplicate_event_returns_200_and_skips_dispatch(
    mock_get_redis_client_async, mock_manager, mock_store
):
    mock_store.get_webhook_secret = AsyncMock(return_value='shared-secret')
    mock_manager.receive_message = AsyncMock()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=False)  # duplicate
    mock_get_redis_client_async.return_value = redis

    body = json.dumps({'pullrequest': {'id': 1}, 'comment': {'id': 99}}).encode()

    response = await bitbucket_events(
        request=_request_with_body(body),
        x_hub_signature=_signed(body),
        x_event_key='pullrequest:comment_created',
        x_request_uuid='req-1',
        x_hook_uuid='install-uuid',
    )

    mock_manager.receive_message.assert_not_called()
    assert response.status_code == 200
    assert json.loads(response.body)['message'].startswith('Duplicate')


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.IS_LOCAL_DEPLOYMENT', False)
@patch('server.routes.integration.bitbucket.webhook_store')
@patch('server.routes.integration.bitbucket.bitbucket_manager')
@patch('server.routes.integration.bitbucket.get_redis_client_async')
async def test_valid_event_dispatches_to_manager_and_returns_200(
    mock_get_redis_client_async, mock_manager, mock_store
):
    mock_store.get_webhook_secret = AsyncMock(return_value='shared-secret')
    mock_manager.receive_message = AsyncMock()
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    mock_get_redis_client_async.return_value = redis

    body = json.dumps({'pullrequest': {'id': 1}, 'comment': {'id': 99}}).encode()

    response = await bitbucket_events(
        request=_request_with_body(body),
        x_hub_signature=_signed(body),
        x_event_key='pullrequest:comment_created',
        x_request_uuid='req-1',
        x_hook_uuid='install-uuid',
    )

    mock_manager.receive_message.assert_awaited_once()
    dispatched = mock_manager.receive_message.call_args.args[0]
    assert dispatched.source.value == 'bitbucket'
    assert dispatched.message['event_key'] == 'pullrequest:comment_created'
    assert response.status_code == 200


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.webhook_store')
@patch('server.routes.integration.bitbucket.SaaSBitBucketService')
async def test_get_bitbucket_resources_lists_admin_repos_with_status(
    mock_service_cls, mock_store
):
    service = MagicMock()
    service.get_all_repositories = AsyncMock(
        return_value=[
            Repository(
                id='{repo-1}',
                full_name='acme/repo-1',
                git_provider=ProviderType.BITBUCKET,
                is_public=False,
            ),
            Repository(
                id='{repo-2}',
                full_name='acme/repo-2',
                git_provider=ProviderType.BITBUCKET,
                is_public=False,
            ),
        ]
    )
    service.user_has_admin_access = AsyncMock(side_effect=[True, False])
    service.check_webhook_exists_on_repository = AsyncMock(
        return_value=(True, '{hook-1}')
    )
    mock_service_cls.return_value = service

    webhook = MagicMock()
    webhook.webhook_uuid = '{hook-1}'
    webhook.webhook_secret = 'shared-secret'
    webhook.user_id = 'kc-installer'
    webhook.last_synced = None
    mock_store.get_webhooks_by_repos = AsyncMock(
        return_value={('acme', 'repo-1'): webhook}
    )

    response = await get_bitbucket_resources(user_id='kc-user')

    assert len(response.resources) == 1
    assert response.resources[0].full_name == 'acme/repo-1'
    assert response.resources[0].webhook_installed is True
    assert response.resources[0].webhook_exists_on_provider is True
    mock_store.get_webhooks_by_repos.assert_awaited_once_with([('acme', 'repo-1')])


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.secrets.token_urlsafe')
@patch('server.routes.integration.bitbucket.webhook_store')
@patch('server.routes.integration.bitbucket.SaaSBitBucketService')
async def test_reinstall_bitbucket_webhook_updates_provider_and_store(
    mock_service_cls, mock_store, mock_token_urlsafe
):
    mock_token_urlsafe.return_value = 'generated-secret'
    service = MagicMock()
    service.user_has_admin_access = AsyncMock(return_value=True)
    service.check_webhook_exists_on_repository = AsyncMock(
        return_value=(True, '{hook-1}')
    )
    service.update_repository_webhook = AsyncMock(return_value='{hook-1}')
    service.create_repository_webhook = AsyncMock()
    mock_service_cls.return_value = service
    mock_store.upsert_webhook_enrollment = AsyncMock()

    response = await reinstall_bitbucket_webhook(
        body=BitbucketWebhookRequest(
            resource=BitbucketResourceIdentifier(
                workspace='acme',
                repo_slug='repo-1',
            )
        ),
        user_id='kc-user',
    )

    assert response.success is True
    assert response.webhook_uuid == '{hook-1}'
    service.update_repository_webhook.assert_awaited_once()
    service.create_repository_webhook.assert_not_called()
    mock_store.upsert_webhook_enrollment.assert_awaited_once_with(
        workspace='acme',
        repo_slug='repo-1',
        user_id='kc-user',
        webhook_uuid='{hook-1}',
        webhook_secret='generated-secret',
    )


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.SaaSBitBucketService')
async def test_reinstall_bitbucket_webhook_rejects_non_admin(mock_service_cls):
    service = MagicMock()
    service.user_has_admin_access = AsyncMock(return_value=False)
    mock_service_cls.return_value = service

    with pytest.raises(HTTPException) as exc:
        await reinstall_bitbucket_webhook(
            body=BitbucketWebhookRequest(
                resource=BitbucketResourceIdentifier(
                    workspace='acme',
                    repo_slug='repo-1',
                )
            ),
            user_id='kc-user',
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
@patch('server.routes.integration.bitbucket.webhook_store')
@patch('server.routes.integration.bitbucket.SaaSBitBucketService')
async def test_uninstall_bitbucket_webhook_deletes_provider_and_store(
    mock_service_cls, mock_store
):
    service = MagicMock()
    service.user_has_admin_access = AsyncMock(return_value=True)
    service.check_webhook_exists_on_repository = AsyncMock(
        return_value=(True, '{hook-1}')
    )
    service.delete_repository_webhook = AsyncMock()
    mock_service_cls.return_value = service

    webhook = MagicMock()
    webhook.webhook_uuid = '{hook-1}'
    mock_store.get_webhook_by_repo = AsyncMock(return_value=webhook)
    mock_store.delete_webhook_by_repo = AsyncMock(return_value=True)

    response = await uninstall_bitbucket_webhook(
        body=BitbucketWebhookRequest(
            resource=BitbucketResourceIdentifier(
                workspace='acme',
                repo_slug='repo-1',
            )
        ),
        user_id='kc-user',
    )

    assert response.success is True
    service.delete_repository_webhook.assert_awaited_once_with(
        'acme', 'repo-1', '{hook-1}'
    )
    mock_store.delete_webhook_by_repo.assert_awaited_once_with(
        workspace='acme',
        repo_slug='repo-1',
    )
