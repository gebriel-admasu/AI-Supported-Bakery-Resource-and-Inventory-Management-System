import { useState, useMemo, type FormEvent } from 'react';
import { X } from 'lucide-react';

import type { Ingredient, Supplier } from '../../types';
import {
  purchaseOrdersApi,
  type CreatePurchaseOrderPayload,
} from '../../api/suppliers';

const etbFormatter = new Intl.NumberFormat('en-ET', {
  style: 'currency',
  currency: 'ETB',
  minimumFractionDigits: 2,
});

export interface CreatePurchaseOrderModalProps {
  suppliers: Supplier[];
  ingredients: Ingredient[];
  onClose: () => void;
  onCreated: () => void;
  /**
   * Optional pre-filled values, used e.g. when launching from a reorder
   * suggestion. The user can still edit any field before submitting.
   */
  defaults?: {
    supplier_id?: string;
    ingredient_id?: string;
    quantity?: number;
    unit_cost?: number;
  };
}

export default function CreatePurchaseOrderModal({
  suppliers,
  ingredients,
  onClose,
  onCreated,
  defaults,
}: CreatePurchaseOrderModalProps) {
  const [form, setForm] = useState({
    supplier_id: defaults?.supplier_id ?? '',
    ingredient_id: defaults?.ingredient_id ?? '',
    quantity: defaults?.quantity != null ? String(defaults.quantity) : '',
    unit_cost: defaults?.unit_cost != null ? String(defaults.unit_cost) : '',
    expected_delivery: '',
    notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const total = useMemo(() => {
    const q = Number(form.quantity);
    const u = Number(form.unit_cost);
    if (Number.isNaN(q) || Number.isNaN(u) || q <= 0 || u < 0) return null;
    return q * u;
  }, [form.quantity, form.unit_cost]);

  const handleChange = (field: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    if (!form.supplier_id || !form.ingredient_id) {
      setError('Please pick both a supplier and an ingredient.');
      setSaving(false);
      return;
    }
    const qty = Number(form.quantity);
    const cost = Number(form.unit_cost);
    if (Number.isNaN(qty) || qty <= 0) {
      setError('Quantity must be greater than zero.');
      setSaving(false);
      return;
    }
    if (Number.isNaN(cost) || cost < 0) {
      setError('Unit cost must be a non-negative number.');
      setSaving(false);
      return;
    }

    const payload: CreatePurchaseOrderPayload = {
      supplier_id: form.supplier_id,
      ingredient_id: form.ingredient_id,
      quantity: qty,
      unit_cost: cost,
      expected_delivery: form.expected_delivery || undefined,
      notes: form.notes.trim() || undefined,
    };

    try {
      await purchaseOrdersApi.create(payload);
      onCreated();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to create purchase order';
      setError(typeof msg === 'string' ? msg : 'Failed to create purchase order');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Create Purchase Order</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Supplier</label>
              <select
                value={form.supplier_id}
                onChange={(e) => handleChange('supplier_id', e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              >
                <option value="">— pick a supplier —</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.lead_time_days != null ? ` (${s.lead_time_days}d lead)` : ''}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Ingredient</label>
              <select
                value={form.ingredient_id}
                onChange={(e) => handleChange('ingredient_id', e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              >
                <option value="">— pick an ingredient —</option>
                {ingredients.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name} ({i.unit})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Quantity</label>
              <input
                type="number"
                value={form.quantity}
                onChange={(e) => handleChange('quantity', e.target.value)}
                required
                min={0}
                step="0.001"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Unit cost (ETB)</label>
              <input
                type="number"
                value={form.unit_cost}
                onChange={(e) => handleChange('unit_cost', e.target.value)}
                required
                min={0}
                step="0.01"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
          </div>

          {total !== null && (
            <div className="text-sm text-gray-700 bg-gray-50 rounded-lg px-3 py-2 flex items-center justify-between">
              <span className="text-gray-500">Order total</span>
              <span className="font-semibold tabular-nums">{etbFormatter.format(total)}</span>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Expected delivery <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="date"
              value={form.expected_delivery}
              onChange={(e) => handleChange('expected_delivery', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              Will be auto-filled at send time using the supplier's lead time if left blank.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Notes <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={form.notes}
              onChange={(e) => handleChange('notes', e.target.value)}
              rows={2}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm resize-y"
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
              {saving ? 'Creating...' : 'Create Purchase Order'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
