import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { GitControlBarRepoButton } from "./git-control-bar-repo-button";
import { GitControlBarBranchButton } from "./git-control-bar-branch-button";
import { GitControlBarPullButton } from "./git-control-bar-pull-button";
import { GitControlBarPushButton } from "./git-control-bar-push-button";
import { GitControlBarPrButton } from "./git-control-bar-pr-button";
import { useActiveConversation } from "#/hooks/query/use-active-conversation";
import { useTaskPolling } from "#/hooks/query/use-task-polling";
import { useUnifiedWebSocketStatus } from "#/hooks/use-unified-websocket-status";
import { useSendMessage } from "#/hooks/use-send-message";
import { useUpdateConversationRepository } from "#/hooks/mutation/use-update-conversation-repository";
import { useRepositoryOnboardingFiles } from "#/hooks/query/use-repository-onboarding-files";
import { Provider } from "#/types/settings";
import { Branch, GitRepository } from "#/types/git";
import { I18nKey } from "#/i18n/declaration";
import { GitControlBarTooltipWrapper } from "./git-control-bar-tooltip-wrapper";
import { OpenRepositoryModal } from "./open-repository-modal";
import { OnboardingPluginModal } from "#/components/features/home/onboarding-plugin-modal";
import { displayErrorToast } from "#/utils/custom-toast-handlers";
import { needsOnboarding } from "#/utils/onboarding-utils";
import { useHomeStore } from "#/stores/home-store";
import { useOptimisticUserMessageStore } from "#/stores/optimistic-user-message-store";

interface GitControlBarProps {
  onSuggestionsClick: (value: string) => void;
}

// localStorage key for tracking onboarding modal dismissal per conversation
const ONBOARDING_MODAL_SHOWN_KEY_PREFIX = "onboarding-modal-shown-";

function getOnboardingModalShownKey(conversationId: string): string {
  return `${ONBOARDING_MODAL_SHOWN_KEY_PREFIX}${conversationId}`;
}

function wasOnboardingModalShown(conversationId: string | undefined): boolean {
  if (!conversationId) return false;
  try {
    return (
      localStorage.getItem(getOnboardingModalShownKey(conversationId)) ===
      "true"
    );
  } catch {
    return false;
  }
}

function markOnboardingModalShown(conversationId: string | undefined): void {
  if (!conversationId) return;
  try {
    localStorage.setItem(getOnboardingModalShownKey(conversationId), "true");
  } catch {
    // Ignore localStorage errors
  }
}

