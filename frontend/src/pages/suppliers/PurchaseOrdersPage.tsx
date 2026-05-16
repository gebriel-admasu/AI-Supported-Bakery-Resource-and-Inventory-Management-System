import { useState, useEffect, type FormEvent } from 'react';
import {
  CheckCircle2,
  ClipboardList,
  Plus,
  Send,
  PackageCheck,
  XCircle,
  X,
} from 'lucide-react';

import type {
  Ingredient,
  PurchaseOrder,
  PurchaseOrderStatus,
  Supplier,
} from '../../types';
import { purchaseOrdersApi, suppliersApi } from '../../api/suppliers';
import { ingredientsApi } from '../../api/ingredients';
import { useAuth } from '../../context/AuthContext';
import CreatePurchaseOrderModal from './CreatePurchaseOrderModal';

const etbFormatter = new Intl.NumberFormat('en-ET', {
  style: 'currency',
  currency: 'ETB',
  minimumFractionDigits: 2,
});

const qtyFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 3,
});

type TabKey = 'all' | PurchaseOrderStatus;

interface Tab {
  key: TabKey;
  label: string;
}

const TABS: Tab[] = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'sent', label: 'Sent' },
  { key: 'received', label: 'Received' },
  { key: 'cancelled', label: 'Cancelled' },
];

const STATUS_STYLES: Record<PurchaseOrderStatus, string> = {
  pending: 'bg-amber-50 text-amber-700',
  approved: 'bg-blue-50 text-blue-700',
  sent: 'bg-indigo-50 text-indigo-700',
  received: 'bg-green-50 text-green-700',
  cancelled: 'bg-gray-100 text-gray-600',
};

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString();
}

type LifecycleAction = 'approve' | 'send' | 'receive' | 'cancel';

interface ActionContext {
  po: PurchaseOrder;
  action: LifecycleAction;
}

