import { useState, useEffect, useMemo, type FormEvent } from 'react';
import { wastageApi, type WastageDetail, type CreateWastagePayload } from '../../api/wastage';
import { type ProductDetail, productsApi } from '../../api/products';
import { ingredientsApi } from '../../api/ingredients';
import { storesApi } from '../../api/stores';
import type { Store } from '../../types';
import { useAuth } from '../../context/AuthContext';
import { Plus, Trash2, X } from 'lucide-react';

const REASON_OPTIONS = [
  { value: 'spoilage', label: 'Spoilage' },
  { value: 'damage', label: 'Damage' },
  { value: 'expiry', label: 'Expiry' },
  { value: 'production_loss', label: 'Production Loss' },
  { value: 'other', label: 'Other' },
] as const;

const REASON_STYLES: Record<string, string> = {
  spoilage: 'bg-yellow-50 text-yellow-700',
  damage: 'bg-red-50 text-red-700',
  expiry: 'bg-orange-50 text-orange-700',
  production_loss: 'bg-purple-50 text-purple-700',
  other: 'bg-gray-100 text-gray-600',
};

const WASTAGE_PAGE_SIZE = 100;
const WASTAGE_MAX_PAGES = 20;

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

function reasonLabel(value: string): string {
  const found = REASON_OPTIONS.find((r) => r.value === value);
  return found?.label ?? value;
}

