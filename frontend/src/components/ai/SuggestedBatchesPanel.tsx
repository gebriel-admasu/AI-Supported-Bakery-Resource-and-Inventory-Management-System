import { useEffect, useState } from 'react';
import { Brain, RefreshCw, Sparkles } from 'lucide-react';
import { aiApi } from '../../api/ai';
import type { OptimalBatchItem, OptimalBatchResponse } from '../../types';

interface SuggestedBatchesPanelProps {
  storeId?: string;
  days?: number;
  className?: string;
}

/**
 * "Suggested batches for the next N days" panel — used on the Production
 * page so bakers see what to produce *before* they plan a batch manually.
 *
 * Failure handling matches the proxy's contract:
 *   - 503 from the AI service ("model not registered") => friendly empty state
 *     pointing at the bootstrap script.
 *   - 504 timeout / 502 bad gateway   => generic retryable error.
 *   - 403                              => silently hides the panel.
 */
export default function SuggestedBatchesPanel({
  storeId,
  days = 1,
  className,
}: SuggestedBatchesPanelProps) {
  const [data, setData] = useState<OptimalBatchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [aiNotReady, setAiNotReady] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [refreshCounter, setRefreshCounter] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        setError('');
        setAiNotReady(false);
        const response = await aiApi.optimalBatches({ days, store_id: storeId });
        if (!cancelled) {
          setData(response);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        const status = (err as { response?: { status?: number } })?.response?.status;
        const detail =
          (err as { response?: { data?: { detail?: string } } })?.response?.data
            ?.detail || '';

        if (status === 403) {
          setForbidden(true);
        } else if (status === 503) {
          setAiNotReady(true);
        } else {
          setError(typeof detail === 'string' && detail ? detail : 'Failed to load AI suggestions.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [storeId, days, refreshCounter]);

  if (forbidden) {
    return null;
  }

  return (
    <div
      className={`bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden ${className ?? ''}`}
    >
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-md bg-purple-100 text-purple-600">
            <Brain size={18} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              AI Suggested Batches
            </h2>
            <p className="text-sm text-gray-500">
              {days === 1
                ? 'Forecasted demand for the next 24 hours.'
                : `Forecasted demand for the next ${days} days.`}
              {data && (
                <>
                  {' '}
                  <span className="text-gray-400">
                    Model v{data.model_version} ·
                    {' '}{new Date(data.generated_at).toLocaleString()}
                  </span>
                </>
              )}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setRefreshCounter((n) => n + 1)}
          disabled={loading}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-primary-700 hover:bg-primary-50 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="p-8 text-center text-gray-400">
          Asking the AI service for suggestions…
        </div>
      ) : aiNotReady ? (
        <div className="p-6 text-sm text-gray-600 flex items-start gap-3 bg-amber-50 border-t border-amber-200">
          <Sparkles className="text-amber-600 flex-shrink-0" size={18} />
          <div>
            <p className="font-medium text-amber-900">AI model not ready yet.</p>
            <p className="mt-1">
              The AI service is running but no Champion model has been registered.
              An admin can train one via the AI Insights page, or run{' '}
              <code className="bg-amber-100 px-1.5 py-0.5 rounded text-xs">
                python ai_service/scripts/bootstrap_champion.py
              </code>
              .
            </p>
          </div>
        </div>
      ) : error ? (
        <div className="p-6 text-sm text-rose-700 bg-rose-50 border-t border-rose-200">
          {error}
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="p-8 text-center text-gray-400">
          No suggestions available for this window.
        </div>
      ) : (
        <BatchTable items={data.items} />
      )}
    </div>
  );
}

function BatchTable({ items }: { items: OptimalBatchItem[] }) {
  // Aggregate per product across all dates in the requested window so the
  // Production page surfaces "total recommended quantity in the next 24 h",
  // not row-per-(product,date) which is harder to act on.
  const aggregated = aggregateByProduct(items);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px]">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Product
            </th>
            <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Forecasted Demand
            </th>
            <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Suggested Batch
            </th>
            <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Confidence
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {aggregated.map((row) => (
            <tr key={row.product_ref} className="hover:bg-gray-50 transition-colors">
              <td className="px-6 py-3 text-sm">
                <div className="font-medium text-gray-900">
                  {row.product_name ?? row.product_ref}
                </div>
                {!row.product_name && (
                  <div className="text-xs text-gray-400">
                    Demo product ref ({row.product_ref})
                  </div>
                )}
              </td>
              <td className="px-6 py-3 text-sm text-right text-gray-700 tabular-nums">
                {row.forecasted_demand.toFixed(1)}
              </td>
              <td className="px-6 py-3 text-sm text-right text-gray-900 tabular-nums font-semibold">
                {row.suggested_batch_qty}
              </td>
              <td className="px-6 py-3 text-sm">
                <ConfidenceBadge value={row.confidence} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface AggregatedRow {
  product_ref: string;
  product_name: string | null | undefined;
  forecasted_demand: number;
  suggested_batch_qty: number;
  confidence: string;
}

function aggregateByProduct(items: OptimalBatchItem[]): AggregatedRow[] {
  const map = new Map<string, AggregatedRow>();
  for (const item of items) {
    const existing = map.get(item.product_ref);
    if (existing) {
      existing.forecasted_demand += item.forecasted_demand;
      existing.suggested_batch_qty += item.suggested_batch_qty;
      if (
        confidenceWeight(item.confidence) < confidenceWeight(existing.confidence)
      ) {
        existing.confidence = item.confidence;
      }
    } else {
      map.set(item.product_ref, {
        product_ref: item.product_ref,
        product_name: item.product_name,
        forecasted_demand: item.forecasted_demand,
        suggested_batch_qty: item.suggested_batch_qty,
        confidence: item.confidence,
      });
    }
  }
  return Array.from(map.values()).sort(
    (a, b) => b.suggested_batch_qty - a.suggested_batch_qty
  );
}

function confidenceWeight(c: string): number {
  if (c === 'high') return 3;
  if (c === 'medium') return 2;
  return 1;
}

function ConfidenceBadge({ value }: { value: string }) {
  const styles =
    value === 'high'
      ? 'bg-emerald-50 text-emerald-700'
      : value === 'medium'
        ? 'bg-amber-50 text-amber-700'
        : 'bg-gray-100 text-gray-600';
  return (
    <span
      className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium capitalize ${styles}`}
    >
      {value}
    </span>
  );
}
