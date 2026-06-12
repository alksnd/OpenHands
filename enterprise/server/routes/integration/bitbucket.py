from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from integrations.bitbucket.bitbucket_manager import BitbucketManager
from integrations.bitbucket.bitbucket_service import SaaSBitBucketService
from integrations.models import Message, SourceType
from integrations.utils import HOST_URL, IS_LOCAL_DEPLOYMENT
from pydantic import BaseModel
from server.auth.token_manager import TokenManager
from storage.bitbucket_webhook_store import BitbucketWebhookStore
from storage.redis import get_redis_client_async

from openhands.app_server.types import AppMode
from openhands.app_server.user_auth import get_user_id
from openhands.app_server.utils.logger import openhands_logger as logger

bitbucket_integration_router = APIRouter(prefix='/integration')

webhook_store = BitbucketWebhookStore()
token_manager = TokenManager()
bitbucket_manager = BitbucketManager(token_manager)

BITBUCKET_WEBHOOK_NAME = 'OpenHands Resolver'
BITBUCKET_WEBHOOK_EVENTS = ['pullrequest:comment_created']
BITBUCKET_WEBHOOK_URL = f'{HOST_URL}/integration/bitbucket/events'


class BitbucketResourceIdentifier(BaseModel):
    workspace: str
    repo_slug: str


class BitbucketResourceWithWebhookStatus(BaseModel):
    workspace: str
    repo_slug: str
    name: str
    full_name: str
    type: str = 'repository'
    webhook_installed: bool
    webhook_exists_on_provider: bool
    webhook_uuid: str | None
    webhook_secret_set: bool
    installed_by_user_id: str | None
    last_synced: str | None


class BitbucketResourcesResponse(BaseModel):
    resources: list[BitbucketResourceWithWebhookStatus]


class BitbucketWebhookRequest(BaseModel):
    resource: BitbucketResourceIdentifier


class BitbucketWebhookInstallationResult(BaseModel):
    workspace: str
    repo_slug: str
    success: bool
    error: str | None
    webhook_uuid: str | None


def _normalize_resource(resource: BitbucketResourceIdentifier) -> tuple[str, str]:
    workspace = resource.workspace.strip()
    repo_slug = resource.repo_slug.strip()
    if not workspace or not repo_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='workspace and repo_slug are required',
        )
    return workspace, repo_slug


def _split_repo_full_name(full_name: str) -> tuple[str, str] | None:
    workspace, separator, repo_slug = full_name.partition('/')
    if not separator or not workspace or not repo_slug:
        return None
    return workspace, repo_slug


async def _ensure_admin_access(
    bitbucket_service: SaaSBitBucketService,
    workspace: str,
    repo_slug: str,
) -> None:
    if not await bitbucket_service.user_has_admin_access(workspace, repo_slug):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='User does not have admin access to this repository',
        )


async def _get_or_create_cloud_webhook(
    bitbucket_service: SaaSBitBucketService,
    workspace: str,
    repo_slug: str,
    webhook_secret: str,
) -> str | None:
    (
        webhook_exists,
        webhook_uuid,
    ) = await bitbucket_service.check_webhook_exists_on_repository(
        workspace, repo_slug, BITBUCKET_WEBHOOK_URL
    )
    if webhook_exists and webhook_uuid:
        return await bitbucket_service.update_repository_webhook(
            workspace=workspace,
            repo_slug=repo_slug,
            webhook_uuid=webhook_uuid,
            description=BITBUCKET_WEBHOOK_NAME,
            webhook_url=BITBUCKET_WEBHOOK_URL,
            webhook_secret=webhook_secret,
            events=BITBUCKET_WEBHOOK_EVENTS,
        )

    return await bitbucket_service.create_repository_webhook(
        workspace=workspace,
        repo_slug=repo_slug,
        description=BITBUCKET_WEBHOOK_NAME,
        webhook_url=BITBUCKET_WEBHOOK_URL,
        webhook_secret=webhook_secret,
        events=BITBUCKET_WEBHOOK_EVENTS,
    )


async def _safe_user_has_admin_access(
    bitbucket_service: SaaSBitBucketService,
    workspace: str,
    repo_slug: str,
) -> bool:
    try:
        return await bitbucket_service.user_has_admin_access(workspace, repo_slug)
    except Exception:
        logger.warning(
            f'[Bitbucket] Admin access check failed for {workspace}/{repo_slug}',
            exc_info=True,
        )
        return False


