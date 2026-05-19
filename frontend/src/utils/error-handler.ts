import { handleStatusMessage } from "#/services/actions";
import { displayErrorToast } from "./custom-toast-handlers";

interface ErrorDetails {
  message: string;
  source?: string;
  metadata?: Record<string, unknown>;
  msgId?: string;
}

// PostHog capture removed — error tracking is now handled server-side
export function trackError(
  details: ErrorDetails, // eslint-disable-line @typescript-eslint/no-unused-vars
): void {}

export function showErrorToast({
  message,
  source,
  metadata = {},
}: ErrorDetails) {
  trackError({ message, source, metadata });
  displayErrorToast(message);
}

export function showChatError({
  message,
  source,
  metadata = {},
  msgId,
}: ErrorDetails) {
  trackError({ message, source, metadata });
  handleStatusMessage({
    type: "error",
    message,
    id: msgId,
    status_update: true,
  });
}

/**
 * Checks if an error message indicates a budget or credit limit issue
 */
export function isBudgetOrCreditError(errorMessage: string): boolean {
  const lowerCaseError = errorMessage.toLowerCase();
  return lowerCaseError.includes("budget") || lowerCaseError.includes("credit");
}

/**
 * Checks if an error message indicates a model/provider configuration issue.
 * Common when users enter bare model names (e.g. "deepseek-chat" instead of
 * "deepseek/deepseek-chat") or misconfigure the LLM provider.
 */
export function isModelConfigurationError(errorMessage: string): boolean {
  const lowerCaseError = errorMessage.toLowerCase();
  return (
    lowerCaseError.includes("llm provider not provided") ||
    lowerCaseError.includes("llm provider not found") ||
    (lowerCaseError.includes("badrequest") &&
      lowerCaseError.includes("provider")) ||
    (lowerCaseError.includes("bad request") &&
      lowerCaseError.includes("provider"))
  );
}
