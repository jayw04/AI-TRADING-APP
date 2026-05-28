import { ReactNode } from "react";

interface Props {
  title: string;
  count: number;
  asOf: string;
  children: ReactNode;
  helpText?: string;
}

export function Widget({ title, count, asOf, children, helpText }: Props) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <div>
          <h3 className="text-sm font-semibold text-neutral-100">
            {title}
            {count > 0 && (
              <span className="ml-2 rounded bg-sky-700 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                {count}
              </span>
            )}
          </h3>
          {helpText && (
            <div className="text-[10px] text-neutral-500">{helpText}</div>
          )}
        </div>
        <div className="text-[10px] text-neutral-500">
          {asOf ? new Date(asOf).toLocaleTimeString() : ""}
        </div>
      </div>
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="py-3 text-center text-xs text-neutral-500">{children}</div>
  );
}