async def _safe_check_cloud_webhook(
    bitbucket_service: SaaSBitBucketService,
    workspace: str,
    repo_slug: str,
) -> tuple[bool, str | None]:
    try:
        return await bitbucket_service.check_webhook_exists_on_repository(
            workspace, repo_slug, BITBUCKET_WEBHOOK_URL
        )
    except Exception:
        logger.warning(
            f'[Bitbucket] Webhook status check failed for {workspace}/{repo_slug}',
            exc_info=True,
        )
        return False, None


async def verify_bitbucket_signature(
    *,
    signature_header: str | None,
    body: bytes,
    webhook_uuid: str | None,
) -> None:
    """Verify ``X-Hub-Signature`` against the per-installation secret.

    Bitbucket Cloud sends ``X-Hook-Uuid`` (unique per installed webhook)
    and ``X-Hub-Signature: sha256=<hex>`` (only when the workspace admin
    sets a secret on the webhook). The webhook record is keyed by the
    Bitbucket-issued ``webhook_uuid``; ``BitbucketWebhook.webhook_uuid`` is
    unique, so a single-key lookup is sufficient.
    """
    if not webhook_uuid:
        raise HTTPException(status_code=403, detail='Missing X-Hook-Uuid header')

    if IS_LOCAL_DEPLOYMENT:
        webhook_secret: str | None = 'localdeploymentwebhooktesttoken'
    else:
        webhook_secret = await webhook_store.get_webhook_secret(
            webhook_uuid=webhook_uuid
        )

    if not webhook_secret:
        raise HTTPException(
            status_code=403, detail='No webhook secret found for installation'
        )

    if IS_LOCAL_DEPLOYMENT and signature_header in (
        None,
        'localdeploymentwebhooktesttoken',
    ):
        return

    if not signature_header:
        raise HTTPException(status_code=403, detail='Missing X-Hub-Signature header')

    expected = (
        'sha256=' + hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=403, detail="Request signatures didn't match!")


@bitbucket_integration_router.get('/bitbucket/resources')
async def get_bitbucket_resources(
    user_id: str = Depends(get_user_id),
) -> BitbucketResourcesResponse:
    """List Bitbucket Cloud repositories where the user can install webhooks."""
    try:
        bitbucket_service = SaaSBitBucketService(external_auth_id=user_id)
        repositories = await bitbucket_service.get_all_repositories(
            sort='updated', app_mode=AppMode.SAAS
        )

        repo_identities: list[tuple[str, str]] = []
        for repo in repositories:
            identity = _split_repo_full_name(repo.full_name)
            if identity:
                repo_identities.append(identity)

        admin_checks = await asyncio.gather(
            *[
                _safe_user_has_admin_access(bitbucket_service, workspace, repo_slug)
                for workspace, repo_slug in repo_identities
            ]
        )
        admin_repo_identities = [
            repo_identity
            for repo_identity, has_admin_access in zip(repo_identities, admin_checks)
            if has_admin_access
        ]

        webhook_map = await webhook_store.get_webhooks_by_repos(admin_repo_identities)
        provider_checks = await asyncio.gather(
            *[
                _safe_check_cloud_webhook(bitbucket_service, workspace, repo_slug)
                for workspace, repo_slug in admin_repo_identities
            ]
        )

        resources: list[BitbucketResourceWithWebhookStatus] = []
        for (workspace, repo_slug), (provider_exists, provider_uuid) in zip(
            admin_repo_identities, provider_checks
        ):
            webhook = webhook_map.get((workspace, repo_slug))
            db_uuid = webhook.webhook_uuid if webhook else None
            webhook_installed = bool(
                provider_exists
                and provider_uuid
                and webhook
                and webhook.webhook_secret
                and db_uuid == provider_uuid
            )
            resources.append(
                BitbucketResourceWithWebhookStatus(
                    workspace=workspace,
                    repo_slug=repo_slug,
                    name=repo_slug,
                    full_name=f'{workspace}/{repo_slug}',
                    webhook_installed=webhook_installed,
                    webhook_exists_on_provider=provider_exists,
                    webhook_uuid=db_uuid,
                    webhook_secret_set=bool(webhook and webhook.webhook_secret),
                    installed_by_user_id=webhook.user_id if webhook else None,
                    last_synced=(
                        webhook.last_synced.isoformat()
                        if webhook and webhook.last_synced
                        else None
                    ),
                )
            )

        return BitbucketResourcesResponse(resources=resources)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f'Error retrieving Bitbucket resources: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to retrieve Bitbucket resources',
        )


