import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Boxes,
  Brain,
  ChefHat,
  Clock,
  DollarSign,
  PackageCheck,
  ShoppingBag,
  TrendingUp,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { aiApi } from '../../api/ai';
import { reportsApi, type DashboardResponse } from '../../api/reports';
import ChartCard from '../../components/reports/ChartCard';
import KpiTile from '../../components/reports/KpiTile';
import LineTrendChart from '../../components/reports/LineTrendChart';
import MiniSparkline from '../../components/reports/MiniSparkline';

function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `ETB ${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function number(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString();
}

function formatDateLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function ActivityIcon({ kind }: { kind: string }) {
  if (kind === 'sale') return <ShoppingBag className="w-4 h-4 text-emerald-600" />;
  if (kind === 'production') return <ChefHat className="w-4 h-4 text-purple-600" />;
  if (kind === 'purchase_order') return <PackageCheck className="w-4 h-4 text-blue-600" />;
  return <AlertTriangle className="w-4 h-4 text-amber-600" />;
}

export default function DashboardPage() {
  const { user, role } = useAuth();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [aiMae, setAiMae] = useState<number | null>(null);

  // Only admins/owners/production_managers can hit the /ai/* endpoints
  // (matches the backend RBAC matrix). Skip the AI fetch entirely for
  // other roles so we don't surface a confusing 403 in the console.
  const canViewAi =
    role === 'admin' || role === 'owner' || role === 'production_manager';

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        setError('');
        const response = await reportsApi.getDashboard();
        if (!cancelled) setData(response);
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'Failed to load dashboard';
        if (!cancelled) setError(message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!canViewAi) {
      setAiMae(null);
      return;
    }
    let cancelled = false;
    aiApi
      .modelPerformance({ window_days: 7 })
      .then((perf) => {
        if (!cancelled) setAiMae(perf.overall_mae);
      })
      .catch(() => {
        // Silently swallow: AI not ready / no champion / network — the tile
        // simply doesn't render. Errors here must not break the dashboard.
        if (!cancelled) setAiMae(null);
      });
    return () => {
      cancelled = true;
    };
  }, [canViewAi]);

  const sparklineRevenue = useMemo(
    () =>
      (data?.revenue_sparkline ?? []).map((p) => ({
        date: p.date,
        value: p.value,
      })),
    [data?.revenue_sparkline]
  );

  const sparklineBatches = useMemo(
    () =>
      (data?.batches_sparkline ?? []).map((p) => ({
        date: p.date,
        value: p.value,
      })),
    [data?.batches_sparkline]
  );

  const revenueTrendData = useMemo(
    () =>
      sparklineRevenue.map((p) => ({
        date: p.date,
        revenue: p.value,
      })),
    [sparklineRevenue]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-gray-500">Loading dashboard…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-lg p-4">
        {error}
      </div>
    );
  }

  if (!data) return null;

  const showFinancial = data.revenue_today !== null;
  const showOps = data.production_batches_today !== null;
  const showProfit = data.gross_profit_week !== null;

  const scopeLabel = data.scoped_store_name
    ? `Scoped to ${data.scoped_store_name}`
    : 'All stores';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome back, {user?.full_name}
        </h1>
        <p className="text-gray-500 mt-1 text-sm">
          {scopeLabel} — role: <span className="font-medium">{role}</span>
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {showFinancial && (
          <>
            <KpiTile
              label="Revenue Today"
              value={money(data.revenue_today)}
              hint={`${number(data.units_sold_today)} units sold`}
              icon={<DollarSign className="w-5 h-5" />}
              accent="success"
            />
            <KpiTile
              label="Revenue (7d)"
              value={money(data.revenue_week)}
              icon={<TrendingUp className="w-5 h-5" />}
              accent="info"
            />
            <KpiTile
              label="Revenue (30d)"
              value={money(data.revenue_month)}
              icon={<TrendingUp className="w-5 h-5" />}
            />
          </>
        )}
        {showProfit && (
          <KpiTile
            label="Gross Profit (7d)"
            value={money(data.gross_profit_week)}
            icon={<DollarSign className="w-5 h-5" />}
            accent="success"
          />
        )}
        {showOps && (
          <>
            <KpiTile
              label="Batches Today"
              value={number(data.production_batches_today)}
              icon={<ChefHat className="w-5 h-5" />}
              accent="info"
            />
            <KpiTile
              label="Active Stock Alerts"
              value={number(data.active_stock_alerts)}
              icon={<AlertTriangle className="w-5 h-5" />}
              accent={(data.active_stock_alerts ?? 0) > 0 ? 'warning' : 'default'}
            />
            <KpiTile
              label="Expiring (≤7d)"
              value={number(data.expiring_ingredients)}
              icon={<Clock className="w-5 h-5" />}
              accent={(data.expiring_ingredients ?? 0) > 0 ? 'warning' : 'default'}
            />
            <KpiTile
              label="Open POs"
              value={number(data.pending_purchase_orders)}
              icon={<Boxes className="w-5 h-5" />}
            />
          </>
        )}
        {canViewAi && aiMae !== null && (
          <KpiTile
            label="Forecast MAE (7d)"
            value={aiMae.toFixed(2)}
            hint="Lower is better — see AI Insights"
            icon={<Brain className="w-5 h-5" />}
            accent="info"
          />
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {showFinancial && (
          <div className="lg:col-span-2">
            <ChartCard
              title="Revenue — last 7 days"
              subtitle="Daily sales totals"
            >
              <LineTrendChart
                data={revenueTrendData}
                xKey="date"
                xTickFormatter={formatDateLabel}
                yTickFormatter={(v) => `ETB ${Math.round(v).toLocaleString()}`}
                series={[
                  {
                    dataKey: 'revenue',
                    label: 'Revenue',
                    color: '#16a34a',
                    valueFormatter: money,
                  },
                ]}
              />
            </ChartCard>
          </div>
        )}

        {showOps && (
          <ChartCard
            title="Batches — last 7 days"
            subtitle="Active production volume"
          >
            <MiniSparkline
              data={sparklineBatches}
              color="#9333ea"
              height={120}
              valueFormatter={(v) => `${Math.round(v)} batches`}
            />
            <div className="text-xs text-gray-500 mt-2">
              Cancelled batches excluded.
            </div>
          </ChartCard>
        )}

        {!showFinancial && showOps && (
          <ChartCard
            title="Operational focus"
            subtitle="Inventory + production lens"
            className="lg:col-span-2"
          >
            <div className="text-sm text-gray-600">
              You are a Production Manager. Revenue figures are hidden by role —
              head to <span className="font-medium">Production</span> or{' '}
              <span className="font-medium">Inventory</span> for operational
              detail.
            </div>
          </ChartCard>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard
          title="Top product today"
          subtitle="Most units sold so far"
          className="lg:col-span-1"
        >
          {data.top_product_today ? (
            <div>
              <p className="text-xl font-semibold text-gray-900">
                {data.top_product_today.product_name}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {number(data.top_product_today.units_sold)} units sold
              </p>
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">
              No sales recorded yet today.
            </p>
          )}
        </ChartCard>

        <ChartCard
          title="Recent activity"
          subtitle="Latest events across the system"
          className="lg:col-span-2"
        >
          {data.recent_activity.length === 0 ? (
            <p className="text-sm text-gray-400 italic">
              Nothing happened yet.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {data.recent_activity.map((item, idx) => (
                <li
                  key={idx}
                  className="py-2 flex items-start gap-3"
                >
                  <span className="mt-0.5">
                    <ActivityIcon kind={item.kind} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-800 truncate">
                      {item.summary}
                    </p>
                    <p className="text-xs text-gray-500">
                      {formatDateLabel(item.occurred_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
