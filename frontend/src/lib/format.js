export const fmt = new Intl.NumberFormat("en");

export function compact(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + "M";
  if (n >= 10_000) return Math.round(n / 1000) + "k";
  return fmt.format(n);
}

export function money(cents) {
  return cents === 0 ? "$0" : `$${(cents / 100).toFixed(0)}/mo`;
}

export function ago(iso) {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export const PROVIDER_LABELS = {
  ollama: "Ollama (local)",
  anthropic: "Claude",
  openai: "OpenAI",
  deepseek: "DeepSeek",
};

export const providerLabel = (name) => PROVIDER_LABELS[name] ?? name;
