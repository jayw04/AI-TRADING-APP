export default function StubPage({ title }: { title: string }) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="rounded-lg bg-neutral-900 border border-neutral-800 px-12 py-10 text-center">
        <h2 className="text-2xl font-semibold text-neutral-100">{title}</h2>
        <p className="text-sm text-neutral-400 mt-2">P0 placeholder.</p>
      </div>
    </div>
  );
}
