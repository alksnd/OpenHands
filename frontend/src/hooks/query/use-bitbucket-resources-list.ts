import { useQuery } from "@tanstack/react-query";
import { integrationService } from "#/api/integration-service/integration-service.api";
import type { BitbucketResourcesResponse } from "#/api/integration-service/integration-service.types";

export function useBitbucketResources(enabled: boolean = true) {
  return useQuery<BitbucketResourcesResponse>({
    queryKey: ["bitbucket-resources"],
    queryFn: () => integrationService.getBitbucketResources(),
    enabled,
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 10,
  });
}
