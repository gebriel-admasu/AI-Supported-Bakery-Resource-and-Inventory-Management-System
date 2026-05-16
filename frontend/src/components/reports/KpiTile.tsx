import type { ReactNode } from 'react';

interface KpiTileProps {
  label: string;
  value: ReactNode;
  hint?: string;
  trend?: {
    direction: 'up' | 'down' | 'flat';
    label: string;
  };
  icon?: ReactNode;
  accent?: 'default' | 'success' | 'warning' | 'danger' | 'info';
}

const ACCENT_BG: Record<NonNullable<KpiTileProps['accent']>, string> = {
  default: 'bg-white',
  success: 'bg-emerald-50',
  warning: 'bg-amber-50',
  danger: 'bg-rose-50',
  info: 'bg-sky-50',
};

const ACCENT_ICON: Record<NonNullable<KpiTileProps['accent']>, string> = {
  default: 'text-gray-500 bg-gray-100',
  success: 'text-emerald-600 bg-emerald-100',
  warning: 'text-amber-600 bg-amber-100',
  danger: 'text-rose-600 bg-rose-100',
  info: 'text-sky-600 bg-sky-100',
};

export default function KpiTile({
  label,
  value,
  hint,
  trend,
  icon,
  accent = 'default',
}: KpiTileProps) {
  const trendColor =
    trend?.direction === 'up'
      ? 'text-emerald-600'
      : trend?.direction === 'down'
        ? 'text-rose-600'
        : 'text-gray-500';
  const trendSymbol =
    trend?.direction === 'up' ? '↑' : trend?.direction === 'down' ? '↓' : '→';

  return (
    <div
      className={`rounded-lg shadow-sm border border-gray-200 p-4 ${ACCENT_BG[accent]}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-gray-500 font-medium">
            {label}
          </p>
          <p className="text-2xl font-semibold text-gray-900 mt-1 truncate">
            {value}
          </p>
          {hint && <p className="text-xs text-gray-500 mt-1">{hint}</p>}
          {trend && (
            <p className={`text-xs font-medium mt-1 ${trendColor}`}>
              {trendSymbol} {trend.label}
            </p>
          )}
        </div>
        {icon && (
          <div className={`p-2 rounded-md flex-shrink-0 ${ACCENT_ICON[accent]}`}>
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
