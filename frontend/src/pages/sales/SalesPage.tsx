import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { salesApi, type SalesOpenPayload, type SalesRecordDetail } from '../../api/sales';
import { storesApi } from '../../api/stores';
import { productsApi, type ProductDetail } from '../../api/products';
import { useAuth } from '../../context/AuthContext';
import type { Store } from '../../types';

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

function toIsoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

export default function SalesPage() {
  const { role, user } = useAuth();
  const navigate = useNavigate();
  const { salesDate } = useParams();
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<ProductDetail[]>([]);
  const [records, setRecords] = useState<SalesRecordDetail[]>([]);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [error, setError] = useState('');
  const [filterClosed, setFilterClosed] = useState<'all' | 'open' | 'closed'>('all');
  const [selectedStoreId, setSelectedStoreId] = useState(user?.store_id ?? '');
  const [form, setForm] = useState({
    store_id: user?.store_id ?? '',
    product_id: '',
    date: new Date().toISOString().slice(0, 10),
    opening_stock: '',
    notes: '',
  });
  const [previousClosingStock, setPreviousClosingStock] = useState<number | null>(null);
  const [editingRecord, setEditingRecord] = useState<SalesRecordDetail | null>(null);
  const [editForm, setEditForm] = useState({
    opening_stock: '',
    quantity_sold: '',
    closing_stock: '',
    notes: '',
  });

  const isOwner = role === 'owner';
  const isStoreManager = role === 'store_manager';
  const canManageSales = isOwner || isStoreManager;
  const activeSalesDate = salesDate ?? '';
  const todayIso = toIsoDate(new Date());
  const isOpeningLockedByCarryForward = isStoreManager && previousClosingStock != null;

  const activeProducts = useMemo(() => products.filter((p) => p.is_active), [products]);

  async function loadLookups() {
    const [storesData, productsData] = await Promise.all([
      storesApi.list({ is_active: true }),
      productsApi.list({ is_active: true }),
    ]);
    setStores(storesData);
    setProducts(productsData);
    const defaultStoreId = user?.store_id ?? storesData[0]?.id ?? '';
    setSelectedStoreId(defaultStoreId);
    setForm((prev) => ({
      ...prev,
      store_id: prev.store_id || defaultStoreId,
      product_id: prev.product_id || productsData[0]?.id || '',
      date: activeSalesDate || prev.date,
    }));
  }

  async function loadDateOptions() {
    const params: { store_id?: string } = {};
    if (selectedStoreId) params.store_id = selectedStoreId;
    const allRecords = await salesApi.list(params);
    const dates = Array.from(new Set(allRecords.map((r) => r.date))).sort((a, b) => b.localeCompare(a));
    setAvailableDates(dates);
  }

  async function loadRecords() {
    const params: {
      store_id?: string;
      is_closed?: boolean;
      date_from?: string;
      date_to?: string;
    } = {};
    if (selectedStoreId) params.store_id = selectedStoreId;
    if (filterClosed === 'open') params.is_closed = false;
    if (filterClosed === 'closed') params.is_closed = true;
    if (activeSalesDate) {
      params.date_from = activeSalesDate;
      params.date_to = activeSalesDate;
    }
    const data = await salesApi.list(params);
    setRecords(data);
  }

  async function bootstrap() {
    try {
      setLoading(true);
      setError('');
      await loadLookups();
      await loadDateOptions();
      await loadRecords();
    } catch {
      setError('Failed to load sales data');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!loading) {
      void (async () => {
        try {
          await loadDateOptions();
          await loadRecords();
        } catch {
          setError('Failed to load sales records');
        }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStoreId, filterClosed, activeSalesDate]);

  useEffect(() => {
    if (activeSalesDate) {
      setForm((prev) => ({ ...prev, date: activeSalesDate }));
    }
  }, [activeSalesDate]);

  useEffect(() => {
    if (!isStoreManager || !form.store_id || !form.product_id || !form.date) {
      setPreviousClosingStock(null);
      return;
    }

    void (async () => {
      try {
        const history = await salesApi.list({
          store_id: form.store_id,
          product_id: form.product_id,
          date_to: form.date,
        });
        const previous = history.find((r) => r.date < form.date);
        if (!previous) {
          setPreviousClosingStock(null);
          return;
        }
        setPreviousClosingStock(previous.closing_stock);
        setForm((prev) => ({ ...prev, opening_stock: String(previous.closing_stock) }));
      } catch {
        setPreviousClosingStock(null);
      }
    })();
  }, [isStoreManager, form.store_id, form.product_id, form.date]);

  const handleOpenDay = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const openingStock = isOpeningLockedByCarryForward
      ? Number(previousClosingStock)
      : Number(form.opening_stock);
    if (!Number.isInteger(openingStock) || openingStock < 0) {
      setError('Opening stock must be a non-negative integer');
      setSaving(false);
      return;
    }
    if (!form.store_id || !form.product_id) {
      setError('Store and product are required');
      setSaving(false);
      return;
    }
    try {
      const payload: SalesOpenPayload = {
        store_id: form.store_id,
        product_id: form.product_id,
        date: form.date,
        opening_stock: openingStock,
        notes: form.notes.trim() || undefined,
      };
      await salesApi.openDay(payload);
      setForm((prev) => ({ ...prev, opening_stock: '', notes: '' }));
      if (form.date !== activeSalesDate) {
        navigate(`/sales/${form.date}`);
      }
      await loadDateOptions();
      await loadRecords();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to open sales day';
      setError(typeof msg === 'string' ? msg : 'Failed to open sales day');
    } finally {
      setSaving(false);
    }
  };

  const canModifyRecord = (record: SalesRecordDetail): boolean => {
    if (isOwner) return true;
    if (isStoreManager) return record.date === todayIso;
    return false;
  };

  const handleRecordSale = async (record: SalesRecordDetail) => {
    const qtyInput = window.prompt(`Enter sold quantity for ${record.product_name ?? 'product'}`);
    if (!qtyInput) return;
    const quantitySold = Number(qtyInput);
    if (!Number.isInteger(quantitySold) || quantitySold <= 0) {
      setError('Sold quantity must be a positive integer');
      return;
    }
    try {
      setError('');
      await salesApi.recordSale(record.id, { quantity_sold: quantitySold });
      await loadRecords();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to record sale';
      setError(typeof msg === 'string' ? msg : 'Failed to record sale');
    }
  };

  const handleCloseDay = async (record: SalesRecordDetail) => {
    const closingInput = window.prompt(
      `Enter closing stock for ${record.product_name ?? 'product'}`,
      String(record.closing_stock)
    );
    if (!closingInput) return;
    const closingStock = Number(closingInput);
    if (!Number.isInteger(closingStock) || closingStock < 0) {
      setError('Closing stock must be a non-negative integer');
      return;
    }
    try {
      setError('');
      await salesApi.closeDay(record.id, {
        closing_stock: closingStock,
        auto_record_wastage: true,
      });
      await loadRecords();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to close sales day';
      setError(typeof msg === 'string' ? msg : 'Failed to close sales day');
    }
  };

  const handleReopenDay = async (record: SalesRecordDetail) => {
    try {
      setError('');
      await salesApi.reopenDay(record.id);
      await loadRecords();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to reopen sales day';
      setError(typeof msg === 'string' ? msg : 'Failed to reopen sales day');
    }
  };

  const openEditModal = (record: SalesRecordDetail) => {
    setEditingRecord(record);
    setEditForm({
      opening_stock: String(record.opening_stock),
      quantity_sold: String(record.quantity_sold),
      closing_stock: String(record.closing_stock),
      notes: record.notes ?? '',
    });
  };

  const closeEditModal = () => {
    setEditingRecord(null);
  };

  const handleSaveEdit = async (e: FormEvent) => {
    e.preventDefault();
    if (!editingRecord) return;

    const openingStock = Number(editForm.opening_stock);
    const quantitySold = Number(editForm.quantity_sold);
    const closingStock = Number(editForm.closing_stock);
    if (!Number.isInteger(openingStock) || openingStock < 0) {
      setError('Opening stock must be a non-negative integer');
      return;
    }
    if (!Number.isInteger(quantitySold) || quantitySold < 0) {
      setError('Sold quantity must be a non-negative integer');
      return;
    }
    if (editingRecord.is_closed && (!Number.isInteger(closingStock) || closingStock < 0)) {
      setError('Closing stock must be a non-negative integer');
      return;
    }

    try {
      setEditSaving(true);
      setError('');
      await salesApi.updateRecord(editingRecord.id, {
        opening_stock: openingStock,
        quantity_sold: quantitySold,
        closing_stock: editingRecord.is_closed ? closingStock : undefined,
        notes: editForm.notes.trim() || undefined,
      });
      closeEditModal();
      await loadRecords();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to update sales record';
      setError(typeof msg === 'string' ? msg : 'Failed to update sales record');
    } finally {
      setEditSaving(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Sales & Store Operations</h1>
      <p className="text-gray-500 mb-3">Daily open, sell, and close workflow with variance tracking</p>
      <p className="text-xs text-gray-500 mb-6">
        {activeSalesDate
          ? `Viewing sales page for date: ${formatDate(activeSalesDate)}`
          : 'Select a date page below for clearer daily operations.'}
      </p>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
          {error}
          <button type="button" onClick={() => setError('')} className="float-right font-bold">&times;</button>
        </div>
      )}

      {canManageSales ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-5">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Open Sales Day</h2>
          <form onSubmit={handleOpenDay} className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <select
              value={form.store_id}
              onChange={(e) => setForm((prev) => ({ ...prev, store_id: e.target.value }))}
              disabled={!isOwner}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              {stores.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <select
              value={form.product_id}
              onChange={(e) => setForm((prev) => ({ ...prev, product_id: e.target.value }))}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              {activeProducts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.sku})
                </option>
              ))}
            </select>
            <input
              type="date"
              value={form.date}
              onChange={(e) => setForm((prev) => ({ ...prev, date: e.target.value }))}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              type="number"
              min={0}
              step={1}
              placeholder="Opening stock"
              value={form.opening_stock}
              onChange={(e) => setForm((prev) => ({ ...prev, opening_stock: e.target.value }))}
              disabled={isOpeningLockedByCarryForward}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Open Day'}
            </button>
          </form>
          {isStoreManager && (
            <p className="text-xs text-gray-500 mt-2">
              {isOpeningLockedByCarryForward
                ? `Opening stock is locked to previous day closing: ${previousClosingStock}.`
                : 'No previous day record found for this product. Opening stock can be entered for initial setup.'}
            </p>
          )}
        </div>
      ) : (
        <div className="bg-blue-50 border border-blue-100 text-blue-800 rounded-xl px-4 py-3 mb-5 text-sm">
          Finance manager has read-only access on sales records.
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {isOwner && (
          <select
            value={selectedStoreId}
            onChange={(e) => setSelectedStoreId(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            {stores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        )}
        <select
          value={filterClosed}
          onChange={(e) => setFilterClosed(e.target.value as 'all' | 'open' | 'closed')}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
        >
          <option value="all">All</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        <button
          type="button"
          onClick={() => navigate('/sales')}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            !activeSalesDate
              ? 'bg-primary-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          All Dates
        </button>
        {availableDates.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => navigate(`/sales/${d}`)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeSalesDate === d
                ? 'bg-primary-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {formatDate(d)}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading sales records...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1150px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Date</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Store</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Product</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Opening</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Today Received</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Total Product</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Sold</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Closing</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Wastage</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Variance</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Amount</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {records.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 text-sm text-gray-700">{formatDate(r.date)}</td>
                    <td className="px-4 py-3 text-sm text-gray-700">{r.store_name ?? '—'}</td>
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">{r.product_name ?? '—'}</td>
                    <td className="px-4 py-3 text-sm text-gray-700 text-right tabular-nums">{r.opening_stock}</td>
                    <td className="px-4 py-3 text-sm text-blue-700 text-right tabular-nums">{r.today_received_qty}</td>
                    <td className="px-4 py-3 text-sm text-indigo-700 text-right tabular-nums font-medium">{r.total_product_qty}</td>
                    <td className="px-4 py-3 text-sm text-gray-700 text-right tabular-nums">{r.quantity_sold}</td>
                    <td className="px-4 py-3 text-sm text-gray-700 text-right tabular-nums">{r.closing_stock}</td>
                    <td className="px-4 py-3 text-sm text-amber-700 text-right tabular-nums">{r.wastage_qty}</td>
                    <td className="px-4 py-3 text-sm text-right tabular-nums">
                      <span className={r.variance_qty === 0 ? 'text-gray-500' : 'text-red-600 font-medium'}>{r.variance_qty}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 text-right tabular-nums">ETB {Number(r.total_amount).toFixed(2)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${r.is_closed ? 'bg-gray-100 text-gray-700' : 'bg-green-50 text-green-700'}`}>
                        {r.is_closed ? 'Closed' : 'Open'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {canManageSales ? (
                        <div className="inline-flex gap-2">
                          <button
                            type="button"
                            onClick={() => openEditModal(r)}
                            disabled={!canModifyRecord(r)}
                            title={!canModifyRecord(r) ? "Past dates are locked for store manager" : undefined}
                            className={`px-2.5 py-1.5 text-xs rounded-lg ${
                              canModifyRecord(r)
                                ? 'bg-gray-50 text-gray-700 hover:bg-gray-100'
                                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                            }`}
                          >
                            Edit
                          </button>
                          {!r.is_closed && canModifyRecord(r) && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleRecordSale(r)}
                                className="px-2.5 py-1.5 text-xs rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100"
                              >
                                Record Sale
                              </button>
                              <button
                                type="button"
                                onClick={() => handleCloseDay(r)}
                                className="px-2.5 py-1.5 text-xs rounded-lg bg-green-50 text-green-700 hover:bg-green-100"
                              >
                                Close Day
                              </button>
                            </>
                          )}
                          {r.is_closed && canModifyRecord(r) && (
                            <button
                              type="button"
                              onClick={() => handleReopenDay(r)}
                              className="px-2.5 py-1.5 text-xs rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100"
                            >
                              Reopen
                            </button>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-gray-500">Read-only</span>
                      )}
                    </td>
                  </tr>
                ))}
                {records.length === 0 && (
                  <tr>
                    <td colSpan={13} className="px-6 py-10 text-center text-gray-400">
                      No sales records found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editingRecord && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-lg rounded-xl shadow-lg border border-gray-200">
            <div className="px-5 py-4 border-b border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900">
                Edit Sales Record - {editingRecord.product_name ?? 'Product'}
              </h3>
              <p className="text-xs text-gray-500 mt-1">
                Date: {formatDate(editingRecord.date)} | Status: {editingRecord.is_closed ? 'Closed' : 'Open'}
              </p>
            </div>
            <form onSubmit={handleSaveEdit} className="p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Opening Stock</label>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={editForm.opening_stock}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, opening_stock: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Sold Quantity</label>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={editForm.quantity_sold}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, quantity_sold: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  />
                </div>
              </div>

              {editingRecord.is_closed && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Closing Stock</label>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={editForm.closing_stock}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, closing_stock: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Notes (Optional)</label>
                <textarea
                  rows={3}
                  value={editForm.notes}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, notes: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={closeEditModal}
                  className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSaving}
                  className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  {editSaving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
