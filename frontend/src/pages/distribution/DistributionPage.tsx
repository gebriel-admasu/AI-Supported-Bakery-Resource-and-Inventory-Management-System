import { useState, useEffect, type FormEvent } from 'react';
import {
  distributionApi,
  type DistributionDetail,
  type DistItemPayload,
  type CreateDistributionPayload,
  type ReceiveItemPayload,
} from '../../api/distribution';
import { type ProductDetail, productsApi } from '../../api/products';
import { storesApi } from '../../api/stores';
import { usersApi } from '../../api/users';
import type { Store, User } from '../../types';
import { useAuth } from '../../context/AuthContext';
import {
  Plus,
  Truck,
  PackageCheck,
  CheckCircle2,
  ArrowRight,
  X,
  Trash2,
  AlertTriangle,
} from 'lucide-react';

const STATUS_OPTIONS = ['all', 'dispatched', 'in_transit', 'received', 'confirmed'] as const;

const STATUS_STYLES: Record<string, string> = {
  dispatched: 'bg-blue-50 text-blue-700',
  in_transit: 'bg-amber-50 text-amber-700',
  received: 'bg-green-50 text-green-700',
  confirmed: 'bg-emerald-50 text-emerald-800',
};

const STATUS_LABELS: Record<string, string> = {
  dispatched: 'Dispatched',
  in_transit: 'In Transit',
  received: 'Received',
  confirmed: 'Confirmed',
};

const DISCREPANCY_STYLES: Record<string, string> = {
  none: 'bg-gray-100 text-gray-600',
  pending_approval: 'bg-amber-50 text-amber-700',
  approved: 'bg-green-50 text-green-700',
  rejected: 'bg-red-50 text-red-700',
};