function money(value: number | null | undefined): string {
  return `ETB ${Number(value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function qtyWithUnit(record: WastageDetail): string {
  const unit =
    record.source_type === 'production'
      ? (record.ingredient_id ? record.ingredient_unit : record.product_unit)
      : record.product_unit;
  return `${record.quantity}${unit ? ` ${unit}` : ''}`;
}

function itemLabel(record: WastageDetail): string {
  if (record.ingredient_id) return record.ingredient_name ?? '—';
  if (record.product_id) return record.product_name ?? '—';
  return '—';
}

export default function WastagePage() {
  const { role, user } = useAuth();
  const canRecordWastage =
    role === 'owner' || role === 'production_manager' || role === 'store_manager';
  const [records, setRecords] = useState<WastageDetail[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [ownerView, setOwnerView] = useState<string>('all');
  const canUseAdvancedView = role === 'owner' || role === 'finance_manager';

  const filteredRecords = records.filter((r) => {
    if (!canUseAdvancedView) return true;
    if (ownerView === 'all') return true;
    if (ownerView === 'production_products') {
      return r.source_type === 'production' && r.product_id != null;
    }
    if (ownerView === 'production_ingredients') {
      return r.source_type === 'production' && r.ingredient_id != null;
    }
    if (ownerView.startsWith('store:')) {
      const storeId = ownerView.slice('store:'.length);
      return r.source_type === 'store' && r.store_id === storeId;
    }
    return true;
  });

  const ownerSummary = useMemo(() => {
    const storeWastageQty = records
      .filter((r) => r.source_type === 'store')
      .reduce((sum, r) => sum + r.quantity, 0);
    const productionProductQty = records
      .filter((r) => r.source_type === 'production' && r.product_id != null)
      .reduce((sum, r) => sum + r.quantity, 0);
    const ingredientWastageQty = records
      .filter((r) => r.source_type === 'production' && r.ingredient_id != null)
      .reduce((sum, r) => sum + r.quantity, 0);
    return {
      storeWastageQty,
      productionProductQty,
      ingredientWastageQty,
    };
  }, [records]);

  async function fetchRecords() {
    try {
      setLoading(true);
      setError('');
      const loadAllWastage = async (): Promise<WastageDetail[]> => {
        let page = 0;
        let skip = 0;
        const all: WastageDetail[] = [];
        while (page < WASTAGE_MAX_PAGES) {
          const chunk = await wastageApi.list({
            skip,
            limit: WASTAGE_PAGE_SIZE,
          });
          all.push(...chunk);
          if (chunk.length < WASTAGE_PAGE_SIZE) break;
          page += 1;
          skip += WASTAGE_PAGE_SIZE;
        }
        return all;
      };

      const tasks: Promise<unknown>[] = [loadAllWastage()];
      if (canUseAdvancedView) tasks.push(storesApi.list({ is_active: true }));
      const [data, storeData] = await Promise.all(tasks) as [WastageDetail[], Store[]?];
      setRecords(data);
      if (storeData) {
        setStores(storeData);
      }
    } catch {
      setError('Failed to load wastage records');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchRecords();
  }, [canUseAdvancedView]);

  const handleSaved = () => {
    setShowModal(false);
    fetchRecords();
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Wastage Records</h1>
          <p className="text-gray-500 mt-1">Track store and production wastage records</p>
        </div>
        {canRecordWastage ? (
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
          >
            <Plus size={18} />
            Record Wastage
          </button>
        ) : (
          <span className="text-xs text-gray-500">Read-only view for finance manager</span>
        )}
      </div>

      {canUseAdvancedView && (
        <div className="mb-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3">
              <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide">Store Wastage</p>
              <p className="text-xl font-bold text-blue-900 tabular-nums mt-1">{ownerSummary.storeWastageQty}</p>
            </div>
            <div className="bg-purple-50 border border-purple-100 rounded-lg px-4 py-3">
              <p className="text-xs font-semibold text-purple-700 uppercase tracking-wide">Product Wastage During Production</p>
              <p className="text-xl font-bold text-purple-900 tabular-nums mt-1">{ownerSummary.productionProductQty}</p>
            </div>
            <div className="bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">
              <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide">Ingredient Wastage</p>
              <p className="text-xl font-bold text-amber-900 tabular-nums mt-1">{ownerSummary.ingredientWastageQty}</p>
            </div>
          </div>

          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setOwnerView('all')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                ownerView === 'all'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              All Wastage
            </button>
            {stores.map((s) => {
              const key = `store:${s.id}`;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setOwnerView(key)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    ownerView === key
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {s.name} Wastage
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setOwnerView('production_products')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                ownerView === 'production_products'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              Product Wastage During Production
            </button>
            <button
              type="button"
              onClick={() => setOwnerView('production_ingredients')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                ownerView === 'production_ingredients'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              Ingredient Wastage
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
          {error}
          <button type="button" onClick={() => setError('')} className="float-right font-bold">
            &times;
          </button>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading wastage records...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Source</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Location</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Item</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Recorded By</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Qty</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Price</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Reason</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredRecords.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 text-sm text-gray-600 whitespace-nowrap">{formatDate(r.date)}</td>
                    <td className="px-6 py-4 text-sm text-gray-700">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        r.source_type === 'production' ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'
                      }`}>
                        {r.source_type === 'production' ? 'Production' : 'Store'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{r.source_type === 'production' ? 'Production Inventory' : (r.store_name ?? '—')}</td>
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {itemLabel(r)}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-700">{r.recorded_by_name ?? r.recorded_by ?? '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-700 tabular-nums">{qtyWithUnit(r)}</td>
                    <td className="px-6 py-4 text-sm text-gray-700 tabular-nums">
                      {r.total_price != null ? (
                        <>
                          <div>{money(r.total_price)}</div>
                          {r.unit_price != null && (
                            <div className="text-xs text-gray-500">{money(r.unit_price)} / unit</div>
                          )}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${REASON_STYLES[r.reason] ?? 'bg-gray-100 text-gray-600'}`}>
                        {reasonLabel(r.reason)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 max-w-[200px] truncate">{r.notes ?? '—'}</td>
                  </tr>
                ))}
                {filteredRecords.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-6 py-12 text-center text-gray-400">
                      <div className="flex flex-col items-center gap-2">
                        <Trash2 className="text-gray-300" size={40} strokeWidth={1.5} />
                        <p>No wastage records yet.</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && canRecordWastage && (
        <WastageFormModal
          role={role}
          userStoreId={user?.store_id}
          onClose={() => setShowModal(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function WastageFormModal({
  role,
  userStoreId,
  onClose,
  onSaved,
}: {
  role: string | null;
  userStoreId?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<ProductDetail[]>([]);
  const [ingredients, setIngredients] = useState<Array<{ id: string; name: string; unit: string }>>([]);
  const [loadingData, setLoadingData] = useState(true);

  const [sourceType, setSourceType] = useState<'store' | 'production'>(
    role === 'production_manager' ? 'production' : 'store'
  );
  const [productionItemType, setProductionItemType] = useState<'ingredient' | 'product'>('ingredient');
  const [storeId, setStoreId] = useState('');
  const [productId, setProductId] = useState('');
  const [ingredientId, setIngredientId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [reason, setReason] = useState('spoilage');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const roleSourceType =
    role === 'store_manager' ? 'store' : role === 'production_manager' ? 'production' : null;

  useEffect(() => {
    const tasks: Promise<unknown>[] = [];
    tasks.push(storesApi.list({ is_active: true }));
    tasks.push(productsApi.list({ is_active: true }));
    if (role !== 'store_manager') {
      tasks.push(ingredientsApi.list({ is_active: true }));
    }

    Promise.all(tasks)
      .then((results) => {
        const s = results[0] as Store[];
        const p = results[1] as ProductDetail[];
        const ing = (results[2] as Array<{ id: string; name: string; unit: string }> | undefined) ?? [];
        setStores(s);
        setProducts(p);
        setIngredients(ing);
        if (userStoreId) setStoreId(userStoreId);
        else if (s.length > 0) setStoreId(s[0].id);
        if (p.length > 0) setProductId(p[0].id);
        if (ing.length > 0) setIngredientId(ing[0].id);
      })
      .catch(() => setError('Failed to load wastage form data'))
      .finally(() => setLoadingData(false));
  }, [role, userStoreId]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty < 1) {
      setError('Quantity must be a positive integer');
      setSaving(false);
      return;
    }

    try {
      const payload: CreateWastagePayload = {
        source_type: roleSourceType ?? sourceType,
        date,
        quantity: qty,
        reason,
        notes: notes.trim() || undefined,
      };
      if ((roleSourceType ?? sourceType) === 'store') {
        payload.store_id = userStoreId ?? storeId;
        payload.product_id = productId;
      } else {
        if (productionItemType === 'ingredient') payload.ingredient_id = ingredientId;
        else payload.product_id = productId;
      }
      await wastageApi.create(payload);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to record wastage';
      setError(typeof msg === 'string' ? msg : 'Failed to record wastage');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Record Wastage</h2>
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
              {roleSourceType == null && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Wastage Source</label>
                  <select
                    value={sourceType}
                    onChange={(e) => setSourceType(e.target.value as 'store' | 'production')}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  >
                    <option value="store">Store Wastage (Product)</option>
                    <option value="production">Production Wastage</option>
                  </select>
                </div>
              )}

              {(roleSourceType ?? sourceType) === 'store' ? (
                <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Store</label>
                <select
                  value={userStoreId ?? storeId}
                  onChange={(e) => setStoreId(e.target.value)}
                  required
                  disabled={!!userStoreId}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                >
                  {stores.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
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
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Production Wastage Type</label>
                    <select
                      value={productionItemType}
                      onChange={(e) => setProductionItemType(e.target.value as 'ingredient' | 'product')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                    >
                      <option value="ingredient">Ingredient Wastage (raw material)</option>
                      <option value="product">Product Wastage During Production</option>
                    </select>
                  </div>
                  {productionItemType === 'ingredient' ? (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Ingredient</label>
                      <select
                        value={ingredientId}
                        onChange={(e) => setIngredientId(e.target.value)}
                        required
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                      >
                        {ingredients.map((ing) => (
                          <option key={ing.id} value={ing.id}>
                            {ing.name} ({ing.unit})
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
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
                  )}
                </>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Quantity</label>
                  <input
                    type="number"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    required
                    min={1}
                    step={1}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
                  <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Reason</label>
                <select
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                >
                  {REASON_OPTIONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Notes <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm resize-y"
                />
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
              {saving ? 'Saving...' : 'Record Wastage'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
