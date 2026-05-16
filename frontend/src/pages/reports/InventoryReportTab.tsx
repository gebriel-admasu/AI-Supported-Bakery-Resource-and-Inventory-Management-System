import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import {
  reportsApi,
  type IngredientConsumptionResponse,
} from '../../api/reports';
import { ingredientsApi } from '../../api/ingredients';
import type { Ingredient } from '../../types';
import ChartCard from '../../components/reports/ChartCard';
import BarBreakdownChart from '../../components/reports/BarBreakdownChart';
import KpiTile from '../../components/reports/KpiTile';
import { exportCsv } from '../../utils/csvExport';
import { compactMoney, defaultRange, money } from './reportHelpers';

export default function InventoryReportTab() {
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [filters, setFilters] = useState(() => ({
    ...defaultRange(30),
    ingredient_id: 'all',
  }));
  const [data, setData] = useState<IngredientConsumptionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const buildParams = useMemo(
    () => () => ({
      date_from: filters.date_from,
      date_to: filters.date_to,
      ingredient_id:
        filters.ingredient_id === 'all' ? undefined : filters.ingredient_id,
    }),
    [filters.date_from, filters.date_to, filters.ingredient_id]
  );

  const load = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await reportsApi.getIngredientConsumption(buildParams());
      setData(response);
    } catch {
      setError('Failed to load ingredient consumption');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void ingredientsApi
      .list({ is_active: true })
      .then(setIngredients)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.date_from, filters.date_to, filters.ingredient_id]);

  const top10 = useMemo(
    () =>
      (data?.items ?? []).slice(0, 10).map((i) => ({
        name: i.ingredient_name,
        cost: i.total_cost,
      })),
    [data?.items]
  );

  const exportCsvFile = () => {
    if (!data) return;
    exportCsv('ingredient-consumption', data.items, [
      { header: 'Ingredient', accessor: (r) => r.ingredient_name },
      { header: 'Unit', accessor: (r) => r.unit },
      { header: 'Total Qty Consumed', accessor: (r) => r.total_qty_consumed.toFixed(3) },
      { header: 'Total Cost', accessor: (r) => r.total_cost.toFixed(2) },
      { header: 'Batch Count', accessor: (r) => r.batch_count },
    ]);
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
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
            value={filters.ingredient_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, ingredient_id: e.target.value }))
            }
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="all">All Ingredients</option>
            {ingredients.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
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
        <p className="text-xs text-gray-500 mt-2">
          Calculated from completed production batches × recipe ingredient lines,
          scaled by actual yield.
        </p>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiTile
          label="Total Cost Consumed"
          value={money(data?.total_cost)}
          accent="info"
        />
        <KpiTile
          label="Unique Ingredients"
          value={(data?.items.length ?? 0).toString()}
        />
        <KpiTile
          label="Largest Line"
          value={data?.items[0]?.ingredient_name ?? '—'}
          hint={
            data?.items[0]
              ? `${money(data.items[0].total_cost)} across ${data.items[0].batch_count} batch(es)`
              : 'No completed batches in range'
          }
        />
      </div>

      <ChartCard
        title="Top consumed ingredients"
        subtitle="Ranked by cost (top 10)"
      >
        <BarBreakdownChart
          data={top10}
          xKey="name"
          yKey="cost"
          label="Cost"
          layout="horizontal"
          height={Math.max(220, top10.length * 32 + 40)}
          yTickFormatter={compactMoney}
          valueFormatter={money}
        />
      </ChartCard>

      <ChartCard
        title="Full breakdown"
        subtitle="Every ingredient consumed in the date range"
        actions={
          <button
            type="button"
            disabled={!data?.items.length}
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
                <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Ingredient</th>
                <th className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase">Unit</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Qty Consumed</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Cost</th>
                <th className="px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase">Batches</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(data?.items ?? []).map((item) => (
                <tr key={item.ingredient_id}>
                  <td className="px-3 py-2 font-medium text-gray-900">{item.ingredient_name}</td>
                  <td className="px-3 py-2 text-gray-500">{item.unit}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {item.total_qty_consumed.toFixed(3)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(item.total_cost)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{item.batch_count}</td>
                </tr>
              ))}
              {!data?.items.length && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-gray-400">
                    No ingredient consumption in the selected range.
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