const DISCREPANCY_LABELS: Record<string, string> = {
  none: 'No discrepancy',
  pending_approval: 'Pending approval',
  approved: 'Approved',
  rejected: 'Rejected',
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

export default function DistributionPage() {
  const { role } = useAuth();
  const [distributions, setDistributions] = useState<DistributionDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [receiveTarget, setReceiveTarget] = useState<DistributionDetail | null>(null);
  const canCreateDispatch = role === 'owner' || role === 'production_manager';
  const canReviewDiscrepancy = role === 'owner' || role === 'production_manager';

  async function fetchDistributions() {
    try {
      setLoading(true);
      setError('');
      const params = statusFilter !== 'all' ? { status: statusFilter } : undefined;
      const data = await distributionApi.list(params);
      setDistributions(data);
    } catch {
      setError('Failed to load distributions');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchDistributions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const handleAdvanceStatus = async (dist: DistributionDetail) => {
    if (dist.status === 'in_transit') {
      setReceiveTarget(dist);
      return;
    }

    const next: Record<string, string> = {
      dispatched: 'in_transit',
      received: 'confirmed',
    };
    const nextStatus = next[dist.status];
    if (!nextStatus) return;

    try {
      setError('');
      await distributionApi.updateStatus(dist.id, nextStatus);
      await fetchDistributions();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to update status';
      setError(typeof msg === 'string' ? msg : 'Failed to update status');
    }
  };

  const handleApproveDiscrepancy = async (dist: DistributionDetail) => {
    const reviewNote = window.prompt('Approval note (optional):') ?? undefined;
    try {
      setError('');
      await distributionApi.approveDiscrepancy(dist.id, { review_note: reviewNote });
      await fetchDistributions();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to approve discrepancy';
      setError(typeof msg === 'string' ? msg : 'Failed to approve discrepancy');
    }
  };

  const handleRejectDiscrepancy = async (dist: DistributionDetail) => {
    const reviewNote = window.prompt('Rejection note (optional):') ?? undefined;
    try {
      setError('');
      await distributionApi.rejectDiscrepancy(dist.id, { review_note: reviewNote });
      await fetchDistributions();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to reject discrepancy';
      setError(typeof msg === 'string' ? msg : 'Failed to reject discrepancy');
    }
  };

  const handleDriverCountConfirm = async (dist: DistributionDetail) => {
    try {
      setError('');
      await distributionApi.confirmDriverCount(dist.id);
      await fetchDistributions();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to confirm loaded counts';
      setError(typeof msg === 'string' ? msg : 'Failed to confirm loaded counts');
    }
  };

  const handleSaved = () => {
    setShowCreateModal(false);
    setReceiveTarget(null);
    fetchDistributions();
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Distribution</h1>
          <p className="text-gray-500 mt-1">Dispatch products to stores and track delivery</p>
        </div>
        {canCreateDispatch && (
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
          >
            <Plus size={18} />
            New Dispatch
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm mb-4">
          {error}
          <button type="button" onClick={() => setError('')} className="float-right font-bold">&times;</button>
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
          <div className="p-8 text-center text-gray-400">Loading distributions...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[750px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Store</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Delivery Staff</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Dispatch Date</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Items</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {distributions.map((d) => (
                  <tr key={d.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">{d.store_name ?? '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-700">{d.delivery_person_name ?? '—'}</td>
                    <td className="px-6 py-4 text-sm text-gray-600 whitespace-nowrap">{formatDate(d.dispatch_date)}</td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {d.items.map((it) => (
                          <div
                            key={it.id}
                            className={`px-2 py-1 rounded text-xs ${
                              it.discrepancy_qty !== 0 ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-blue-700'
                            }`}
                          >
                            <span>
                              {it.product_name ?? 'Product'}: {it.quantity_sent}
                              {it.quantity_received != null && (
                                <span className="text-green-600 ml-1">({it.quantity_received} rcvd)</span>
                              )}
                              {it.discrepancy_qty !== 0 && (
                                <span className="ml-1 font-medium">(diff {it.discrepancy_qty})</span>
                              )}
                            </span>
                            {it.discrepancy_qty !== 0 && (
                              <div className="mt-0.5 text-[11px] leading-4 text-amber-800">
                                Reason: {it.discrepancy_reason ?? '—'}
                                {it.discrepancy_note ? ` | Note: ${it.discrepancy_note}` : ''}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1">
                        <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_STYLES[d.status] ?? 'bg-gray-100 text-gray-600'}`}>
                          {STATUS_LABELS[d.status] ?? d.status}
                        </span>
                        {d.has_discrepancy && (
                          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${DISCREPANCY_STYLES[d.discrepancy_status] ?? 'bg-gray-100 text-gray-600'}`}>
                            <AlertTriangle size={12} />
                            {DISCREPANCY_LABELS[d.discrepancy_status] ?? d.discrepancy_status}
                          </span>
                        )}
                        {d.status === 'in_transit' && (
                          <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${
                            d.driver_count_confirmed ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'
                          }`}>
                            {d.driver_count_confirmed ? 'Driver Count Confirmed' : 'Driver Count Pending'}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      {!d.is_locked && d.status === 'dispatched' && (role === 'owner' || role === 'production_manager') && (
                        <button
                          type="button"
                          onClick={() => handleAdvanceStatus(d)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors"
                          title="Advance to next status"
                        >
                          <Truck size={14} /> {role === 'delivery_staff' ? 'Start Delivery' : 'Mark In Transit'}
                          <ArrowRight size={12} />
                        </button>
                      )}
                      {!d.is_locked && d.status === 'in_transit' && role === 'delivery_staff' && !d.driver_count_confirmed && (
                        <button
                          type="button"
                          onClick={() => handleDriverCountConfirm(d)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-50 text-green-700 hover:bg-green-100 transition-colors"
                          title="Confirm loaded counts"
                        >
                          <CheckCircle2 size={14} /> Confirm Loaded Qty
                        </button>
                      )}
                      {!d.is_locked && d.status === 'in_transit' && role === 'delivery_staff' && d.driver_count_confirmed && (
                        <span className="text-xs text-gray-500">Counts confirmed. Awaiting store receipt</span>
                      )}
                      {!d.is_locked && d.status === 'in_transit' && d.driver_count_confirmed && (role === 'owner' || role === 'store_manager') && (
                        <button
                          type="button"
                          onClick={() => handleAdvanceStatus(d)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors"
                          title="Record received quantities"
                        >
                          <PackageCheck size={14} /> Receive
                          <ArrowRight size={12} />
                        </button>
                      )}
                      {!d.is_locked && d.status === 'received' && d.has_discrepancy && d.discrepancy_status === 'rejected' && (role === 'owner' || role === 'store_manager') && (
                        <button
                          type="button"
                          onClick={() => setReceiveTarget(d)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors"
                          title="Re-enter received quantities after rejection"
                        >
                          <PackageCheck size={14} /> Re-Receive
                        </button>
                      )}
                      {!d.is_locked && d.status === 'received' && d.has_discrepancy && d.discrepancy_status === 'pending_approval' && canReviewDiscrepancy && (
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => handleApproveDiscrepancy(d)}
                            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-50 text-green-700 hover:bg-green-100 transition-colors"
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRejectDiscrepancy(d)}
                            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-50 text-red-700 hover:bg-red-100 transition-colors"
                          >
                            Reject
                          </button>
                        </div>
                      )}
                      {!d.is_locked && d.status === 'received' && (!d.has_discrepancy || d.discrepancy_status === 'approved') && canReviewDiscrepancy && (
                        <button
                          type="button"
                          onClick={() => handleAdvanceStatus(d)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors"
                          title="Advance to next status"
                        >
                          <CheckCircle2 size={14} /> Confirm
                          <ArrowRight size={12} />
                        </button>
                      )}
                      {d.is_locked && (
                        <span className="text-xs text-gray-400">Locked</span>
                      )}
                    </td>
                  </tr>
                ))}
                {distributions.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-gray-400">
                      <div className="flex flex-col items-center gap-2">
                        <Truck className="text-gray-300" size={40} strokeWidth={1.5} />
                        <p>No distributions found. Create a dispatch to get started.</p>
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
        <CreateDistributionModal
          onClose={() => setShowCreateModal(false)}
          onSaved={handleSaved}
        />
      )}

      {receiveTarget && (
        <ReceiveModal
          distribution={receiveTarget}
          onClose={() => setReceiveTarget(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function CreateDistributionModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<ProductDetail[]>([]);
  const [deliveryStaff, setDeliveryStaff] = useState<User[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  const [storeId, setStoreId] = useState('');
  const [deliveryPersonId, setDeliveryPersonId] = useState('');
  const [dispatchDate, setDispatchDate] = useState(new Date().toISOString().slice(0, 10));
  const [lines, setLines] = useState<DistItemPayload[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      storesApi.list({ is_active: true }),
      productsApi.list({ is_active: true }),
      usersApi.list({ role: 'delivery_staff', is_active: true }),
    ])
      .then(([s, p, staff]) => {
        setStores(s);
        setProducts(p);
        setDeliveryStaff(staff);
        if (s.length > 0) setStoreId(s[0].id);
        if (staff.length > 0) setDeliveryPersonId(staff[0].id);
      })
      .catch(() => setError('Failed to load data'))
      .finally(() => setLoadingData(false));
  }, []);

  const usedProductIds = new Set(lines.map((l) => l.product_id));

  const addLine = () => {
    const available = products.filter((p) => !usedProductIds.has(p.id));
    if (available.length === 0) return;
    setLines((prev) => [...prev, { product_id: available[0].id, quantity_sent: 1 }]);
  };

  const removeLine = (idx: number) => {
    setLines((prev) => prev.filter((_, i) => i !== idx));
  };

  const updateLine = (idx: number, field: keyof DistItemPayload, value: string) => {
    setLines((prev) =>
      prev.map((line, i) => {
        if (i !== idx) return line;
        if (field === 'product_id') return { ...line, product_id: value };
        return { ...line, quantity_sent: Number(value) || 0 };
      })
    );
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    if (lines.length === 0) {
      setError('Add at least one product');
      setSaving(false);
      return;
    }
    for (const line of lines) {
      if (line.quantity_sent < 1) {
        setError('All quantities must be at least 1');
        setSaving(false);
        return;
      }
    }

    try {
      if (!deliveryPersonId) {
        setError('Select a delivery staff member');
        setSaving(false);
        return;
      }

      const payload: CreateDistributionPayload = {
        store_id: storeId,
        dispatch_date: dispatchDate,
        delivery_person_id: deliveryPersonId,
        items: lines,
      };
      await distributionApi.create(payload);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to create dispatch';
      setError(typeof msg === 'string' ? msg : 'Failed to create dispatch');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">New Dispatch</h2>
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
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Destination Store</label>
                  <select
                    value={storeId}
                    onChange={(e) => setStoreId(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  >
                    {stores.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Delivery Staff</label>
                  <select
                    value={deliveryPersonId}
                    onChange={(e) => setDeliveryPersonId(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  >
                    {deliveryStaff.map((staff) => (
                      <option key={staff.id} value={staff.id}>{staff.full_name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Dispatch Date</label>
                  <input
                    type="date"
                    value={dispatchDate}
                    onChange={(e) => setDispatchDate(e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-700">Products to dispatch</label>
                  <button
                    type="button"
                    onClick={addLine}
                    disabled={products.filter((p) => !usedProductIds.has(p.id)).length === 0}
                    className="flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Plus size={14} /> Add product
                  </button>
                </div>

                {lines.length === 0 ? (
                  <p className="text-sm text-gray-400 border border-dashed border-gray-300 rounded-lg p-4 text-center">
                    No products added. Click "Add product" above.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {lines.map((line, idx) => {
                      const availableForRow = products.filter(
                        (p) => p.id === line.product_id || !usedProductIds.has(p.id)
                      );
                      return (
                        <div key={idx} className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg border border-gray-200">
                          <select
                            value={line.product_id}
                            onChange={(e) => updateLine(idx, 'product_id', e.target.value)}
                            className="flex-1 min-w-0 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 outline-none bg-white"
                          >
                            {availableForRow.map((p) => (
                              <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>
                            ))}
                          </select>
                          <input
                            type="number"
                            value={line.quantity_sent || ''}
                            onChange={(e) => updateLine(idx, 'quantity_sent', e.target.value)}
                            placeholder="Qty"
                            min={1}
                            step={1}
                            required
                            className="w-20 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 outline-none text-right tabular-nums"
                          />
                          <button
                            type="button"
                            onClick={() => removeLine(idx)}
                            className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
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
              {saving ? 'Dispatching...' : 'Dispatch'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ReceiveModal({
  distribution,
  onClose,
  onSaved,
}: {
  distribution: DistributionDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [receivedQtys, setReceivedQtys] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const it of distribution.items) {
      m[it.id] = it.quantity_received != null ? String(it.quantity_received) : String(it.quantity_sent);
    }
    return m;
  });
  const [discrepancyReasons, setDiscrepancyReasons] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const it of distribution.items) {
      m[it.id] = it.discrepancy_reason ?? '';
    }
    return m;
  });
  const [discrepancyNotes, setDiscrepancyNotes] = useState<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    for (const it of distribution.items) {
      m[it.id] = it.discrepancy_note ?? '';
    }
    return m;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    const items: ReceiveItemPayload[] = distribution.items.map((it) => {
      const received = Number(receivedQtys[it.id]) || 0;
      const discrepancyQty = it.quantity_sent - received;
      return {
        item_id: it.id,
        quantity_received: received,
        discrepancy_reason: discrepancyQty !== 0 ? discrepancyReasons[it.id]?.trim() || undefined : undefined,
        discrepancy_note: discrepancyQty !== 0 ? discrepancyNotes[it.id]?.trim() || undefined : undefined,
      };
    });

    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (item.quantity_received < 0) {
        setError('Received quantities cannot be negative');
        setSaving(false);
        return;
      }
      const sentQty = distribution.items[i].quantity_sent;
      if (sentQty !== item.quantity_received && !item.discrepancy_reason) {
        setError('Discrepancy reason is required when sent and received differ');
        setSaving(false);
        return;
      }
    }

    try {
      await distributionApi.receiveItems(distribution.id, items);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to record receipt';
      setError(typeof msg === 'string' ? msg : 'Failed to record receipt');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Receive Shipment</h2>
          <button type="button" onClick={onClose} className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

          <p className="text-sm text-gray-600">
            Shipment to <span className="font-medium text-gray-900">{distribution.store_name}</span>
            {' '}on {formatDate(distribution.dispatch_date)}
          </p>

          <div className="space-y-3">
            {distribution.items.map((it) => {
              const receivedValue = Number(receivedQtys[it.id]) || 0;
              const discrepancyQty = it.quantity_sent - receivedValue;
              const hasDiscrepancy = discrepancyQty !== 0;
              return (
                <div key={it.id} className="p-3 bg-gray-50 rounded-lg border border-gray-200 space-y-2">
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900">{it.product_name ?? 'Product'}</p>
                      <p className="text-xs text-gray-500">
                        Sent: {it.quantity_sent}
                        {hasDiscrepancy && (
                          <span className="ml-2 text-amber-700 font-medium">
                            Difference: {discrepancyQty}
                          </span>
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <label className="text-xs text-gray-500">Received:</label>
                      <input
                        type="number"
                        value={receivedQtys[it.id] ?? ''}
                        onChange={(e) =>
                          setReceivedQtys((prev) => ({ ...prev, [it.id]: e.target.value }))
                        }
                        min={0}
                        step={1}
                        required
                        className="w-20 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 outline-none text-right tabular-nums"
                      />
                    </div>
                  </div>
                  {hasDiscrepancy && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <input
                        type="text"
                        value={discrepancyReasons[it.id] ?? ''}
                        onChange={(e) =>
                          setDiscrepancyReasons((prev) => ({ ...prev, [it.id]: e.target.value }))
                        }
                        required
                        placeholder="Reason (required)"
                        className="px-2 py-1.5 border border-amber-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 outline-none"
                      />
                      <input
                        type="text"
                        value={discrepancyNotes[it.id] ?? ''}
                        onChange={(e) =>
                          setDiscrepancyNotes((prev) => ({ ...prev, [it.id]: e.target.value }))
                        }
                        placeholder="Note (optional)"
                        className="px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 outline-none"
                      />
                    </div>
                  )}
                </div>
              );
            })}
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
              {saving ? 'Saving...' : 'Confirm Receipt'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
