import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CREDENTIAL_KINDS,
  CredentialMetadata,
  credentialsApi,
} from "@/api/credentials";

const QUERY_KEY = ["credentials"];

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function CredentialCard({
  kind,
  label,
  meta,
}: {
  kind: string;
  label: string;
  meta: CredentialMetadata | undefined;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const isSet = meta?.has_value ?? false;

  const setMutation = useMutation({
    mutationFn: (v: string) => credentialsApi.set(kind, v),
    onSuccess: () => {
      setValue(""); // never keep plaintext in component state after submit
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: () => credentialsApi.revoke(kind),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-neutral-100">{label}</div>
          <div className="mt-1 flex items-center gap-2 text-xs">
            {isSet ? (
              <span className="rounded bg-green-900/50 px-1.5 py-0.5 text-green-300">
                Set
              </span>
            ) : (
              <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-400">
                Not set
              </span>
            )}
            {isSet && (
              <span className="text-neutral-500">
                last used {relativeTime(meta?.last_used_at ?? null)}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setEditing((e) => !e)}
            className="rounded bg-blue-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-600"
          >
            {isSet ? "Rotate" : "Set"}
          </button>
          {isSet && (
            <button
              type="button"
              onClick={() => {
                if (window.confirm(`Revoke ${label}? This cannot be undone via the UI.`)) {
                  revokeMutation.mutate();
                }
              }}
              disabled={revokeMutation.isPending}
              className="rounded bg-red-900/60 px-2.5 py-1 text-xs font-medium text-red-200 hover:bg-red-800 disabled:opacity-50"
            >
              Revoke
            </button>
          )}
        </div>
      </div>

      {editing && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (value) setMutation.mutate(value);
          }}
        >
          <input
            type="password"
            autoComplete="off"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={`New value for ${label}`}
            className="flex-1 rounded bg-neutral-800 px-2 py-1 font-mono text-sm text-white"
          />
          <button
            type="submit"
            disabled={!value || setMutation.isPending}
            className="rounded bg-green-700 px-3 py-1 text-xs font-semibold text-white hover:bg-green-600 disabled:opacity-50"
          >
            {setMutation.isPending ? "Saving…" : "Save"}
          </button>
        </form>
      )}

      {setMutation.isError && (
        <div className="mt-2 text-xs text-red-300">
          Failed to save. Check the value and try again.
        </div>
      )}
    </div>
  );
}

export default function Credentials() {
  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => credentialsApi.list(),
  });

  const byKind = new Map((data ?? []).map((m) => [m.kind, m]));

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-lg font-semibold text-neutral-100">Credentials</h1>
      <p className="mt-1 text-xs text-neutral-400">
        Secrets are encrypted at rest with the workbench master key. Values are
        never shown after you save them — rotate to replace, revoke to remove.
        Your TOTP secret is managed in the login/2FA flow, not here.
      </p>
      <p className="mt-2 text-xs text-amber-300/80">
        Note: the <span className="font-mono">Workbench MCP — Bearer Key</span>{" "}
        also lives in the <span className="font-mono">WORKBENCH_MCP_KEY</span>{" "}
        env var that the workbench-mcp container reads. If you rotate it here,
        update <span className="font-mono">.env</span> to the same value and
        recreate the container, or the MCP server will keep sending the old token
        and get 401s.
      </p>

      {isLoading && (
        <div className="mt-6 text-sm text-neutral-400">Loading…</div>
      )}
      {isError && (
        <div className="mt-6 text-sm text-red-300">
          Failed to load credentials.
        </div>
      )}

      {!isLoading && !isError && (
        <div className="mt-6 space-y-3">
          {CREDENTIAL_KINDS.map(({ kind, label }) => (
            <CredentialCard
              key={kind}
              kind={kind}
              label={label}
              meta={byKind.get(kind)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