@bitbucket_integration_router.post('/bitbucket/reinstall-webhook')
async def reinstall_bitbucket_webhook(
    body: BitbucketWebhookRequest,
    user_id: str = Depends(get_user_id),
) -> BitbucketWebhookInstallationResult:
    workspace, repo_slug = _normalize_resource(body.resource)
    bitbucket_service = SaaSBitBucketService(external_auth_id=user_id)

    try:
        await _ensure_admin_access(bitbucket_service, workspace, repo_slug)
        webhook_secret = secrets.token_urlsafe(32)
        webhook_uuid = await _get_or_create_cloud_webhook(
            bitbucket_service, workspace, repo_slug, webhook_secret
        )
        if not webhook_uuid:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to install Bitbucket webhook',
            )

        await webhook_store.upsert_webhook_enrollment(
            workspace=workspace,
            repo_slug=repo_slug,
            user_id=user_id,
            webhook_uuid=webhook_uuid,
            webhook_secret=webhook_secret,
        )

        return BitbucketWebhookInstallationResult(
            workspace=workspace,
            repo_slug=repo_slug,
            success=True,
            error=None,
            webhook_uuid=webhook_uuid,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f'Error installing Bitbucket webhook: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to install Bitbucket webhook',
        )


@bitbucket_integration_router.post('/bitbucket/uninstall-webhook')
async def uninstall_bitbucket_webhook(
    body: BitbucketWebhookRequest,
    user_id: str = Depends(get_user_id),
) -> BitbucketWebhookInstallationResult:
    workspace, repo_slug = _normalize_resource(body.resource)
    bitbucket_service = SaaSBitBucketService(external_auth_id=user_id)

    try:
        await _ensure_admin_access(bitbucket_service, workspace, repo_slug)
        webhook = await webhook_store.get_webhook_by_repo(workspace, repo_slug)
        (
            provider_exists,
            provider_uuid,
        ) = await bitbucket_service.check_webhook_exists_on_repository(
            workspace, repo_slug, BITBUCKET_WEBHOOK_URL
        )
        db_uuid = webhook.webhook_uuid if webhook else None
        webhook_uuid = provider_uuid or db_uuid
        if provider_uuid:
            await bitbucket_service.delete_repository_webhook(
                workspace, repo_slug, provider_uuid
            )
        elif provider_exists:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to locate Bitbucket webhook id',
            )

        await webhook_store.delete_webhook_by_repo(
            workspace=workspace,
            repo_slug=repo_slug,
        )

        return BitbucketWebhookInstallationResult(
            workspace=workspace,
            repo_slug=repo_slug,
            success=True,
            error=None,
            webhook_uuid=webhook_uuid,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f'Error uninstalling Bitbucket webhook: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to uninstall Bitbucket webhook',
        )


@bitbucket_integration_router.post('/bitbucket/events')
async def bitbucket_events(
    request: Request,
    x_hub_signature: str | None = Header(None),
    x_event_key: str | None = Header(None),
    x_request_uuid: str | None = Header(None),
    x_hook_uuid: str | None = Header(None),
):
    try:
        body = await request.body()
        await verify_bitbucket_signature(
            signature_header=x_hub_signature,
            body=body,
            webhook_uuid=x_hook_uuid,
        )

        payload_data = json.loads(body) if body else {}
        pr_id = (payload_data.get('pullrequest') or {}).get('id')
        comment_id = (payload_data.get('comment') or {}).get('id')

        # Dedup by (event_key, pr_id, comment_id, request_uuid). Falls back to
        # a hash of the body when the request UUID is missing.
        if x_request_uuid:
            dedup_key = f'bb:{x_event_key}:{pr_id}:{comment_id}:{x_request_uuid}'
        else:
            dedup_hash = hashlib.sha256(body).hexdigest()
            dedup_key = f'bitbucket_msg:{dedup_hash}'

        redis = get_redis_client_async()
        created = await redis.set(dedup_key, 1, nx=True, ex=60)
        if not created:
            logger.info('bitbucket_is_duplicate')
            return JSONResponse(
                status_code=200,
                content={'message': 'Duplicate Bitbucket event ignored.'},
            )

        message = Message(
            source=SourceType.BITBUCKET,
            message={
                'payload': payload_data,
                'event_key': x_event_key,
                'installation_id': x_hook_uuid,
            },
        )
        await bitbucket_manager.receive_message(message)

        return JSONResponse(
            status_code=200,
            content={'message': 'Bitbucket events endpoint reached successfully.'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f'Error processing Bitbucket event: {e}')
        return JSONResponse(status_code=400, content={'error': 'Invalid payload.'})
