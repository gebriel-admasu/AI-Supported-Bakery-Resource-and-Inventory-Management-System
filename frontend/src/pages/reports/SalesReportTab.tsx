import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import {
  reportsApi,
  type SalesTrendsResponse,
  type TopSellersResponse,
} from '../../api/reports';
import { storesApi } from '../../api/stores';
import type { Store } from '../../types';
import ChartCard from '../../components/reports/ChartCard';
import LineTrendChart from '../../components/reports/LineTrendChart';
import BarBreakdownChart from '../../components/reports/BarBreakdownChart';
import KpiTile from '../../components/reports/KpiTile';
import { exportCsv } from '../../utils/csvExport';
import {
  compactMoney,
  defaultRange,
  formatDateLabel,
  money,
} from './reportHelpers';

interface SalesFilters {
  date_from: string;
  date_to: string;
  store_id: string;
  granularity: 'day' | 'week';
}

export default function SalesReportTab() {
  const [stores, setStores] = useState<Store[]>([]);
  const [filters, setFilters] = useState<SalesFilters>(() => ({
    ...defaultRange(30),
    store_id: 'all',
    granularity: 'day',
  }));
  const [trends, setTrends] = useState<SalesTrendsResponse | null>(null);
  const [topSellers, setTopSellers] = useState<TopSellersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const buildParams = useMemo(
    () => () => ({
      date_from: filters.date_from,
      date_to: filters.date_to,
      store_id: filters.store_id === 'all' ? undefined : filters.store_id,
    }),
    [filters.date_from, filters.date_to, filters.store_id]
  );

  const load = async () => {
    try {
      setLoading(true);
      setError('');
      const params = buildParams();
      const [t, ts] = await Promise.all([
        reportsApi.getSalesTrends({ ...params, granularity: filters.granularity }),
        reportsApi.getTopSellers({ ...params, order_by: 'revenue', limit: 10 }),
      ]);
      setTrends(t);
      setTopSellers(ts);
    } catch {
      setError('Failed to load sales report');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void storesApi
      .list({ is_active: true })
      .then(setStores)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.date_from, filters.date_to, filters.store_id, filters.granularity]);

  const trendChartData = useMemo(
    () =>
      (trends?.points ?? []).map((p) => ({
        date: p.date,
        revenue: p.revenue,
        units: p.units_sold,
      })),
    [trends?.points]
  );

  const topSellerChartData = useMemo(
    () =>
      (topSellers?.items ?? []).map((t) => ({
        name: t.product_name,
        revenue: t.revenue,
      })),
    [topSellers?.items]
  );

  const exportTrendsCsv = () => {
    if (!trends) return;
    exportCsv('sales-trends', trends.points, [
      { header: 'Date', accessor: (r) => r.date },
      { header: 'Units Sold', accessor: (r) => r.units_sold },
      { header: 'Revenue', accessor: (r) => r.revenue.toFixed(2) },
      { header: 'Transactions', accessor: (r) => r.transaction_count },
    ]);
  };

  const exportTopSellersCsv = () => {
    if (!topSellers) return;
    exportCsv('top-sellers', topSellers.items, [
      { header: 'Product', accessor: (r) => r.product_name },
      { header: 'SKU', accessor: (r) => r.sku ?? '' },
      { header: 'Units Sold', accessor: (r) => r.units_sold },
      { header: 'Revenue', accessor: (r) => r.revenue.toFixed(2) },
      { header: 'Avg Unit Price', accessor: (r) => r.avg_unit_price.toFixed(2) },
    ]);
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, date_from: e.target.value }))
            }
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          />
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, date_to: e.target.value }))
            }
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          />
          <select
            value={filters.store_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, store_id: e.target.value }))
            }
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="all">All Stores</option>
            {stores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <select
            value={filters.granularity}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                granularity: e.target.value as 'day' | 'week',
              }))
            }
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
          </select>
          <button
            type="button"
            disabled={loading}
            onClick={() => void load()}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiTile
          label="Total Revenue"
          value={money(trends?.total_revenue)}
          hint={`${filters.date_from} → ${filters.date_to}`}
          accent="success"
        />
        <KpiTile
          label="Total Units Sold"
          value={(trends?.total_units ?? 0).toLocaleString()}
          accent="info"
        />
        <KpiTile
          label="Top Product"
          value={topSellers?.items[0]?.product_name ?? '—'}
          hint={
            topSellers?.items[0]
              ? `${topSellers.items[0].units_sold} units · ${money(topSellers.items[0].revenue)}`
              : 'No sales in range'
          }
        />
      </div>

      <ChartCard
        title="Sales trend"
        subtitle={`Granularity: ${filters.granularity}`}
        actions={
          <button
            type="button"
            disabled={!trends?.points.length}
            onClick={exportTrendsCsv}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
        }
      >
        <LineTrendChart
          data={trendChartData}
          xKey="date"
          xTickFormatter={formatDateLabel}
          yTickFormatter={compactMoney}
          series={[
            {
              dataKey: 'revenue',
              label: 'Revenue',
              color: '#16a34a',
              valueFormatter: money,
            },
            {
              dataKey: 'units',
              label: 'Units Sold',
              color: '#2563eb',
            },
          ]}
        />
      </ChartCard>

      <ChartCard
        title="Top sellers"
        subtitle="Ranked by revenue (top 10)"
        actions={
          <button
            type="button"
            disabled={!topSellers?.items.length}
            onClick={exportTopSellersCsv}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
        }
      >
        <BarBreakdownChart
          data={topSellerChartData}
          xKey="name"
          yKey="revenue"
          label="Revenue"
          layout="horizontal"
          height={Math.max(220, topSellerChartData.length * 32 + 40)}
          yTickFormatter={compactMoney}
          valueFormatter={money}
        />

        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-left">
                <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Product</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">SKU</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Units</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Revenue</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Avg Price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(topSellers?.items ?? []).map((item) => (
                <tr key={item.product_id}>
                  <td className="px-3 py-2">{item.product_name}</td>
                  <td className="px-3 py-2 text-gray-500">{item.sku ?? '—'}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{item.units_sold}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(item.revenue)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(item.avg_unit_price)}</td>
                </tr>
              ))}
              {!topSellers?.items.length && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-gray-400">
                    No sales in the selected range.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </div>
  );
}
