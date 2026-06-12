from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from storage.bitbucket_webhook import BitbucketWebhook
from storage.database import a_session_maker


@dataclass
class BitbucketWebhookStore:
    """Read/write helpers for the ``bitbucket_webhook`` table.

    Used by the resolver webhook route to look up the per-installation
    secret needed to verify ``X-Hub-Signature``.
    """

    async def get_webhook_secret(self, webhook_uuid: str) -> str | None:
        """Return the shared secret for ``webhook_uuid``, or None."""
        async with a_session_maker() as session:
            query = (
                select(BitbucketWebhook)
                .where(BitbucketWebhook.webhook_uuid == webhook_uuid)
                .limit(1)
            )
            result = await session.execute(query)
            webhook = result.scalars().first()
            return webhook.webhook_secret if webhook else None

    async def get_webhook_user_id(self, webhook_uuid: str) -> str | None:
        """Return the keycloak ``user_id`` of the installer.

        Used by :class:`BitbucketManager` to resolve "who installed this
        webhook?" without depending on a per-actor Keycloak attribute
        mapper (which Bitbucket Cloud's built-in IdP cannot populate).
        """
        async with a_session_maker() as session:
            query = (
                select(BitbucketWebhook.user_id)
                .where(BitbucketWebhook.webhook_uuid == webhook_uuid)
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_webhook_by_repo(
        self, workspace: str, repo_slug: str
    ) -> BitbucketWebhook | None:
        async with a_session_maker() as session:
            query = (
                select(BitbucketWebhook)
                .where(
                    BitbucketWebhook.workspace == workspace,
                    BitbucketWebhook.repo_slug == repo_slug,
                )
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalars().first()

    async def get_webhooks_by_repos(
        self, repos: list[tuple[str, str]]
    ) -> dict[tuple[str, str], BitbucketWebhook]:
        if not repos:
            return {}

        async with a_session_maker() as session:
            clauses = [
                and_(
                    BitbucketWebhook.workspace == workspace,
                    BitbucketWebhook.repo_slug == repo_slug,
                )
                for workspace, repo_slug in repos
            ]
            query = select(BitbucketWebhook).where(or_(*clauses))
            result = await session.execute(query)
            webhooks = result.scalars().all()
            return {
                (webhook.workspace, webhook.repo_slug): webhook
                for webhook in webhooks
                if webhook.repo_slug
            }

    async def upsert_webhook_enrollment(
        self,
        *,
        workspace: str,
        repo_slug: str,
        user_id: str,
        webhook_uuid: str,
        webhook_secret: str,
    ) -> BitbucketWebhook:
        async with a_session_maker() as session:
            async with session.begin():
                query = (
                    select(BitbucketWebhook)
                    .where(
                        BitbucketWebhook.workspace == workspace,
                        BitbucketWebhook.repo_slug == repo_slug,
                    )
                    .limit(1)
                )
                result = await session.execute(query)
                webhook = result.scalars().first()

                if webhook:
                    webhook.user_id = user_id
                    webhook.webhook_uuid = webhook_uuid
                    webhook.webhook_secret = webhook_secret
                    webhook.last_synced = datetime.utcnow()
                else:
                    webhook = BitbucketWebhook(
                        workspace=workspace,
                        repo_slug=repo_slug,
                        user_id=user_id,
                        webhook_uuid=webhook_uuid,
                        webhook_secret=webhook_secret,
                    )
                    session.add(webhook)

            await session.refresh(webhook)
            return webhook

    async def delete_webhook_by_repo(self, *, workspace: str, repo_slug: str) -> bool:
        async with a_session_maker() as session:
            async with session.begin():
                stmt = delete(BitbucketWebhook).where(
                    BitbucketWebhook.workspace == workspace,
                    BitbucketWebhook.repo_slug == repo_slug,
                )
                result = await session.execute(stmt)
                return result.rowcount > 0

    @classmethod
    async def get_instance(cls) -> BitbucketWebhookStore:
        return BitbucketWebhookStore()
