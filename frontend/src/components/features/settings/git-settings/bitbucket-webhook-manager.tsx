import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { BrandButton } from "#/components/features/settings/brand-button";
import type { BitbucketResource } from "#/api/integration-service/integration-service.types";
import { useBitbucketResources } from "#/hooks/query/use-bitbucket-resources-list";
import { useReinstallBitbucketWebhook } from "#/hooks/mutation/use-reinstall-bitbucket-webhook";
import { useUninstallBitbucketWebhook } from "#/hooks/mutation/use-uninstall-bitbucket-webhook";
import { I18nKey } from "#/i18n/declaration";
import { cn } from "#/utils/utils";
import { Typography } from "#/ui/typography";

interface BitbucketWebhookManagerProps {
  className?: string;
}

function resourceKey(resource: BitbucketResource) {
  return `${resource.workspace}/${resource.repo_slug}`;
}

function StatusBadge({ installed }: { installed: boolean }) {
  const { t } = useTranslation();

  if (installed) {
    return (
      <Typography.Text className="px-2 py-1 text-xs rounded bg-green-500/20 text-green-400">
        {t(I18nKey.BITBUCKET$WEBHOOK_STATUS_INSTALLED)}
      </Typography.Text>
    );
  }

  return (
    <Typography.Text className="px-2 py-1 text-xs rounded bg-gray-500/20 text-gray-400">
      {t(I18nKey.BITBUCKET$WEBHOOK_STATUS_NOT_INSTALLED)}
    </Typography.Text>
  );
}

export function BitbucketWebhookManager({
  className,
}: BitbucketWebhookManagerProps) {
  const { t } = useTranslation();
  const [installingResource, setInstallingResource] = useState<string | null>(
    null,
  );
  const [uninstallingResource, setUninstallingResource] = useState<
    string | null
  >(null);

  const { data, isLoading, isError } = useBitbucketResources(true);
  const reinstallMutation = useReinstallBitbucketWebhook();
  const uninstallMutation = useUninstallBitbucketWebhook();
  const resources = data?.resources || [];

  const handleReinstall = async (resource: BitbucketResource) => {
    const key = resourceKey(resource);
    setInstallingResource(key);
    try {
      await reinstallMutation.mutateAsync({
        workspace: resource.workspace,
        repo_slug: resource.repo_slug,
      });
    } finally {
      setInstallingResource(null);
    }
  };

  const handleUninstall = async (resource: BitbucketResource) => {
    const key = resourceKey(resource);
    setUninstallingResource(key);
    try {
      await uninstallMutation.mutateAsync({
        workspace: resource.workspace,
        repo_slug: resource.repo_slug,
      });
    } finally {
      setUninstallingResource(null);
    }
  };

  if (isLoading) {
    return (
      <div className={cn("flex flex-col gap-4", className)}>
        <Typography.H3 className="text-lg font-medium text-white">
          {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_TITLE)}
        </Typography.H3>
        <Typography.Text className="text-sm text-gray-400">
          {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_LOADING)}
        </Typography.Text>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={cn("flex flex-col gap-4", className)}>
        <Typography.H3 className="text-lg font-medium text-white">
          {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_TITLE)}
        </Typography.H3>
        <Typography.Text className="text-sm text-red-400">
          {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_ERROR)}
        </Typography.Text>
      </div>
    );
  }

  if (resources.length === 0) {
    return (
      <div className={cn("flex flex-col gap-4", className)}>
        <Typography.H3 className="text-lg font-medium text-white">
          {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_TITLE)}
        </Typography.H3>
        <Typography.Text className="text-sm text-gray-400">
          {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_NO_RESOURCES)}
        </Typography.Text>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div className="flex items-center justify-between">
        <Typography.H3 className="text-lg font-medium text-white">
          {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_TITLE)}
        </Typography.H3>
      </div>

      <Typography.Text className="text-sm text-gray-400">
        {t(I18nKey.BITBUCKET$WEBHOOK_MANAGER_DESCRIPTION)}
      </Typography.Text>

      <div className="border border-neutral-700 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-neutral-800">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                {t(I18nKey.BITBUCKET$WEBHOOK_COLUMN_REPOSITORY)}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                {t(I18nKey.BITBUCKET$WEBHOOK_COLUMN_STATUS)}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                {t(I18nKey.BITBUCKET$WEBHOOK_COLUMN_ACTION)}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-700">
            {resources.map((resource) => {
              const key = resourceKey(resource);
              const isInstalling = installingResource === key;
              const isUninstalling = uninstallingResource === key;
              let installButtonLabel = resource.webhook_installed
                ? t(I18nKey.BITBUCKET$WEBHOOK_REINSTALL)
                : t(I18nKey.BITBUCKET$WEBHOOK_INSTALL);
              if (isInstalling) {
                installButtonLabel = t(I18nKey.BITBUCKET$WEBHOOK_INSTALLING);
              }

              return (
                <tr
                  key={key}
                  className="hover:bg-neutral-800/50 transition-colors align-top"
                >
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <Typography.Text className="text-sm font-medium text-white">
                        {resource.name}
                      </Typography.Text>
                      <Typography.Text className="text-xs text-gray-400">
                        {resource.full_name}
                      </Typography.Text>
                      {resource.installed_by_user_id && (
                        <Typography.Text className="text-xs text-gray-500">
                          {t(I18nKey.BITBUCKET$WEBHOOK_INSTALLED_BY, {
                            userId: resource.installed_by_user_id,
                          })}
                        </Typography.Text>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge installed={resource.webhook_installed} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <BrandButton
                        type="button"
                        variant="primary"
                        onClick={() => handleReinstall(resource)}
                        isDisabled={
                          installingResource !== null ||
                          uninstallingResource !== null
                        }
                        className="cursor-pointer"
                        testId={`bitbucket-reinstall-webhook-${key}`}
                      >
                        {installButtonLabel}
                      </BrandButton>
                      <BrandButton
                        type="button"
                        variant="secondary"
                        onClick={() => handleUninstall(resource)}
                        isDisabled={
                          installingResource !== null ||
                          uninstallingResource !== null ||
                          (!resource.webhook_installed &&
                            !resource.webhook_exists_on_provider &&
                            !resource.webhook_secret_set)
                        }
                        className="cursor-pointer"
                        testId={`bitbucket-uninstall-webhook-${key}`}
                      >
                        {isUninstalling
                          ? t(I18nKey.BITBUCKET$WEBHOOK_UNINSTALLING)
                          : t(I18nKey.BITBUCKET$WEBHOOK_UNINSTALL)}
                      </BrandButton>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
