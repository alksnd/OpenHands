import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BitbucketWebhookManager } from "#/components/features/settings/git-settings/bitbucket-webhook-manager";
import { integrationService } from "#/api/integration-service/integration-service.api";
import type { BitbucketResource } from "#/api/integration-service/integration-service.types";
import { I18nKey } from "#/i18n/declaration";

vi.mock("#/utils/custom-toast-handlers", () => ({
  displaySuccessToast: vi.fn(),
  displayErrorToast: vi.fn(),
}));

const mockResources: BitbucketResource[] = [
  {
    workspace: "acme",
    repo_slug: "repo-1",
    name: "repo-1",
    full_name: "acme/repo-1",
    type: "repository",
    webhook_installed: false,
    webhook_exists_on_provider: false,
    webhook_uuid: null,
    webhook_secret_set: false,
    installed_by_user_id: null,
    last_synced: null,
  },
  {
    workspace: "acme",
    repo_slug: "repo-2",
    name: "repo-2",
    full_name: "acme/repo-2",
    type: "repository",
    webhook_installed: true,
    webhook_exists_on_provider: true,
    webhook_uuid: "{hook-2}",
    webhook_secret_set: true,
    installed_by_user_id: "kc-installer",
    last_synced: "2026-01-01T00:00:00",
  },
];

describe("BitbucketWebhookManager", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BitbucketWebhookManager />
      </QueryClientProvider>,
    );

  it("renders repositories with webhook status", async () => {
    vi.spyOn(integrationService, "getBitbucketResources").mockResolvedValue({
      resources: mockResources,
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("repo-1")).toBeInTheDocument();
      expect(screen.getByText("repo-2")).toBeInTheDocument();
    });

    expect(screen.getByText("acme/repo-1")).toBeInTheDocument();
    expect(screen.getByText("acme/repo-2")).toBeInTheDocument();
    expect(
      screen.getByText(I18nKey.BITBUCKET$WEBHOOK_STATUS_NOT_INSTALLED),
    ).toBeInTheDocument();
    expect(
      screen.getByText(I18nKey.BITBUCKET$WEBHOOK_STATUS_INSTALLED),
    ).toBeInTheDocument();
    expect(
      screen.getByText(I18nKey.BITBUCKET$WEBHOOK_INSTALLED_BY),
    ).toBeInTheDocument();
  });

  it("calls install endpoint for an uninstalled repository", async () => {
    const user = userEvent.setup();
    vi.spyOn(integrationService, "getBitbucketResources").mockResolvedValue({
      resources: mockResources,
    });
    const installSpy = vi
      .spyOn(integrationService, "reinstallBitbucketWebhook")
      .mockResolvedValue({
        workspace: "acme",
        repo_slug: "repo-1",
        success: true,
        error: null,
        webhook_uuid: "{hook-1}",
      });

    renderComponent();

    await user.click(
      await screen.findByTestId("bitbucket-reinstall-webhook-acme/repo-1"),
    );

    await waitFor(() => {
      expect(installSpy).toHaveBeenCalledWith({
        resource: {
          workspace: "acme",
          repo_slug: "repo-1",
        },
      });
    });
  });

  it("calls uninstall endpoint for an installed repository", async () => {
    const user = userEvent.setup();
    vi.spyOn(integrationService, "getBitbucketResources").mockResolvedValue({
      resources: mockResources,
    });
    const uninstallSpy = vi
      .spyOn(integrationService, "uninstallBitbucketWebhook")
      .mockResolvedValue({
        workspace: "acme",
        repo_slug: "repo-2",
        success: true,
        error: null,
        webhook_uuid: "{hook-2}",
      });

    renderComponent();

    await user.click(
      await screen.findByTestId("bitbucket-uninstall-webhook-acme/repo-2"),
    );

    await waitFor(() => {
      expect(uninstallSpy).toHaveBeenCalledWith({
        resource: {
          workspace: "acme",
          repo_slug: "repo-2",
        },
      });
    });
  });
});
