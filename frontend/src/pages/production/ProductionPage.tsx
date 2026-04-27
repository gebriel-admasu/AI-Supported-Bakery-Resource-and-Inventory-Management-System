import { useState, useEffect, type FormEvent } from 'react';
import {
  productionApi,
  type BatchDetail,
  type CreateBatchPayload,
  type UpdateBatchPayload,
} from '../../api/production';
import { type RecipeDetail, recipesApi } from '../../api/recipes';
import { type ProductDetail, productsApi } from '../../api/products';
import { Plus, Play, CheckCircle2, XCircle, Factory, X } from 'lucide-react';

const STATUS_OPTIONS = ['all', 'planned', 'in_progress', 'completed', 'cancelled'] as const;

const STATUS_STYLES: Record<string, string> = {
  planned: 'bg-blue-50 text-blue-700',
  in_progress: 'bg-amber-50 text-amber-700',
  completed: 'bg-green-50 text-green-700',
  cancelled: 'bg-red-50 text-red-700',
};

const STATUS_LABELS: Record<string, string> = {
  planned: 'Planned',
  in_progress: 'In Progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

export default function ProductionPage() {
  const [batches, setBatches] = useState<BatchDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [completeTarget, setCompleteTarget] = useState<BatchDetail | null>(null);

  async function fetchBatches() {
    try {
      setLoading(true);
      setError('');
      const params = statusFilter !== 'all' ? { status: statusFilter } : undefined;
      const data = await productionApi.listBatches(params);
      setBatches(data);
    } catch {
      setError('Failed to load production batches');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchBatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const handleStartBatch = async (batch: BatchDetail) => {
    try {
      setError('');
      await productionApi.updateBatch(batch.id, { status: 'in_progress' });
      await fetchBatches();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to start batch';
      setError(typeof msg === 'string' ? msg : 'Failed to start batch');
    }
  };

  const handleCancelBatch = async (batch: BatchDetail) => {
    try {
      setError('');
      await productionApi.updateBatch(batch.id, { status: 'cancelled' });
      await fetchBatches();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to cancel batch';
      setError(typeof msg === 'string' ? msg : 'Failed to cancel batch');
    }
  };

  const handleSaved = () => {
    setShowCreateModal(false);
    setCompleteTarget(null);
    fetchBatches();
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Production Planning</h1>
          <p className="text-gray-500 mt-1">Plan, track, and complete production batches</p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreateModal(true)}
          className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
        >
          <Plus size={18} />
          Plan Batch
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
          {error}
          <button type="button" onClick={() => setError('')} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      <div className="flex gap-2 mb-4 flex-wrap">
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              statusFilter === s
                ? 'bg-primary-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {s === 'all' ? 'All' : STATUS_LABELS[s] ?? s}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading batches...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Product</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Recipe</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Batch Size</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Yield / Waste</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {batches.map((b) => (
                  <tr key={b.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">{b.product_name ?? '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-700">{b.recipe_name ?? '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-700 tabular-nums">{b.batch_size}</td>
                    <td className="px-6 py-4 text-sm text-gray-700 tabular-nums">
                      {b.actual_yield != null ? b.actual_yield : '—'}
                      {b.waste_qty != null && b.waste_qty > 0 && (
                        <span className="text-red-500 ml-1">/ {b.waste_qty} waste</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600 whitespace-nowrap">{formatDate(b.production_date)}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_STYLES[b.status] ?? 'bg-gray-100 text-gray-600'}`}>
                        {STATUS_LABELS[b.status] ?? b.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {b.status === 'planned' && (
                          <>
                            <button
                              type="button"
                              onClick={() => handleStartBatch(b)}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-amber-600 hover:bg-amber-50 transition-colors"
                              title="Start production (deducts ingredients)"
                            >
                              <Play size={16} />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleCancelBatch(b)}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                              title="Cancel batch"
                            >
                              <XCircle size={16} />
                            </button>
                          </>
                        )}
                        {b.status === 'in_progress' && (
                          <button
                            type="button"
                            onClick={() => setCompleteTarget(b)}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
                            title="Mark complete"
                          >
                            <CheckCircle2 size={16} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {batches.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-gray-400">
                      <div className="flex flex-col items-center gap-2">
                        <Factory className="text-gray-300" size={40} strokeWidth={1.5} />
                        <p>No production batches found. Plan one to get started.</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreateModal && (
        <CreateBatchModal
          onClose={() => setShowCreateModal(false)}
          onSaved={handleSaved}
        />
      )}

      {completeTarget && (
        <CompleteBatchModal
          batch={completeTarget}
          onClose={() => setCompleteTarget(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function CreateBatchModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [recipes, setRecipes] = useState<RecipeDetail[]>([]);
  const [products, setProducts] = useState<ProductDetail[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  const [recipeId, setRecipeId] = useState('');
  const [productId, setProductId] = useState('');
  const [batchSize, setBatchSize] = useState('');
  const [productionDate, setProductionDate] = useState(new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      recipesApi.list({ is_active: true }),
      productsApi.list({ is_active: true }),
    ])
      .then(([r, p]) => {
        setRecipes(r);
        setProducts(p);
        if (r.length > 0) setRecipeId(r[0].id);
        if (p.length > 0) setProductId(p[0].id);
      })
      .catch(() => setError('Failed to load recipes/products'))
      .finally(() => setLoadingData(false));
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    const size = Number(batchSize);
    if (!Number.isInteger(size) || size < 1) {
      setError('Batch size must be a positive integer');
      setSaving(false);
      return;
    }

    try {
      const payload: CreateBatchPayload = {
        recipe_id: recipeId,
        product_id: productId,
        batch_size: size,
        production_date: productionDate,
      };
      await productionApi.createBatch(payload);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to create batch';
      setError(typeof msg === 'string' ? msg : 'Failed to create batch');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Plan New Batch</h2>
          <button type="button" onClick={onClose} className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

          {loadingData ? (
            <p className="text-sm text-gray-400">Loading data...</p>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Recipe</label>
                <select
                  value={recipeId}
                  onChange={(e) => setRecipeId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                >
                  {recipes.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} (v{r.version}, yield {r.yield_qty})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Product</label>
                <select
                  value={productId}
                  onChange={(e) => setProductId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.sku})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Batch Size (multiplier)</label>
                  <input
                    type="number"
                    value={batchSize}
                    onChange={(e) => setBatchSize(e.target.value)}
                    required
                    min={1}
                    step={1}
                    placeholder="e.g. 5"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Production Date</label>
                  <input
                    type="date"
                    value={productionDate}
                    onChange={(e) => setProductionDate(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  />
                </div>
              </div>
            </>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || loadingData}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving...' : 'Plan Batch'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CompleteBatchModal({
  batch,
  onClose,
  onSaved,
}: {
  batch: BatchDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [actualYield, setActualYield] = useState('');
  const [expectedOutput, setExpectedOutput] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    recipesApi
      .getById(batch.recipe_id)
      .then((recipe) => {
        setExpectedOutput(recipe.yield_qty * batch.batch_size);
      })
      .catch(() => {});
  }, [batch.recipe_id, batch.batch_size]);

  const yieldNum = Number(actualYield);
  const wasteNum =
    expectedOutput != null && Number.isFinite(yieldNum) && yieldNum >= 0
      ? Math.max(0, expectedOutput - yieldNum)
      : 0;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    if (!Number.isInteger(yieldNum) || yieldNum < 0) {
      setError('Actual yield must be a non-negative integer');
      setSaving(false);
      return;
    }

    try {
      const payload: UpdateBatchPayload = {
        status: 'completed',
        actual_yield: yieldNum,
        waste_qty: wasteNum,
      };
      await productionApi.updateBatch(batch.id, payload);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to complete batch';
      setError(typeof msg === 'string' ? msg : 'Failed to complete batch');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Complete Batch</h2>
          <button type="button" onClick={onClose} className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

          <div className="text-sm text-gray-600 space-y-1">
            <p>
              Completing <span className="font-medium text-gray-900">{batch.product_name}</span>
              {' '}(batch size: {batch.batch_size})
            </p>
            {expectedOutput != null && (
              <p>
                Expected output: <span className="font-medium text-gray-900 tabular-nums">{expectedOutput}</span> units
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Actual Yield</label>
              <input
                type="number"
                value={actualYield}
                onChange={(e) => setActualYield(e.target.value)}
                required
                min={0}
                step={1}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Waste (auto-calculated)</label>
              <div className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-700 tabular-nums">
                {actualYield ? wasteNum : '—'}
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving...' : 'Mark Complete'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
