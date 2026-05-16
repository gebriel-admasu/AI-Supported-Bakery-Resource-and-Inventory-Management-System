/** Shared utilities for the Phase 10 report tabs. */

export function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function defaultRange(days = 30): { date_from: string; date_to: string } {
  const today = new Date();
  const start = new Date(today.getTime() - (days - 1) * 86_400_000);
  return { date_from: toIsoDate(start), date_to: toIsoDate(today) };
}

export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `ETB ${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function compactMoney(value: number): string {
  return `ETB ${Math.round(value).toLocaleString()}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—';
  return `${Number(value).toFixed(digits)}%`;
}

export function formatDateLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
