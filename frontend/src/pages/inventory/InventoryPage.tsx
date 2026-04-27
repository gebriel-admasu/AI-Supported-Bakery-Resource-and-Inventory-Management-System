import { useState, useEffect, useMemo, type FormEvent } from 'react';
import type { Ingredient } from '../../types';
import { ingredientsApi } from '../../api/ingredients';
import {
  inventoryApi,
  type InventoryStock,
  type StockAlert,
  type AddStockPayload,
  type UpdateStockPayload,
} from '../../api/inventory';
import { Plus, Pencil, AlertTriangle, Package, ArrowUpDown, X } from 'lucide-react';

type SortKey = 'name' | 'quantity' | 'updated';

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

function stockStatus(
  quantity: number | string,
  minThreshold: number | string | null
): { label: string; className: string } {
  if (minThreshold == null) {
    return { label: 'No threshold', className: 'bg-gray-100 text-gray-600' };
  }
  if (Number(quantity) >= Number(minThreshold)) {
    return { label: 'OK', className: 'bg-green-50 text-green-700' };
  }
  return { label: 'Low Stock', className: 'bg-amber-50 text-amber-800' };
}

export default function InventoryPage() {
  const [stocks, setStocks] = useState<InventoryStock[]>([]);
  const [alerts, setAlerts] = useState<StockAlert[]>([]);
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortAsc, setSortAsc] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingStock, setEditingStock] = useState<InventoryStock | null>(null);

  const ingredientUnitById = useMemo(() => {
    const m = new Map<string, string>();
    for (const ing of ingredients) {
      m.set(ing.id, ing.unit);
    }
    return m;
  }, [ingredients]);

  const ingredientStocks = useMemo(
    () => stocks.filter((s) => s.ingredient_id != null),
    [stocks]
  );

  const sortedStocks = useMemo(() => {
    const rows = [...ingredientStocks];
    rows.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'name') {
        const na = (a.ingredient_name ?? '').toLowerCase();
        const nb = (b.ingredient_name ?? '').toLowerCase();
        cmp = na.localeCompare(nb);
      } else if (sortKey === 'quantity') {
        cmp = a.quantity - b.quantity;
      } else {
        cmp = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
      }
      return sortAsc ? cmp : -cmp;
    });
    return rows;
  }, [ingredientStocks, sortKey, sortAsc]);

  async function loadAll() {
    try {
      setLoading(true);
      setError('');
      const [stockData, alertData, ingData] = await Promise.all([
        inventoryApi.listStocks(),
        inventoryApi.listAlerts(),
        ingredientsApi.list({ is_active: true }),
      ]);
      setStocks(stockData);
      setAlerts(alertData);
      setIngredients(ingData);
    } catch {
      setError('Failed to load inventory data');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc((v) => !v);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const openEdit = (row: InventoryStock) => {
    setEditingStock(row);
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Inventory</h1>
          <p className="text-gray-500 mt-1">
            Ingredient stock levels, thresholds, and low-stock alerts
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
        >
          <Plus size={18} />
          Add Stock Entry
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

      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Package className="text-primary-600" size={22} strokeWidth={2} />
          <h2 className="text-lg font-semibold text-gray-900">Stock Overview</h2>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-gray-400">Loading stock levels...</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px]">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      <button
                        type="button"
                        onClick={() => toggleSort('name')}
                        className="inline-flex items-center gap-1.5 hover:text-gray-800"
                      >
                        Ingredient Name
                        <ArrowUpDown size={14} className="text-gray-400" />
                      </button>
                    </th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      <button
                        type="button"
                        onClick={() => toggleSort('quantity')}
                        className="inline-flex items-center gap-1.5 hover:text-gray-800"
                      >
                        Quantity
                        <ArrowUpDown size={14} className="text-gray-400" />
                      </button>
                    </th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Min Threshold
                    </th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      <button
                        type="button"
                        onClick={() => toggleSort('updated')}
                        className="inline-flex items-center gap-1.5 hover:text-gray-800"
                      >
                        Last Updated
                        <ArrowUpDown size={14} className="text-gray-400" />
                      </button>
                    </th>
                    <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {sortedStocks.map((row) => {
                    const unit =
                      row.ingredient_id != null
                        ? ingredientUnitById.get(row.ingredient_id) ?? ''
                        : '';
                    const status = stockStatus(row.quantity, row.min_threshold);
                    return (
                      <tr key={row.id} className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4">
                          <p className="text-sm font-medium text-gray-900">
                            {row.ingredient_name ?? '—'}
                          </p>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-900 tabular-nums">
                          {row.quantity}
                          {unit ? (
                            <span className="text-gray-500 ml-1">{unit}</span>
                          ) : null}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-700 tabular-nums">
                          {row.min_threshold != null ? (
                            <>
                              {row.min_threshold}
                              {unit ? (
                                <span className="text-gray-500 ml-1">{unit}</span>
                              ) : null}
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <span
                            className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${status.className}`}
                          >
                            {status.label}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600 whitespace-nowrap">
                          {formatDateTime(row.updated_at)}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button
                            type="button"
                            onClick={() => openEdit(row)}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                            title="Edit quantity and threshold"
                          >
                            <Pencil size={16} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {sortedStocks.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-gray-400">
                        <div className="flex flex-col items-center gap-2">
                          <Package className="text-gray-300" size={40} strokeWidth={1.5} />
                          <p>No ingredient stock entries yet. Add one to get started.</p>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section>
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="text-amber-600" size={22} strokeWidth={2} />
          <h2 className="text-lg font-semibold text-gray-900">Stock Alerts</h2>
        </div>

        <div className="rounded-xl border-2 border-amber-200 bg-amber-50/50 shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-amber-800/70">Loading alerts...</div>
          ) : alerts.length === 0 ? (
            <div className="px-6 py-10 text-center text-amber-900/60 text-sm">
              No active stock alerts. All tracked items are within thresholds.
            </div>
          ) : (
            <ul className="divide-y divide-amber-200/80">
              {alerts.map((a) => (
                <li
                  key={a.id}
                  className="flex flex-col sm:flex-row sm:items-center gap-3 px-5 py-4 bg-white/60"
                >
                  <AlertTriangle
                    className="shrink-0 text-amber-600 sm:mt-0.5"
                    size={22}
                    strokeWidth={2}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-900">
                      {a.ingredient_name ?? 'Unknown ingredient'}
                    </p>
                    <p className="text-sm text-amber-900/90 mt-0.5">
                      Current: <span className="tabular-nums font-medium">{a.current_qty}</span>
                      {' · '}
                      Min threshold: <span className="tabular-nums font-medium">{a.min_qty}</span>
                    </p>
                    <p className="text-xs text-gray-500 mt-1">{formatDateTime(a.timestamp)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {showAddModal && (
        <AddStockModal
          ingredients={ingredients}
          stockedIngredientIds={new Set(
            ingredientStocks.map((s) => s.ingredient_id).filter((id): id is string => id != null)
          )}
          onClose={() => setShowAddModal(false)}
          onSaved={() => {
            setShowAddModal(false);
            void loadAll();
          }}
        />
      )}

      {editingStock && (
        <UpdateStockModal
          stock={editingStock}
          unit={
            editingStock.ingredient_id != null
              ? ingredientUnitById.get(editingStock.ingredient_id) ?? ''
              : ''
          }
          onClose={() => setEditingStock(null)}
          onSaved={() => {
            setEditingStock(null);
            void loadAll();
          }}
        />
      )}
    </div>
  );
}

function AddStockModal({
  ingredients,
  stockedIngredientIds,
  onClose,
  onSaved,
}: {
  ingredients: Ingredient[];
  stockedIngredientIds: Set<string>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const available = ingredients.filter((i) => !stockedIngredientIds.has(i.id));
  const [ingredientId, setIngredientId] = useState(available[0]?.id ?? '');
  const [quantity, setQuantity] = useState('');
  const [minThreshold, setMinThreshold] = useState('');
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState('');

  const selected = ingredients.find((i) => i.id === ingredientId);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setLocalError('');

    const qty = Number(quantity);
    if (!ingredientId) {
      setLocalError('Select an ingredient');
      setSaving(false);
      return;
    }
    if (Number.isNaN(qty) || qty < 0) {
      setLocalError('Quantity must be a valid non-negative number');
      setSaving(false);
      return;
    }

    const payload: AddStockPayload = {
      ingredient_id: ingredientId,
      quantity: qty,
    };
    const minNum = minThreshold.trim() === '' ? undefined : Number(minThreshold);
    if (minNum !== undefined) {
      if (Number.isNaN(minNum) || minNum < 0) {
        setLocalError('Min threshold must be a valid non-negative number');
        setSaving(false);
        return;
      }
      payload.min_threshold = minNum;
    }

    try {
      await inventoryApi.addStock(payload);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to add stock';
      setLocalError(typeof msg === 'string' ? msg : 'Failed to add stock');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Add Stock Entry</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {localError && (
            <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{localError}</div>
          )}

          {available.length === 0 ? (
            <p className="text-sm text-gray-600">
              All active ingredients already have a stock line, or there are no ingredients. Add
              ingredients first or remove duplicate coverage in the backend.
            </p>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ingredient</label>
                <select
                  value={ingredientId}
                  onChange={(e) => setIngredientId(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                >
                  {available.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name} ({i.unit})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Quantity
                  {selected ? (
                    <span className="text-gray-400 font-normal"> ({selected.unit})</span>
                  ) : null}
                </label>
                <input
                  type="number"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  required
                  min={0}
                  step="any"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Min threshold <span className="text-gray-400 font-normal">(optional)</span>
                  {selected ? (
                    <span className="text-gray-400 font-normal"> ({selected.unit})</span>
                  ) : null}
                </label>
                <input
                  type="number"
                  value={minThreshold}
                  onChange={(e) => setMinThreshold(e.target.value)}
                  min={0}
                  step="any"
                  placeholder="Alert when below this level"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                />
              </div>
            </>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || available.length === 0}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving...' : 'Add Stock'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function UpdateStockModal({
  stock,
  unit,
  onClose,
  onSaved,
}: {
  stock: InventoryStock;
  unit: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [quantity, setQuantity] = useState(String(stock.quantity));
  const [minThreshold, setMinThreshold] = useState(
    stock.min_threshold != null ? String(stock.min_threshold) : ''
  );
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setLocalError('');

    const qty = Number(quantity);
    if (Number.isNaN(qty) || qty < 0) {
      setLocalError('Quantity must be a valid non-negative number');
      setSaving(false);
      return;
    }

    const payload: UpdateStockPayload = { quantity: qty };
    const minNum = minThreshold.trim() === '' ? undefined : Number(minThreshold);
    if (minNum !== undefined) {
      if (Number.isNaN(minNum) || minNum < 0) {
        setLocalError('Min threshold must be a valid non-negative number');
        setSaving(false);
        return;
      }
      payload.min_threshold = minNum;
    }

    try {
      await inventoryApi.updateStock(stock.id, payload);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to update stock';
      setLocalError(typeof msg === 'string' ? msg : 'Failed to update stock');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Update Stock</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {localError && (
            <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{localError}</div>
          )}

          <p className="text-sm text-gray-600">
            <span className="font-medium text-gray-900">{stock.ingredient_name ?? 'Ingredient'}</span>
            {unit ? <span className="text-gray-500"> · {unit}</span> : null}
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Quantity
              {unit ? <span className="text-gray-400 font-normal"> ({unit})</span> : null}
            </label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
              min={0}
              step="any"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Min threshold <span className="text-gray-400 font-normal">(optional)</span>
              {unit ? <span className="text-gray-400 font-normal"> ({unit})</span> : null}
            </label>
            <input
              type="number"
              value={minThreshold}
              onChange={(e) => setMinThreshold(e.target.value)}
              min={0}
              step="any"
              placeholder="Leave empty for no threshold"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
