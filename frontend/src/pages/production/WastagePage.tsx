import { useState, useEffect, type FormEvent } from 'react';
import { wastageApi, type WastageDetail, type CreateWastagePayload } from '../../api/wastage';
import { type ProductDetail, productsApi } from '../../api/products';
import { storesApi } from '../../api/stores';
import type { Store } from '../../types';
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

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

function reasonLabel(value: string): string {
  const found = REASON_OPTIONS.find((r) => r.value === value);
  return found?.label ?? value;
}

export default function WastagePage() {
  const [records, setRecords] = useState<WastageDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);

  async function fetchRecords() {
    try {
      setLoading(true);
      setError('');
      const data = await wastageApi.list();
      setRecords(data);
    } catch {
      setError('Failed to load wastage records');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchRecords();
  }, []);

  const handleSaved = () => {
    setShowModal(false);
    fetchRecords();
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Wastage Records</h1>
          <p className="text-gray-500 mt-1">Track and record product wastage across stores</p>
        </div>
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
        >
          <Plus size={18} />
          Record Wastage
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

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading wastage records...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Store</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Product</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Recorded By</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Qty</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Reason</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {records.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 text-sm text-gray-600 whitespace-nowrap">{formatDate(r.date)}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{r.store_name ?? '—'}</td>
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">{r.product_name ?? '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-700">{r.recorded_by_name ?? r.recorded_by ?? '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-700 tabular-nums">{r.quantity}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${REASON_STYLES[r.reason] ?? 'bg-gray-100 text-gray-600'}`}>
                        {reasonLabel(r.reason)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 max-w-[200px] truncate">{r.notes ?? '—'}</td>
                  </tr>
                ))}
                {records.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-gray-400">
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

      {showModal && (
        <WastageFormModal
          onClose={() => setShowModal(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function WastageFormModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<ProductDetail[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  const [storeId, setStoreId] = useState('');
  const [productId, setProductId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [reason, setReason] = useState('spoilage');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([storesApi.list(), productsApi.list({ is_active: true })])
      .then(([s, p]) => {
        setStores(s);
        setProducts(p);
        if (s.length > 0) setStoreId(s[0].id);
        if (p.length > 0) setProductId(p[0].id);
      })
      .catch(() => setError('Failed to load stores/products'))
      .finally(() => setLoadingData(false));
  }, []);

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
        store_id: storeId,
        product_id: productId,
        date,
        quantity: qty,
        reason,
        notes: notes.trim() || undefined,
      };
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
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Store</label>
                <select
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value)}
                  required
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
