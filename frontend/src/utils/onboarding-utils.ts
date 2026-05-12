import { RepositoryOnboardingFiles } from "#/types/git";

/**
 * Check if a repository needs onboarding (neither AGENTS.md nor REPO.md exists)
 * @param onboardingFiles The onboarding files status from the API
 * @returns true if the repository needs onboarding, false otherwise
 */
export function needsOnboarding(
  onboardingFiles: RepositoryOnboardingFiles | undefined | null,
): boolean {
  if (!onboardingFiles) {
    return false;
  }
  return !onboardingFiles.has_agents_md && !onboardingFiles.has_repo_md;
}
