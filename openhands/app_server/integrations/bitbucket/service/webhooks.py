from typing import Any

from openhands.app_server.integrations.bitbucket.service.base import BitBucketMixinBase
from openhands.app_server.integrations.service_types import RequestMethod


class BitBucketWebhooksMixin(BitBucketMixinBase):
    """Repository webhook helpers for Bitbucket Cloud."""

    async def get_repository_webhooks(
        self, workspace: str, repo_slug: str
    ) -> list[dict[str, Any]]:
        url = f'{self.BASE_URL}/repositories/{workspace}/{repo_slug}/hooks'
        return await self._fetch_paginated_data(url, {}, max_items=100)

    async def check_webhook_exists_on_repository(
        self, workspace: str, repo_slug: str, webhook_url: str
    ) -> tuple[bool, str | None]:
        webhooks = await self.get_repository_webhooks(workspace, repo_slug)
        for webhook in webhooks:
            if webhook.get('url') == webhook_url:
                return True, webhook.get('uuid')
        return False, None

    async def create_repository_webhook(
        self,
        *,
        workspace: str,
        repo_slug: str,
        description: str,
        webhook_url: str,
        webhook_secret: str,
        events: list[str],
    ) -> str | None:
        url = f'{self.BASE_URL}/repositories/{workspace}/{repo_slug}/hooks'
        payload = {
            'description': description,
            'url': webhook_url,
            'active': True,
            'secret': webhook_secret,
            'events': events,
        }
        response, _ = await self._make_request(
            url=url,
            params=payload,
            method=RequestMethod.POST,
        )
        return response.get('uuid') if response else None

    async def update_repository_webhook(
        self,
        *,
        workspace: str,
        repo_slug: str,
        webhook_uuid: str,
        description: str,
        webhook_url: str,
        webhook_secret: str,
        events: list[str],
    ) -> str | None:
        url = (
            f'{self.BASE_URL}/repositories/{workspace}/{repo_slug}/hooks/{webhook_uuid}'
        )
        payload = {
            'description': description,
            'url': webhook_url,
            'active': True,
            'secret': webhook_secret,
            'events': events,
        }
        response, _ = await self._make_request(
            url=url,
            params=payload,
            method=RequestMethod.PUT,
        )
        return response.get('uuid') if response else None

    async def delete_repository_webhook(
        self, workspace: str, repo_slug: str, webhook_uuid: str
    ) -> None:
        url = (
            f'{self.BASE_URL}/repositories/{workspace}/{repo_slug}/hooks/{webhook_uuid}'
        )
        await self._make_request(url=url, method=RequestMethod.DELETE)

    async def user_has_admin_access(self, workspace: str, repo_slug: str) -> bool:
        url = f'{self.BASE_URL}/user/permissions/repositories'
        params = {'q': f'repository.full_name="{workspace}/{repo_slug}"'}
        response, _ = await self._make_request(url, params)
        for entry in response.get('values', []):
            if entry.get('permission') == 'admin':
                return True
        return False
