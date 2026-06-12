import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { integrationService } from "#/api/integration-service/integration-service.api";
import type {
  BitbucketResourceIdentifier,
  BitbucketWebhookInstallationResult,
} from "#/api/integration-service/integration-service.types";
import { I18nKey } from "#/i18n/declaration";
import {
  displayErrorToast,
  displaySuccessToast,
} from "#/utils/custom-toast-handlers";

export function useUninstallBitbucketWebhook() {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  return useMutation<
    BitbucketWebhookInstallationResult,
    Error,
    BitbucketResourceIdentifier,
    unknown
  >({
    mutationFn: (resource: BitbucketResourceIdentifier) =>
      integrationService.uninstallBitbucketWebhook({ resource }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["bitbucket-resources"] });

      if (data.success) {
        displaySuccessToast(t(I18nKey.BITBUCKET$WEBHOOK_UNINSTALL_SUCCESS));
      } else if (data.error) {
        displayErrorToast(data.error);
      } else {
        displayErrorToast(t(I18nKey.BITBUCKET$WEBHOOK_UNINSTALL_FAILED));
      }
    },
    onError: (error) => {
      displayErrorToast(
        error?.message || t(I18nKey.BITBUCKET$WEBHOOK_UNINSTALL_FAILED),
      );
    },
  });
}
