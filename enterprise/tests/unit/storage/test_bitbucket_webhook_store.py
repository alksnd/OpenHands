"""Unit tests for BitbucketWebhookStore."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from storage.base import Base
from storage.bitbucket_webhook import BitbucketWebhook
from storage.bitbucket_webhook_store import BitbucketWebhookStore


@pytest.fixture(scope='function')
def event_loop():
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='function')
async def async_engine(event_loop):
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        poolclass=StaticPool,
        connect_args={'check_same_thread': False},
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(scope='function')
async def async_session_maker(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def webhook_store(async_session_maker):
    import storage.bitbucket_webhook_store as store_module

    store_module.a_session_maker = async_session_maker
    return BitbucketWebhookStore()


@pytest.fixture
async def sample_webhook(async_session_maker):
    async with async_session_maker() as session:
        webhook = BitbucketWebhook(
            workspace='acme',
            repo_slug='myrepo',
            user_id='kc-installer',
            webhook_uuid='{hook-uuid}',
            webhook_secret='shared-secret',
        )
        session.add(webhook)
        await session.commit()
        await session.refresh(webhook)
    return webhook


@pytest.mark.asyncio
async def test_get_webhook_secret_returns_secret_for_matching_uuid(
    webhook_store, sample_webhook
):
    secret = await webhook_store.get_webhook_secret(webhook_uuid='{hook-uuid}')
    assert secret == 'shared-secret'


@pytest.mark.asyncio
async def test_get_webhook_user_id_returns_installer_keycloak_id(
    webhook_store, sample_webhook
):
    user_id = await webhook_store.get_webhook_user_id(webhook_uuid='{hook-uuid}')
    assert user_id == 'kc-installer'


@pytest.mark.asyncio
async def test_get_webhooks_by_repos_returns_matching_webhooks(
    webhook_store, sample_webhook
):
    webhook_map = await webhook_store.get_webhooks_by_repos(
        [('acme', 'myrepo'), ('other', 'nope')]
    )

    assert list(webhook_map.keys()) == [('acme', 'myrepo')]
    assert webhook_map[('acme', 'myrepo')].webhook_secret == 'shared-secret'


@pytest.mark.asyncio
async def test_upsert_webhook_enrollment_creates_row(webhook_store):
    webhook = await webhook_store.upsert_webhook_enrollment(
        workspace='acme',
        repo_slug='newrepo',
        user_id='kc-user',
        webhook_uuid='{new-hook}',
        webhook_secret='new-secret',
    )

    assert webhook.workspace == 'acme'
    assert webhook.repo_slug == 'newrepo'
    assert webhook.user_id == 'kc-user'
    assert webhook.webhook_uuid == '{new-hook}'
    assert webhook.webhook_secret == 'new-secret'


@pytest.mark.asyncio
async def test_upsert_webhook_enrollment_updates_existing_row(
    webhook_store, sample_webhook
):
    webhook = await webhook_store.upsert_webhook_enrollment(
        workspace='acme',
        repo_slug='myrepo',
        user_id='kc-new-installer',
        webhook_uuid='{rotated-hook}',
        webhook_secret='rotated-secret',
    )

    assert webhook.id == sample_webhook.id
    assert webhook.user_id == 'kc-new-installer'
    assert webhook.webhook_uuid == '{rotated-hook}'
    assert webhook.webhook_secret == 'rotated-secret'


@pytest.mark.asyncio
async def test_delete_webhook_by_repo_removes_row(webhook_store, sample_webhook):
    deleted = await webhook_store.delete_webhook_by_repo(
        workspace='acme',
        repo_slug='myrepo',
    )

    assert deleted is True
    webhook = await webhook_store.get_webhook_by_repo('acme', 'myrepo')
    assert webhook is None
