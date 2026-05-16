import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  PlayCircle,
  RefreshCw,
  Sparkles,
  Target,
  TrendingDown,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { aiApi } from '../../api/ai';
import type {
  BacktestResponse,
  ForecastListItem,
  ForecastListResponse,
  ModelPerformanceResponse,
  ModelRegistryListResponse,
  RetrainResponse,
} from '../../types';
import ChartCard from '../../components/reports/ChartCard';
import KpiTile from '../../components/reports/KpiTile';
import LineTrendChart from '../../components/reports/LineTrendChart';
import SuggestedBatchesPanel from '../../components/ai/SuggestedBatchesPanel';

/**
 * AI Insights dashboard — single page surface for the forecasting + MLOps
 * pipeline (Phase 11 + 12). Sections:
 *
 *   1. KPI hero row     — champion version, MAE this week, latest retrain
 *   2. Performance chart — daily MAE for the active champion
 *   3. Recent forecasts  — what the model predicted vs. what actually sold
 *   4. Model registry    — all versions with status + promotion dates
 *   5. MLOps controls    — admin/owner-only Retrain + Backtest buttons
 *
 * Errors are categorised so the UI can degrade gracefully when the AI
 * service is unreachable (503) vs. when the user simply lacks permission
 * for some panels (403 — usually safe to hide).
 */