export function GitControlBar({ onSuggestionsClick }: GitControlBarProps) {
  const { t } = useTranslation();
  const { conversationId } = useParams<{ conversationId: string }>();
  const [isOpenRepoModalOpen, setIsOpenRepoModalOpen] = useState(false);
  const [showOnboardingModal, setShowOnboardingModal] = useState(false);
  const { addRecentRepository } = useHomeStore();
  const { setOptimisticUserMessage } = useOptimisticUserMessageStore();

  const { data: conversation } = useActiveConversation();
  const { repositoryInfo } = useTaskPolling();
  const webSocketStatus = useUnifiedWebSocketStatus();
  const webSocketStatusRef = useRef(webSocketStatus);
  useEffect(() => {
    webSocketStatusRef.current = webSocketStatus;
  }, [webSocketStatus]);
  const { send } = useSendMessage();
  const sendRef = useRef(send);
  useEffect(() => {
    sendRef.current = send;
  }, [send]);
  const { mutate: updateRepository } = useUpdateConversationRepository();

  // Priority: conversation data > task data
  // This ensures we show repository info immediately from task, then transition to conversation data
  const selectedRepository =
    conversation?.selected_repository || repositoryInfo?.selectedRepository;
  const gitProvider = (conversation?.git_provider ||
    repositoryInfo?.gitProvider) as Provider;
  const selectedBranch =
    conversation?.selected_branch || repositoryInfo?.selectedBranch;

  const hasRepository = !!selectedRepository;

  // Enable buttons only when conversation exists and WS is connected
  const isConversationReady = !!conversation && webSocketStatus === "OPEN";

  // Check onboarding files for the current repository
  const { data: onboardingFiles } = useRepositoryOnboardingFiles(
    selectedRepository,
    gitProvider,
    selectedBranch,
    hasRepository,
  );

  // Show onboarding modal once per conversation when repo needs onboarding
  // This handles both:
  // 1. Conversation loaded with a repo that needs onboarding
  // 2. User connected a new repo via OpenRepositoryModal
  // The modal only shows once per conversation (persisted in localStorage)
  // We wait until isConversationReady (WebSocket connected) to ensure:
  // - The conversation state is stable (no double-firing)
  // - "Load Plugin" can send a message immediately
  useEffect(() => {
    // Must have a valid conversationId to track in localStorage
    if (!conversationId) {
      return;
    }

    // Wait until the conversation is ready (WebSocket connected)
    // This ensures stable state and that "Load Plugin" works immediately
    if (!isConversationReady) {
      return;
    }

    // Check localStorage synchronously - prevents race conditions
    if (wasOnboardingModalShown(conversationId)) {
      return;
    }

    if (hasRepository && needsOnboarding(onboardingFiles)) {
      // Mark as shown BEFORE updating state to prevent double-firing
      markOnboardingModalShown(conversationId);
      setShowOnboardingModal(true);
    }
  }, [hasRepository, onboardingFiles, conversationId, isConversationReady]);

  const handleOnboardingDismiss = useCallback(() => {
    setShowOnboardingModal(false);
  }, []);

  const handleOnboardingLoadPlugin = useCallback(() => {
    setShowOnboardingModal(false);

    // Check WebSocket is connected before sending
    if (webSocketStatusRef.current !== "OPEN") {
      displayErrorToast(t(I18nKey.CHAT_INTERFACE$DISCONNECTED));
      return;
    }

    // Send message to agent to add the onboarding plugin and run setup-openhands
    const onboardingPrompt = `/add-skill https://github.com/OpenHands/extensions/tree/main/plugins/onboarding

After adding the skill, run \`setup-openhands\` to configure this repository for OpenHands.`;

    setOptimisticUserMessage(onboardingPrompt);
    sendRef.current({
      action: "message",
      args: {
        content: onboardingPrompt,
        timestamp: new Date().toISOString(),
      },
    });
  }, [t, setOptimisticUserMessage]);

  const handleLaunchRepository = (
    repository: GitRepository,
    branch: Branch,
  ) => {
    if (!conversationId) return;

    // Persist to recent repositories list (matches home page behavior)
    addRecentRepository(repository);

    // Note: We update repository metadata first, then send clone command.
    // The clone command is sent to the agent via WebSocket (fire-and-forget).
    // If cloning fails, the agent will report the error in the chat,
    // and the user can retry or change the repository.
    // This is a trade-off: immediate UI feedback vs. strict atomicity.
    updateRepository(
      {
        conversationId,
        repository: repository.full_name,
        branch: branch.name,
        gitProvider: repository.git_provider,
      },
      {
        onSuccess: () => {
          // Use ref to read the latest WebSocket status (avoids stale closure)
          if (webSocketStatusRef.current !== "OPEN") {
            displayErrorToast(
              t(I18nKey.CONVERSATION$CLONE_COMMAND_FAILED_DISCONNECTED),
            );
            return;
          }

          // Send clone command to agent after metadata is updated
          // Use ref to always call the latest send function (avoids stale closure
          // where V1 sendMessage holds a reference to a now-closed WebSocket)
          // Include git provider in prompt so agent clones from correct source
          const providerName =
            repository.git_provider.charAt(0).toUpperCase() +
            repository.git_provider.slice(1);
          const clonePrompt = `Clone ${repository.full_name} from ${providerName} and checkout branch ${branch.name}.`;
          setOptimisticUserMessage(clonePrompt);
          sendRef.current({
            action: "message",
            args: {
              content: clonePrompt,
              timestamp: new Date().toISOString(),
            },
          });
        },
      },
    );
  };

  return (
    <div className="flex flex-row items-center">
      <div className="flex flex-row gap-2.5 items-center overflow-x-auto flex-wrap md:flex-nowrap relative scrollbar-hide">
        <GitControlBarRepoButton
          selectedRepository={selectedRepository}
          gitProvider={gitProvider}
          onClick={() => setIsOpenRepoModalOpen(true)}
          disabled={!isConversationReady}
        />

        <GitControlBarTooltipWrapper
          tooltipMessage={t(I18nKey.COMMON$GIT_TOOLS_DISABLED_CONTENT)}
          testId="git-control-bar-branch-button-tooltip"
          shouldShowTooltip={!hasRepository}
        >
          <GitControlBarBranchButton
            selectedBranch={selectedBranch}
            selectedRepository={selectedRepository}
            gitProvider={gitProvider}
          />
        </GitControlBarTooltipWrapper>

        {hasRepository ? (
          <>
            <GitControlBarTooltipWrapper
              tooltipMessage={t(I18nKey.COMMON$GIT_TOOLS_DISABLED_CONTENT)}
              testId="git-control-bar-pull-button-tooltip"
              shouldShowTooltip={!hasRepository}
            >
              <GitControlBarPullButton
                onSuggestionsClick={onSuggestionsClick}
                isConversationReady={isConversationReady}
              />
            </GitControlBarTooltipWrapper>

            <GitControlBarTooltipWrapper
              tooltipMessage={t(I18nKey.COMMON$GIT_TOOLS_DISABLED_CONTENT)}
              testId="git-control-bar-push-button-tooltip"
              shouldShowTooltip={!hasRepository}
            >
              <GitControlBarPushButton
                onSuggestionsClick={onSuggestionsClick}
                hasRepository={hasRepository}
                currentGitProvider={gitProvider}
                isConversationReady={isConversationReady}
              />
            </GitControlBarTooltipWrapper>

            <GitControlBarTooltipWrapper
              tooltipMessage={t(I18nKey.COMMON$GIT_TOOLS_DISABLED_CONTENT)}
              testId="git-control-bar-pr-button-tooltip"
              shouldShowTooltip={!hasRepository}
            >
              <GitControlBarPrButton
                onSuggestionsClick={onSuggestionsClick}
                hasRepository={hasRepository}
                currentGitProvider={gitProvider}
                isConversationReady={isConversationReady}
              />
            </GitControlBarTooltipWrapper>
          </>
        ) : null}
      </div>

      <OpenRepositoryModal
        isOpen={isOpenRepoModalOpen}
        onClose={() => setIsOpenRepoModalOpen(false)}
        onLaunch={handleLaunchRepository}
        defaultProvider={gitProvider}
      />

      {showOnboardingModal && (
        <OnboardingPluginModal
          onLoadPlugin={handleOnboardingLoadPlugin}
          onDismiss={handleOnboardingDismiss}
        />
      )}
    </div>
  );
}
