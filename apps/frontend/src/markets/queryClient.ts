import { QueryClient } from "@tanstack/react-query";

const tracked = new Set<QueryClient>();

export function defaultQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
  });
}

/** Remember a client so logout can drop every account's cached responses. */
export function trackQueryClient(client: QueryClient): () => void {
  tracked.add(client);
  return () => {
    tracked.delete(client);
  };
}

export function clearSessionCaches(): void {
  for (const client of tracked) client.clear();
}
