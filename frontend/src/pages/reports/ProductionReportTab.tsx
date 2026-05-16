import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import {
  reportsApi,
  type ProductionEfficiencyResponse,
} from '../../api/reports';
import ChartCard from '../../components/reports/ChartCard';
import BarBreakdownChart from '../../components/reports/BarBreakdownChart';
import KpiTile from '../../components/reports/KpiTile';
import { exportCsv } from '../../utils/csvExport';
import { defaultRange, pct } from './reportHelpers';

export default function ProductionReportTab() {
  const [filters, setFilters] = useState(() => defaultRange(30));
  const [data, setData] = useState<ProductionEfficiencyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await reportsApi.getProductionEfficiency({
        date_from: filters.date_from,
        date_to: filters.date_to,
      });
      setData(response);
    } catch {
      setError('Failed to load production efficiency');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.date_from, filters.date_to]);

  const recipeChartData = useMemo(
    () =>
      (data?.by_recipe ?? []).slice(0, 10).map((r) => ({
        name: r.recipe_name,
        completed: r.completed_batches,
      })),
    [data?.by_recipe]
  );

  const statusBreakdownData = useMemo(
    () => [
      { name: 'Planned', count: data?.planned_count ?? 0 },
      { name: 'In Progress', count: data?.in_progress_count ?? 0 },
      { name: 'Completed', count: data?.completed_count ?? 0 },
      { name: 'Cancelled', count: data?.cancelled_count ?? 0 },
    ],
    [data]
  );

  const exportCsvFile = () => {
    if (!data) return;
    exportCsv('production-efficiency', data.by_recipe, [
      { header: 'Recipe', accessor: (r) => r.recipe_name },
      { header: 'Planned', accessor: (r) => r.planned_batches },
      { header: 'Completed', accessor: (r) => r.completed_batches },
      { header: 'Cancelled', accessor: (r) => r.cancelled_batches },
      { header: 'Planned Qty', accessor: (r) => r.total_planned_qty },
      { header: 'Actual Qty', accessor: (r) => r.total_actual_qty },
      {
        header: 'Avg Yield Variance %',
        accessor: (r) => r.avg_yield_variance_pct.toFixed(2),
      },
    ]);
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
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

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <KpiTile
          label="Total Batches"
          value={(data?.total_batches ?? 0).toLocaleString()}
        />
        <KpiTile
          label="Completion Rate"
          value={pct(data?.completion_rate)}
          hint="completed / (completed + cancelled)"
          accent={
            (data?.completion_rate ?? 0) >= 80
              ? 'success'
              : (data?.completion_rate ?? 0) >= 50
                ? 'info'
                : 'warning'
          }
        />
        <KpiTile
          label="Avg Yield Variance"
          value={pct(data?.avg_yield_variance_pct, 2)}
          hint="vs. planned batch size (completed only)"
          accent={
            Math.abs(data?.avg_yield_variance_pct ?? 0) <= 5
              ? 'success'
              : 'warning'
          }
        />
        <KpiTile
          label="Currently In Progress"
          value={(data?.in_progress_count ?? 0).toLocaleString()}
          accent="info"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title="Batch status breakdown"
          subtitle="Counts across all recipes in the range"
        >
          <BarBreakdownChart
            data={statusBreakdownData}
            xKey="name"
            yKey="count"
            label="Batches"
            layout="horizontal"
            height={220}
          />
        </ChartCard>

        <ChartCard
          title="Top recipes by completed batches"
          subtitle="Top 10 contributors"
        >
          <BarBreakdownChart
            data={recipeChartData}
            xKey="name"
            yKey="completed"
            label="Completed Batches"
            layout="horizontal"
            height={Math.max(220, recipeChartData.length * 32 + 40)}
          />
        </ChartCard>
      </div>

      <ChartCard
        title="Per-recipe breakdown"
        subtitle="Planned vs actual quantities and yield variance"
        actions={
          <button
            type="button"
            disabled={!data?.by_recipe.length}
            onClick={exportCsvFile}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-left">
                <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Recipe</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Planned</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Completed</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Cancelled</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Planned Qty</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Actual Qty</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Avg Yield Δ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(data?.by_recipe ?? []).map((r) => (
                <tr key={r.recipe_id}>
                  <td className="px-3 py-2 font-medium text-gray-900">{r.recipe_name}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.planned_batches}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.completed_batches}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.cancelled_batches}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.total_planned_qty}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.total_actual_qty}</td>
                  <td
                    className={`px-3 py-2 text-right tabular-nums ${r.avg_yield_variance_pct < 0 ? 'text-rose-600' : 'text-emerald-600'}`}
                  >
                    {pct(r.avg_yield_variance_pct, 2)}
                  </td>
                </tr>
              ))}
              {!data?.by_recipe.length && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-gray-400">
                    No production batches in the selected range.
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
