import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import {
  reportsApi,
  type WastageTrendsResponse,
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

type GroupBy = 'date' | 'reason' | 'source';

export default function WastageReportTab() {
  const [stores, setStores] = useState<Store[]>([]);
  const [filters, setFilters] = useState(() => ({
    ...defaultRange(30),
    store_id: 'all',
    group_by: 'date' as GroupBy,
  }));
  const [data, setData] = useState<WastageTrendsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const buildParams = useMemo(
    () => () => ({
      date_from: filters.date_from,
      date_to: filters.date_to,
      store_id: filters.store_id === 'all' ? undefined : filters.store_id,
      group_by: filters.group_by,
    }),
    [filters.date_from, filters.date_to, filters.store_id, filters.group_by]
  );

  const load = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await reportsApi.getWastageTrends(buildParams());
      setData(response);
    } catch {
      setError('Failed to load wastage report');
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
  }, [filters.date_from, filters.date_to, filters.store_id, filters.group_by]);

  const chartData = useMemo(
    () =>
      (data?.buckets ?? []).map((b) => ({
        key: b.label,
        cost: b.total_cost,
        qty: b.total_qty,
      })),
    [data?.buckets]
  );

  const exportTrendsCsv = () => {
    if (!data) return;
    exportCsv(`wastage-by-${filters.group_by}`, data.buckets, [
      {
        header: filters.group_by === 'date' ? 'Date' : 'Bucket',
        accessor: (r) => r.label,
      },
      { header: 'Total Qty', accessor: (r) => r.total_qty },
      { header: 'Total Cost', accessor: (r) => r.total_cost.toFixed(2) },
      { header: 'Records', accessor: (r) => r.record_count },
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
            value={filters.group_by}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, group_by: e.target.value as GroupBy }))
            }
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="date">Group by Date</option>
            <option value="reason">Group by Reason</option>
            <option value="source">Group by Source</option>
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
          label="Total Wastage Cost"
          value={money(data?.total_cost)}
          accent="warning"
        />
        <KpiTile
          label="Total Wastage Qty"
          value={(data?.total_qty ?? 0).toLocaleString()}
          accent="warning"
        />
        <KpiTile
          label="Buckets"
          value={(data?.buckets.length ?? 0).toString()}
          hint={`grouped by ${filters.group_by}`}
        />
      </div>

      <ChartCard
        title={`Wastage by ${filters.group_by}`}
        subtitle="Cost contribution per bucket"
        actions={
          <button
            type="button"
            disabled={!data?.buckets.length}
            onClick={exportTrendsCsv}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
        }
      >
        {filters.group_by === 'date' ? (
          <LineTrendChart
            data={chartData}
            xKey="key"
            xTickFormatter={formatDateLabel}
            yTickFormatter={compactMoney}
            series={[
              {
                dataKey: 'cost',
                label: 'Wastage Cost',
                color: '#dc2626',
                valueFormatter: money,
              },
            ]}
          />
        ) : (
          <BarBreakdownChart
            data={chartData}
            xKey="key"
            yKey="cost"
            label="Wastage Cost"
            layout="horizontal"
            height={Math.max(220, chartData.length * 40 + 40)}
            yTickFormatter={compactMoney}
            valueFormatter={money}
          />
        )}

        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-left">
                <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">
                  {filters.group_by === 'date' ? 'Date' : 'Bucket'}
                </th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Qty</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Cost</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Records</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(data?.buckets ?? []).map((b) => (
                <tr key={b.key}>
                  <td className="px-3 py-2">
                    {filters.group_by === 'date' ? formatDateLabel(b.key) : b.label}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{b.total_qty}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(b.total_cost)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{b.record_count}</td>
                </tr>
              ))}
              {!data?.buckets.length && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-gray-400">
                    No wastage records in the selected range.
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
