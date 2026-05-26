from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status

from openhands.app_server.sandbox.sandbox_models import (
    ExposedUrl,
    SandboxInfo,
    SandboxStatus,
)
from openhands.app_server.sandbox.sandbox_router import (
    _is_allowed_worker_url,
    get_web_host_status,
)

SANDBOX_ID = 'sb-test-123'
WORKER_URL = 'https://work-1-runtime.example.com/'


def _make_sandbox_info() -> SandboxInfo:
    return SandboxInfo(
        id=SANDBOX_ID,
        created_by_user_id='test-user-id',
        sandbox_spec_id='test-spec',
        status=SandboxStatus.RUNNING,
        session_api_key='session-key',
        exposed_urls=[
            ExposedUrl(name='WORKER_1', url=WORKER_URL, port=12000),
            ExposedUrl(
                name='VSCODE',
                url='https://vscode-runtime.example.com/',
                port=12001,
            ),
        ],
    )


def test_allows_only_registered_worker_urls():
    sandbox = _make_sandbox_info()

    assert _is_allowed_worker_url(sandbox, WORKER_URL)
    assert _is_allowed_worker_url(sandbox, WORKER_URL.rstrip('/'))
    assert not _is_allowed_worker_url(sandbox, 'https://vscode-runtime.example.com/')
    assert not _is_allowed_worker_url(sandbox, 'https://metadata.google.internal/')


@pytest.mark.asyncio
async def test_web_host_status_returns_probe_result_for_worker_url():
    sandbox_service = AsyncMock()
    sandbox_service.get_sandbox = AsyncMock(return_value=_make_sandbox_info())

    with patch(
        'openhands.app_server.sandbox.sandbox_router._probe_web_host',
        AsyncMock(return_value=True),
    ) as mock_probe:
        response = await get_web_host_status(
            sandbox_id=SANDBOX_ID,
            url=WORKER_URL,
            sandbox_service=sandbox_service,
        )

    assert response.reachable is True
    sandbox_service.get_sandbox.assert_awaited_once_with(SANDBOX_ID)
    mock_probe.assert_awaited_once_with(WORKER_URL)


@pytest.mark.asyncio
async def test_web_host_status_rejects_unregistered_urls():
    sandbox_service = AsyncMock()
    sandbox_service.get_sandbox = AsyncMock(return_value=_make_sandbox_info())

    with (
        patch(
            'openhands.app_server.sandbox.sandbox_router._probe_web_host',
            AsyncMock(return_value=True),
        ) as mock_probe,
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_web_host_status(
            sandbox_id=SANDBOX_ID,
            url='https://metadata.google.internal/',
            sandbox_service=sandbox_service,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    mock_probe.assert_not_called()


@pytest.mark.asyncio
async def test_web_host_status_returns_404_for_missing_sandbox():
    sandbox_service = AsyncMock()
    sandbox_service.get_sandbox = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_web_host_status(
            sandbox_id=SANDBOX_ID,
            url=WORKER_URL,
            sandbox_service=sandbox_service,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
