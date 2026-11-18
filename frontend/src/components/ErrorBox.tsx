export function ErrorBox({ error }: { error: string }) {
  return (
    <div className="rounded-md border border-rose-700/50 bg-rose-500/10 px-3 py-2 text-sm text-rose-300 whitespace-pre-wrap">
      {error}
    </div>
  )
}