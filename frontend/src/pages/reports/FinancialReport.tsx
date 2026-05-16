import { useEffect, useState } from 'react';
import {
  financeApi,
  type FinanceSummary,
  type PnlTrendPoint,
  type ProductMarginItem,
} from '../../api/finance';
import { productsApi, type ProductDetail } from '../../api/products';
import { storesApi } from '../../api/stores';
import type { Store } from '../../types';

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function money(value: number): string {
  return `ETB ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function percent(value: number): string {
  return `${Number(value || 0).toFixed(2)}%`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

export default function FinancialReport() {
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<ProductDetail[]>([]);
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [margins, setMargins] = useState<ProductMarginItem[]>([]);
  const [trend, setTrend] = useState<PnlTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const todayIso = toIsoDate(new Date());
  const thirtyDaysAgoIso = toIsoDate(
    new Date(Date.now() - 29 * 24 * 60 * 60 * 1000)
  );
  const [filters, setFilters] = useState({
    date_from: thirtyDaysAgoIso,
    date_to: todayIso,
    store_id: 'all',
    product_id: 'all',
    finalized_only: true,
  });

  const buildParams = () => ({
    date_from: filters.date_from,
    date_to: filters.date_to,
    store_id: filters.store_id === 'all' ? undefined : filters.store_id,
    product_id: filters.product_id === 'all' ? undefined : filters.product_id,
    finalized_only: filters.finalized_only,
  });

  const loadLookups = async () => {
    const [storeData, productData] = await Promise.all([
      storesApi.list({ is_active: true }),
      productsApi.list({ is_active: true }),
    ]);
    setStores(storeData);
    setProducts(productData);
  };

  const loadFinancialData = async () => {
    const params = buildParams();
    const [summaryData, marginsData, trendData] = await Promise.all([
      financeApi.getSummary(params),
      financeApi.getProductMargins({
        date_from: params.date_from,
        date_to: params.date_to,
        store_id: params.store_id,
        product_id: params.product_id,
        finalized_only: params.finalized_only,
        limit: 100,
      }),
      financeApi.getPnlTrend(params),
    ]);

    setSummary(summaryData);
    setMargins(marginsData.items);
    setTrend(trendData.points);
  };

  const bootstrap = async () => {
    try {
      setLoading(true);
      setError('');
      await loadLookups();
      await loadFinancialData();
    } catch {
      setError('Failed to load financial analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyFilters = async () => {
    if (!filters.date_from || !filters.date_to) {
      setError('Date range is required');
      return;
    }
    if (filters.date_from > filters.date_to) {
      setError('date_from cannot be after date_to');
      return;
    }
    try {
      setError('');
      setLoading(true);
      await loadFinancialData();
    } catch {
      setError('Failed to refresh financial analytics');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
          {error}
          <button type="button" onClick={() => setError('')} className="float-right font-bold">&times;</button>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-5">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Filters</h2>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => setFilters((prev) => ({ ...prev, date_from: e.target.value }))}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          />
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => setFilters((prev) => ({ ...prev, date_to: e.target.value }))}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          />
          <select
            value={filters.store_id}
            onChange={(e) => setFilters((prev) => ({ ...prev, store_id: e.target.value }))}
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
            value={filters.product_id}
            onChange={(e) => setFilters((prev) => ({ ...prev, product_id: e.target.value }))}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            <option value="all">All Products</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.sku})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void applyFilters()}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700"
          >
            Apply
          </button>
          <label className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700">
            <input
              type="checkbox"
              checked={filters.finalized_only}
              onChange={(e) => setFilters((prev) => ({ ...prev, finalized_only: e.target.checked }))}
            />
            Finalized Sales Only
          </label>
        </div>
      </div>

      {summary && (summary.missing_cost_rows > 0 || summary.estimated_cost_rows > 0) ? (
        <div className="mb-5 bg-amber-50 border border-amber-200 text-amber-800 text-sm px-4 py-3 rounded-lg">
          {summary.missing_cost_rows} row(s) have missing/zero costs and {summary.estimated_cost_rows} row(s) used estimated
          fallback cost logic. Snapshot-complete historical rows provide the most reliable margin figures.
        </div>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
        <MetricCard label="Revenue" value={summary ? money(summary.total_revenue) : '—'} tone="blue" />
        <MetricCard label="COGS" value={summary ? money(summary.total_cogs) : '—'} tone="purple" />
        <MetricCard label="Gross Profit" value={summary ? money(summary.gross_profit) : '—'} tone="green" />
        <MetricCard label="Gross Margin %" value={summary ? percent(summary.gross_margin_pct) : '—'} tone="indigo" />
        {filters.store_id === 'all' ? (
          <>
            <MetricCard label="Store Wastage Cost" value={summary ? money(summary.store_wastage_cost) : '—'} tone="blue" />
            <MetricCard label="Ingredient Wastage Cost" value={summary ? money(summary.ingredient_wastage_cost) : '—'} tone="indigo" />
            <MetricCard
              label="Product Wastage During Production"
              value={summary ? money(summary.production_product_wastage_cost) : '—'}
              tone="purple"
            />
            <MetricCard label="Total Wastage Cost" value={summary ? money(summary.total_wastage_cost) : '—'} tone="amber" />
          </>
        ) : (
          <MetricCard label="Store Wastage Cost" value={summary ? money(summary.total_wastage_cost) : '—'} tone="amber" />
        )}
        <MetricCard label="Estimated Net Profit" value={summary ? money(summary.estimated_net_profit) : '—'} tone="teal" />
      </div>

      {filters.store_id !== 'all' ? (
        <p className="text-xs text-gray-500 mb-5">
          Store filter is active. Wastage and net profit are calculated for the selected store only.
        </p>
      ) : null}

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-5">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">Product Margin Breakdown</h2>
          <p className="text-sm text-gray-500 mt-1">Per-product contribution using recipe cost as unit COGS baseline</p>
        </div>
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading product margins...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Product</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Units Sold</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Revenue</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">COGS</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Gross Profit</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Margin %</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Avg Price</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Unit COGS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {margins.map((item) => (
                  <tr key={item.product_id} className={item.missing_cost ? 'bg-amber-50/40' : item.estimated_cost ? 'bg-blue-50/40' : ''}>
                    <td className="px-4 py-3 text-sm">
                      <div className="font-medium text-gray-900">{item.product_name}</div>
                      <div className="text-xs text-gray-500">{item.sku}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{item.units_sold}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(item.revenue)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(item.cogs)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(item.gross_profit)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{percent(item.gross_margin_pct)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(item.avg_selling_price)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(item.unit_cogs)}</td>
                  </tr>
                ))}
                {!margins.length && (
                  <tr>
                    <td colSpan={8} className="px-6 py-8 text-center text-gray-400">
                      No product margin data in selected range.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">Daily Profit &amp; Loss Trend</h2>
          <p className="text-sm text-gray-500 mt-1">Revenue, COGS, gross profit, wastage cost, and estimated net profit</p>
        </div>
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading P&amp;L trend...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Date</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Revenue</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">COGS</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Gross Profit</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Wastage Cost</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Estimated Net Profit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {trend.map((point) => (
                  <tr key={point.date}>
                    <td className="px-4 py-3 text-sm text-gray-700">{formatDate(point.date)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(point.revenue)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(point.cogs)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(point.gross_profit)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">{money(point.wastage_cost)}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums font-medium">{money(point.estimated_net_profit)}</td>
                  </tr>
                ))}
                {!trend.length && (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                      No P&amp;L trend data in selected range.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'blue' | 'purple' | 'green' | 'indigo' | 'amber' | 'teal';
}) {
  const tones: Record<typeof tone, string> = {
    blue: 'bg-blue-50 text-blue-800 border-blue-100',
    purple: 'bg-purple-50 text-purple-800 border-purple-100',
    green: 'bg-green-50 text-green-800 border-green-100',
    indigo: 'bg-indigo-50 text-indigo-800 border-indigo-100',
    amber: 'bg-amber-50 text-amber-800 border-amber-100',
    teal: 'bg-teal-50 text-teal-800 border-teal-100',
  };

  return (
    <div className={`rounded-xl border px-4 py-3 ${tones[tone]}`}>
      <p className="text-xs uppercase tracking-wide font-semibold">{label}</p>
      <p className="text-lg font-bold mt-1 tabular-nums">{value}</p>
    </div>
  );
}