export default function PurchaseOrdersPage() {
  const { role, user } = useAuth();

  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<TabKey>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [actionCtx, setActionCtx] = useState<ActionContext | null>(null);

  async function fetchOrders(tab: TabKey) {
    try {
      setLoading(true);
      setError('');
      const data = await purchaseOrdersApi.list(
        tab === 'all' ? undefined : { status: tab }
      );
      setOrders(data);
    } catch {
      setError('Failed to load purchase orders');
    } finally {
      setLoading(false);
    }
  }

  async function fetchLookups() {
    try {
      const [s, i] = await Promise.all([
        suppliersApi.list({ is_active: true }),
        ingredientsApi.list({ is_active: true }),
      ]);
      setSuppliers(s);
      setIngredients(i);
    } catch {
      // non-fatal — orders can still be listed/managed
    }
  }

  useEffect(() => {
    void fetchLookups();
  }, []);

  useEffect(() => {
    void fetchOrders(activeTab);
  }, [activeTab]);

  const canApprove = role === 'owner';
  const canCancel = (po: PurchaseOrder): boolean => {
    if (role === 'owner') return true;
    if (po.created_by === user?.id && po.status === 'pending') return true;
    return false;
  };

  const refreshAfterAction = async () => {
    setActionCtx(null);
    await fetchOrders(activeTab);
  };

  const refreshAfterCreate = async () => {
    setShowCreate(false);
    if (activeTab !== 'all' && activeTab !== 'pending') {
      setActiveTab('pending');
    } else {
      await fetchOrders(activeTab);
    }
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Purchase Orders</h1>
          <p className="text-gray-500 mt-1">
            Track and progress purchase orders through approval, dispatch and receipt
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
        >
          <Plus size={18} />
          Create Purchase Order
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

      <div className="mb-4 flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`px-3.5 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              activeTab === tab.key
                ? 'bg-primary-600 text-white border-primary-600'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading purchase orders...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Supplier
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Ingredient
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Quantity
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Unit Cost
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Total
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Order Date
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Expected
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {orders.map((po) => (
                  <tr key={po.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {po.supplier_name || '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {po.ingredient_name || '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900 text-right tabular-nums">
                      {qtyFormatter.format(po.quantity)}
                      {po.ingredient_unit && (
                        <span className="text-gray-400 ml-1">{po.ingredient_unit}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700 text-right tabular-nums">
                      {etbFormatter.format(po.unit_cost)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900 text-right tabular-nums font-medium">
                      {etbFormatter.format(po.total_cost)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDate(po.order_date)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDate(po.expected_delivery)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium capitalize ${
                          STATUS_STYLES[po.status]
                        }`}
                      >
                        {po.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <PoRowActions
                        po={po}
                        canApprove={canApprove}
                        canCancel={canCancel(po)}
                        onAction={(action) => setActionCtx({ po, action })}
                      />
                    </td>
                  </tr>
                ))}
                {orders.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-6 py-12 text-center text-gray-400">
                      <div className="flex flex-col items-center gap-2">
                        <ClipboardList className="text-gray-300" size={40} strokeWidth={1.5} />
                        <p>
                          {activeTab === 'all'
                            ? 'No purchase orders yet. Create one to get started.'
                            : `No ${activeTab} purchase orders.`}
                        </p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreate && (
        <CreatePurchaseOrderModal
          suppliers={suppliers}
          ingredients={ingredients}
          onClose={() => setShowCreate(false)}
          onCreated={refreshAfterCreate}
        />
      )}

      {actionCtx && (
        <PurchaseOrderActionModal
          ctx={actionCtx}
          onClose={() => setActionCtx(null)}
          onCompleted={refreshAfterAction}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Row action buttons
// ---------------------------------------------------------------------------

function PoRowActions({
  po,
  canApprove,
  canCancel,
  onAction,
}: {
  po: PurchaseOrder;
  canApprove: boolean;
  canCancel: boolean;
  onAction: (action: LifecycleAction) => void;
}) {
  const buttons: { action: LifecycleAction; label: string; icon: React.ReactNode; classes: string }[] =
    [];

  if (po.status === 'pending' && canApprove) {
    buttons.push({
      action: 'approve',
      label: 'Approve',
      icon: <CheckCircle2 size={14} />,
      classes:
        'text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-100',
    });
  }
  if (po.status === 'approved') {
    buttons.push({
      action: 'send',
      label: 'Send',
      icon: <Send size={14} />,
      classes:
        'text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-100',
    });
  }
  if (po.status === 'sent') {
    buttons.push({
      action: 'receive',
      label: 'Receive',
      icon: <PackageCheck size={14} />,
      classes:
        'text-green-700 bg-green-50 hover:bg-green-100 border border-green-100',
    });
  }
  if (
    canCancel &&
    po.status !== 'received' &&
    po.status !== 'cancelled'
  ) {
    buttons.push({
      action: 'cancel',
      label: 'Cancel',
      icon: <XCircle size={14} />,
      classes:
        'text-red-700 bg-red-50 hover:bg-red-100 border border-red-100',
    });
  }

  if (buttons.length === 0) {
    return <span className="text-xs text-gray-400">—</span>;
  }

  return (
    <div className="flex items-center justify-end gap-1.5">
      {buttons.map((b) => (
        <button
          key={b.action}
          type="button"
          onClick={() => onAction(b.action)}
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${b.classes}`}
        >
          {b.icon}
          {b.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Action confirmation modal (handles approve / send / receive / cancel)
// ---------------------------------------------------------------------------

const ACTION_META: Record<
  LifecycleAction,
  {
    title: string;
    description: string;
    submitLabel: string;
    fieldLabel: string;
    fieldPlaceholder: string;
    submitClasses: string;
  }
> = {
  approve: {
    title: 'Approve Purchase Order',
    description: 'Approving moves the PO from PENDING to APPROVED.',
    submitLabel: 'Approve',
    fieldLabel: 'Note (optional)',
    fieldPlaceholder: 'e.g. Approved within budget for Q4 restock.',
    submitClasses: 'bg-blue-600 hover:bg-blue-700',
  },
  send: {
    title: 'Send Purchase Order',
    description:
      'Sending records that the PO has been placed with the supplier. ' +
      "If you don't pick a date, expected delivery is computed from the supplier's lead time.",
    submitLabel: 'Send',
    fieldLabel: 'Note (optional)',
    fieldPlaceholder: 'e.g. Confirmed by phone with supplier.',
    submitClasses: 'bg-indigo-600 hover:bg-indigo-700',
  },
  receive: {
    title: 'Receive Purchase Order',
    description:
      'Receiving will mark the PO as RECEIVED and automatically credit the ordered quantity to production inventory.',
    submitLabel: 'Receive',
    fieldLabel: 'Note (optional)',
    fieldPlaceholder: 'e.g. All units received in good condition.',
    submitClasses: 'bg-green-600 hover:bg-green-700',
  },
  cancel: {
    title: 'Cancel Purchase Order',
    description:
      'Cancelling is permanent. No inventory will be credited and the PO cannot be reopened.',
    submitLabel: 'Cancel PO',
    fieldLabel: 'Reason (optional)',
    fieldPlaceholder: 'e.g. Supplier out of stock.',
    submitClasses: 'bg-red-600 hover:bg-red-700',
  },
};

function PurchaseOrderActionModal({
  ctx,
  onClose,
  onCompleted,
}: {
  ctx: ActionContext;
  onClose: () => void;
  onCompleted: () => void;
}) {
  const meta = ACTION_META[ctx.action];
  const [text, setText] = useState('');
  const [expectedDelivery, setExpectedDelivery] = useState('');
  const [actualDelivery, setActualDelivery] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      switch (ctx.action) {
        case 'approve':
          await purchaseOrdersApi.approve(ctx.po.id, {
            note: text.trim() || null,
          });
          break;
        case 'send':
          await purchaseOrdersApi.send(ctx.po.id, {
            expected_delivery: expectedDelivery || null,
            note: text.trim() || null,
          });
          break;
        case 'receive':
          await purchaseOrdersApi.receive(ctx.po.id, {
            actual_delivery: actualDelivery || null,
            note: text.trim() || null,
          });
          break;
        case 'cancel':
          await purchaseOrdersApi.cancel(ctx.po.id, {
            reason: text.trim() || null,
          });
          break;
      }
      onCompleted();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Action failed';
      setError(typeof msg === 'string' ? msg : 'Action failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">{meta.title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <p className="text-sm text-gray-600">{meta.description}</p>

          <div className="bg-gray-50 rounded-lg px-3 py-2 text-sm">
            <div className="font-medium text-gray-900">
              {ctx.po.supplier_name} — {ctx.po.ingredient_name}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {qtyFormatter.format(ctx.po.quantity)} {ctx.po.ingredient_unit ?? ''} ·{' '}
              {etbFormatter.format(ctx.po.total_cost)}
            </div>
          </div>

          {error && (
            <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
          )}

          {ctx.action === 'send' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Expected delivery <span className="text-gray-400 font-normal">(optional)</span>
              </label>
              <input
                type="date"
                value={expectedDelivery}
                onChange={(e) => setExpectedDelivery(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                Leave blank to auto-fill from supplier lead time.
              </p>
            </div>
          )}

          {ctx.action === 'receive' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Actual delivery date
              </label>
              <input
                type="date"
                value={actualDelivery}
                onChange={(e) => setActualDelivery(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{meta.fieldLabel}</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
              placeholder={meta.fieldPlaceholder}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm resize-y"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={submitting}
              className={`px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 transition-colors ${meta.submitClasses}`}
            >
              {submitting ? 'Working...' : meta.submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