export default function AiInsightsPage() {
  const { role } = useAuth();
  const canRunMlops = role === 'admin' || role === 'owner';

  const [models, setModels] = useState<ModelRegistryListResponse | null>(null);
  const [performance, setPerformance] = useState<ModelPerformanceResponse | null>(null);
  const [forecasts, setForecasts] = useState<ForecastListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiNotReady, setAiNotReady] = useState(false);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    setAiNotReady(false);
    try {
      // Models is the only "must-succeed" call. If it 503s, we treat the AI
      // service as not-ready and show a single empty state instead of a
      // cascade of failing panels.
      const modelData = await aiApi.listModels();
      setModels(modelData);

      // The remaining calls are best-effort — failures are isolated so e.g.
      // an empty forecast archive doesn't break the performance chart.
      const [perfResult, fcResult] = await Promise.allSettled([
        aiApi.modelPerformance({ window_days: 14 }),
        aiApi.listForecasts({ limit: 25 }),
      ]);
      setPerformance(perfResult.status === 'fulfilled' ? perfResult.value : null);
      setForecasts(fcResult.status === 'fulfilled' ? fcResult.value : null);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '';
      if (status === 503) {
        setAiNotReady(true);
      } else if (status === 403) {
        setError('You do not have permission to view AI insights.');
      } else {
        setError(
          typeof detail === 'string' && detail
            ? detail
            : 'Failed to load AI insights. Is the AI service running on :8001?'
        );
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll, refreshKey]);

  const champion = useMemo(
    () => models?.items.find((m) => m.status === 'champion') ?? null,
    [models]
  );

  // Build chart data ahead of render — Recharts needs `number` types
  const performanceChartData = useMemo(
    () =>
      (performance?.daily ?? []).map((p) => ({
        date: p.bucket_date,
        mae: Number(p.mae.toFixed(2)),
        predictions: p.predictions,
      })),
    [performance]
  );

  if (loading) {
    return (
      <div className="space-y-6">
        <PageHeader role={role ?? null} />
        <div className="flex items-center justify-center py-20">
          <div className="text-gray-500">Loading AI insights…</div>
        </div>
      </div>
    );
  }

  if (aiNotReady) {
    return (
      <div className="space-y-6">
        <PageHeader role={role ?? null} />
        <AiNotReadyPanel
          canBootstrap={canRunMlops}
          onAfterRetrain={() => setRefreshKey((n) => n + 1)}
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader role={role ?? null} />
        <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="flex-shrink-0 mt-0.5" size={18} />
          <div>{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader role={role ?? null} onRefresh={() => setRefreshKey((n) => n + 1)} />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile
          label="Active Champion"
          value={champion ? `v${champion.version}` : '—'}
          hint={
            champion
              ? `${champion.training_rows_used.toLocaleString()} rows · ${champion.training_source ?? 'unknown'}`
              : 'No champion registered'
          }
          icon={<Brain className="w-5 h-5" />}
          accent={champion ? 'success' : 'warning'}
        />
        <KpiTile
          label="Holdout MAE"
          value={champion?.holdout_mae?.toFixed(2) ?? '—'}
          hint="Lower is better"
          icon={<Target className="w-5 h-5" />}
          accent="info"
        />
        <KpiTile
          label="MAE (last 14d)"
          value={
            performance?.overall_mae != null
              ? performance.overall_mae.toFixed(2)
              : '—'
          }
          hint={`${performance?.daily?.length ?? 0} scored days`}
          icon={<TrendingDown className="w-5 h-5" />}
          accent={
            performance?.overall_mae != null && champion?.holdout_mae != null
              ? performance.overall_mae <= champion.holdout_mae * 1.2
                ? 'success'
                : 'warning'
              : 'default'
          }
        />
        <KpiTile
          label="Total Versions"
          value={String(models?.items.length ?? 0)}
          hint={`${models?.items.filter((m) => m.status === 'archived').length ?? 0} archived`}
          icon={<Sparkles className="w-5 h-5" />}
        />
      </div>

      {canRunMlops && (
        <MlopsControls onActionComplete={() => setRefreshKey((n) => n + 1)} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <ChartCard
            title="Forecast Accuracy"
            subtitle={`Daily MAE for the champion model — last ${performance?.window_days ?? 14} days`}
          >
            <LineTrendChart
              data={performanceChartData}
              xKey="date"
              xTickFormatter={formatShortDate}
              series={[
                {
                  dataKey: 'mae',
                  label: 'MAE',
                  color: '#dc2626',
                  valueFormatter: (v) => v.toFixed(2),
                },
              ]}
            />
          </ChartCard>
        </div>

        <ChartCard
          title="Scoring Volume"
          subtitle="Predictions scored per day"
        >
          {performanceChartData.length === 0 ? (
            <div className="flex items-center justify-center h-[280px] text-sm text-gray-400 italic">
              No scored predictions yet. Run a backtest to populate.
            </div>
          ) : (
            <ul className="text-sm space-y-2 max-h-[260px] overflow-y-auto">
              {performanceChartData
                .slice()
                .reverse()
                .map((p) => (
                  <li
                    key={p.date}
                    className="flex items-center justify-between gap-3 py-1.5 border-b border-gray-100 last:border-0"
                  >
                    <span className="text-gray-600">{formatShortDate(p.date)}</span>
                    <span className="text-gray-500 tabular-nums">
                      {p.predictions} preds · MAE {p.mae.toFixed(2)}
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </ChartCard>
      </div>

      <SuggestedBatchesPanel days={1} />

      <ChartCard
        title="Recent Forecasts"
        subtitle="Last 25 predictions, newest first. Empty 'Actual' means the day hasn't been backtested yet."
      >
        <RecentForecastsTable items={forecasts?.items ?? []} />
      </ChartCard>

      <ChartCard
        title="Model Registry"
        subtitle="All trained versions with their lifecycle status"
      >
        <ModelRegistryTable items={models?.items ?? []} />
      </ChartCard>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PageHeader({
  role,
  onRefresh,
}: {
  role: string | null;
  onRefresh?: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Insights</h1>
        <p className="text-gray-500 text-sm mt-1">
          Demand forecasting, model performance, and MLOps automation
          {role && (
            <>
              {' '}— viewing as <span className="font-medium">{role}</span>
            </>
          )}
        </p>
      </div>
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          className="flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-lg text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      )}
    </div>
  );
}

function AiNotReadyPanel({
  canBootstrap,
  onAfterRetrain,
}: {
  canBootstrap: boolean;
  onAfterRetrain: () => void;
}) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 flex items-start gap-4">
      <div className="p-2 rounded-lg bg-amber-100 text-amber-700 flex-shrink-0">
        <Sparkles size={20} />
      </div>
      <div className="flex-1">
        <h2 className="text-lg font-semibold text-amber-900">
          The AI is still warming up.
        </h2>
        <p className="text-sm text-amber-800 mt-1">
          No Champion model has been registered yet, so demand forecasting is offline.
          This is normal for a fresh deployment — bootstrap the first model below
          or run the CLI helper:
        </p>
        <pre className="mt-3 bg-amber-100 border border-amber-200 rounded px-3 py-2 text-xs text-amber-900 overflow-x-auto">
          python ai_service/scripts/bootstrap_champion.py
        </pre>
        {canBootstrap && (
          <div className="mt-4">
            <MlopsControls
              onActionComplete={onAfterRetrain}
              compact
              defaultSource="kaggle"
            />
          </div>
        )}
      </div>
    </div>
  );
}

function MlopsControls({
  onActionComplete,
  compact = false,
  defaultSource = 'live',
}: {
  onActionComplete: () => void;
  compact?: boolean;
  defaultSource?: 'kaggle' | 'synthetic' | 'live';
}) {
  const [retraining, setRetraining] = useState(false);
  const [backtesting, setBacktesting] = useState(false);
  const [source, setSource] = useState<'kaggle' | 'synthetic' | 'live'>(defaultSource);
  const [lookbackDays, setLookbackDays] = useState(7);
  const [lastResult, setLastResult] = useState<RetrainResponse | null>(null);
  const [lastBacktest, setLastBacktest] = useState<BacktestResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  const handleRetrain = async () => {
    setRetraining(true);
    setErrorMsg('');
    try {
      const result = await aiApi.retrain({ source, reason: 'manual_ui' });
      setLastResult(result);
      onActionComplete();
    } catch (err: unknown) {
      setErrorMsg(extractDetail(err, 'Retrain failed.'));
    } finally {
      setRetraining(false);
    }
  };

  const handleBacktest = async () => {
    setBacktesting(true);
    setErrorMsg('');
    try {
      const result = await aiApi.backtest({ lookback_days: lookbackDays });
      setLastBacktest(result);
      onActionComplete();
    } catch (err: unknown) {
      setErrorMsg(extractDetail(err, 'Backtest failed.'));
    } finally {
      setBacktesting(false);
    }
  };

  return (
    <div
      className={`bg-white rounded-xl border border-gray-200 ${compact ? 'p-4' : 'p-5'}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <PlayCircle className="text-primary-600" size={18} />
        <h3 className="font-semibold text-gray-900">MLOps Controls</h3>
        <span className="text-xs text-gray-400">(admin / owner only)</span>
      </div>

      {errorMsg && (
        <div className="mb-3 text-sm text-rose-700 bg-rose-50 border border-rose-200 px-3 py-2 rounded">
          {errorMsg}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border border-gray-100 rounded-lg p-3">
          <div className="text-sm font-medium text-gray-700 mb-2">
            Train a new model
          </div>
          <div className="flex items-center gap-2 mb-2">
            <label className="text-xs text-gray-600">Data source:</label>
            <select
              value={source}
              onChange={(e) =>
                setSource(e.target.value as 'kaggle' | 'synthetic' | 'live')
              }
              disabled={retraining}
              className="text-sm border border-gray-300 rounded px-2 py-1 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none disabled:opacity-50"
            >
              <option value="live">live (real bakery sales)</option>
              <option value="kaggle">kaggle (warm-start dataset)</option>
              <option value="synthetic">synthetic (generated)</option>
            </select>
          </div>
          <button
            type="button"
            onClick={handleRetrain}
            disabled={retraining}
            className="w-full sm:w-auto flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {retraining ? (
              <RefreshCw className="animate-spin" size={14} />
            ) : (
              <Brain size={14} />
            )}
            {retraining ? 'Training…' : 'Trigger Retrain'}
          </button>
          {lastResult && (
            <div className="mt-3 text-xs bg-gray-50 border border-gray-200 rounded p-2">
              <div className="font-medium text-gray-800 flex items-center gap-1">
                {lastResult.promoted ? (
                  <CheckCircle2 className="text-emerald-600" size={14} />
                ) : (
                  <AlertTriangle className="text-amber-600" size={14} />
                )}
                {lastResult.promoted
                  ? `v${lastResult.candidate_version} promoted to champion`
                  : `v${lastResult.candidate_version} ${lastResult.status}`}
              </div>
              <p className="text-gray-600 mt-1">{lastResult.message}</p>
              <p className="text-gray-500 mt-1">
                Holdout MAE: {lastResult.holdout_mae.toFixed(2)} ·{' '}
                {lastResult.training_rows.toLocaleString()} rows ·{' '}
                {lastResult.training_source}
              </p>
            </div>
          )}
        </div>

        <div className="border border-gray-100 rounded-lg p-3">
          <div className="text-sm font-medium text-gray-700 mb-2">
            Backtest recent forecasts
          </div>
          <div className="flex items-center gap-2 mb-2">
            <label className="text-xs text-gray-600">Lookback days:</label>
            <input
              type="number"
              min={1}
              max={30}
              value={lookbackDays}
              onChange={(e) => setLookbackDays(Number(e.target.value))}
              disabled={backtesting}
              className="w-20 text-sm border border-gray-300 rounded px-2 py-1 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none disabled:opacity-50"
            />
          </div>
          <button
            type="button"
            onClick={handleBacktest}
            disabled={backtesting}
            className="w-full sm:w-auto flex items-center justify-center gap-2 bg-gray-100 text-gray-800 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            {backtesting ? (
              <RefreshCw className="animate-spin" size={14} />
            ) : (
              <Target size={14} />
            )}
            {backtesting ? 'Scoring…' : 'Run Backtest'}
          </button>
          {lastBacktest && (
            <div className="mt-3 text-xs bg-gray-50 border border-gray-200 rounded p-2 text-gray-600">
              Scored {lastBacktest.rows_scored} forecasts (
              {lastBacktest.forecasts_skipped_no_actual} still pending real sales)
              {lastBacktest.mean_abs_error != null && (
                <> · MAE {lastBacktest.mean_abs_error.toFixed(2)}</>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RecentForecastsTable({ items }: { items: ForecastListItem[] }) {
  if (items.length === 0) {
    return (
      <div className="text-sm text-gray-400 italic py-6 text-center">
        No archived forecasts yet. Generate one from the Production page or via{' '}
        <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">POST /api/v1/ai/predict</code>.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px]">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <Th>Target Date</Th>
            <Th>Product</Th>
            <Th>Store</Th>
            <Th align="right">Predicted</Th>
            <Th align="right">Actual</Th>
            <Th align="right">Abs Err</Th>
            <Th align="right">v</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {items.map((row) => (
            <tr key={row.id} className="hover:bg-gray-50">
              <Td>{formatShortDate(row.target_date)}</Td>
              <Td>{row.product_name ?? row.product_ref}</Td>
              <Td>{row.store_name ?? row.store_ref}</Td>
              <Td align="right" mono>
                {row.predicted_qty.toFixed(1)}
              </Td>
              <Td align="right" mono>
                {row.actual_qty != null ? row.actual_qty.toFixed(1) : '—'}
              </Td>
              <Td align="right" mono>
                {row.abs_error != null ? row.abs_error.toFixed(2) : '—'}
              </Td>
              <Td align="right" mono>
                v{row.model_version}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelRegistryTable({
  items,
}: {
  items: ModelRegistryListResponse['items'];
}) {
  if (items.length === 0) {
    return (
      <div className="text-sm text-gray-400 italic py-6 text-center">
        No model versions registered.
      </div>
    );
  }
  const sorted = [...items].sort((a, b) => b.version - a.version);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px]">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <Th>Version</Th>
            <Th>Status</Th>
            <Th align="right">Holdout MAE</Th>
            <Th align="right">Training rows</Th>
            <Th>Source</Th>
            <Th>Trained</Th>
            <Th>Promoted</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((m) => (
            <tr key={m.id} className="hover:bg-gray-50">
              <Td>
                <span className="font-mono font-medium">v{m.version}</span>
              </Td>
              <Td>
                <StatusBadge status={m.status} />
              </Td>
              <Td align="right" mono>
                {m.holdout_mae != null ? m.holdout_mae.toFixed(2) : '—'}
              </Td>
              <Td align="right" mono>
                {m.training_rows_used.toLocaleString()}
              </Td>
              <Td>{m.training_source ?? '—'}</Td>
              <Td>{formatShortDate(m.trained_at)}</Td>
              <Td>{m.promoted_at ? formatShortDate(m.promoted_at) : '—'}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    champion: 'bg-emerald-50 text-emerald-700',
    candidate: 'bg-blue-50 text-blue-700',
    archived: 'bg-gray-100 text-gray-600',
    rejected: 'bg-rose-50 text-rose-700',
  };
  return (
    <span
      className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium capitalize ${styles[status] ?? 'bg-gray-100 text-gray-600'}`}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Tiny shared cells
// ---------------------------------------------------------------------------

function Th({
  children,
  align = 'left',
}: {
  children: React.ReactNode;
  align?: 'left' | 'right';
}) {
  return (
    <th
      className={`px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider ${
        align === 'right' ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = 'left',
  mono = false,
}: {
  children: React.ReactNode;
  align?: 'left' | 'right';
  mono?: boolean;
}) {
  return (
    <td
      className={`px-4 py-2.5 text-sm text-gray-700 ${
        align === 'right' ? 'text-right' : 'text-left'
      } ${mono ? 'tabular-nums' : ''}`}
    >
      {children}
    </td>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function extractDetail(err: unknown, fallback: string): string {
  const detail =
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
