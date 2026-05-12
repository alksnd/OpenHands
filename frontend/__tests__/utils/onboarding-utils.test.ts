import { describe, it, expect } from "vitest";
import { needsOnboarding } from "#/utils/onboarding-utils";

describe("needsOnboarding", () => {
  it("should return false when onboardingFiles is undefined", () => {
    expect(needsOnboarding(undefined)).toBe(false);
  });

  it("should return false when onboardingFiles is null", () => {
    expect(needsOnboarding(null)).toBe(false);
  });

  it("should return true when both AGENTS.md and REPO.md are missing", () => {
    expect(
      needsOnboarding({
        has_agents_md: false,
        has_repo_md: false,
      }),
    ).toBe(true);
  });

  it("should return false when AGENTS.md exists", () => {
    expect(
      needsOnboarding({
        has_agents_md: true,
        has_repo_md: false,
      }),
    ).toBe(false);
  });

  it("should return false when REPO.md exists", () => {
    expect(
      needsOnboarding({
        has_agents_md: false,
        has_repo_md: true,
      }),
    ).toBe(false);
  });

  it("should return false when both files exist", () => {
    expect(
      needsOnboarding({
        has_agents_md: true,
        has_repo_md: true,
      }),
    ).toBe(false);
  });
});
