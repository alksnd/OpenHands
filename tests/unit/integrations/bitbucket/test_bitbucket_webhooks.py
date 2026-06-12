from unittest.mock import AsyncMock

import pytest

from openhands.app_server.integrations.bitbucket.bitbucket_service import (
    BitBucketService,
)
from openhands.app_server.integrations.service_types import RequestMethod


@pytest.mark.asyncio
async def test_create_repository_webhook_posts_bitbucket_payload():
    service = BitBucketService(token=None)
    service._make_request = AsyncMock(  # type: ignore[method-assign]
        return_value=({'uuid': '{hook-1}'}, {})
    )

    webhook_uuid = await service.create_repository_webhook(
        workspace='acme',
        repo_slug='repo-1',
        description='OpenHands Resolver',
        webhook_url='https://app.example.com/integration/bitbucket/events',
        webhook_secret='secret',
        events=['pullrequest:comment_created'],
    )

    assert webhook_uuid == '{hook-1}'
    service._make_request.assert_awaited_once_with(
        url='https://api.bitbucket.org/2.0/repositories/acme/repo-1/hooks',
        params={
            'description': 'OpenHands Resolver',
            'url': 'https://app.example.com/integration/bitbucket/events',
            'active': True,
            'secret': 'secret',
            'events': ['pullrequest:comment_created'],
        },
        method=RequestMethod.POST,
    )


@pytest.mark.asyncio
async def test_update_repository_webhook_puts_secret_and_events():
    service = BitBucketService(token=None)
    service._make_request = AsyncMock(  # type: ignore[method-assign]
        return_value=({'uuid': '{hook-1}'}, {})
    )

    webhook_uuid = await service.update_repository_webhook(
        workspace='acme',
        repo_slug='repo-1',
        webhook_uuid='{hook-1}',
        description='OpenHands Resolver',
        webhook_url='https://app.example.com/integration/bitbucket/events',
        webhook_secret='secret',
        events=['pullrequest:comment_created'],
    )

    assert webhook_uuid == '{hook-1}'
    service._make_request.assert_awaited_once_with(
        url='https://api.bitbucket.org/2.0/repositories/acme/repo-1/hooks/{hook-1}',
        params={
            'description': 'OpenHands Resolver',
            'url': 'https://app.example.com/integration/bitbucket/events',
            'active': True,
            'secret': 'secret',
            'events': ['pullrequest:comment_created'],
        },
        method=RequestMethod.PUT,
    )


@pytest.mark.asyncio
async def test_delete_repository_webhook_uses_bitbucket_delete_endpoint():
    service = BitBucketService(token=None)
    service._make_request = AsyncMock(return_value=({}, {}))  # type: ignore[method-assign]

    await service.delete_repository_webhook('acme', 'repo-1', '{hook-1}')

    service._make_request.assert_awaited_once_with(
        url='https://api.bitbucket.org/2.0/repositories/acme/repo-1/hooks/{hook-1}',
        method=RequestMethod.DELETE,
    )
