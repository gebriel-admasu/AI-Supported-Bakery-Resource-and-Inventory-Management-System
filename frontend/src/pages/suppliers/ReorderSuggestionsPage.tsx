import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Plus,
  RefreshCw,
  ShoppingCart,
} from 'lucide-react';

import type {
  Ingredient,
  ReorderSuggestionItem,
  Supplier,
} from '../../types';
import { reorderApi, suppliersApi } from '../../api/suppliers';
import { ingredientsApi } from '../../api/ingredients';
import CreatePurchaseOrderModal from './CreatePurchaseOrderModal';

const etbFormatter = new Intl.NumberFormat('en-ET', {
  style: 'currency',
  currency: 'ETB',
  minimumFractionDigits: 2,
});

const qtyFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 3,
});

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString();
}

interface PrefillContext {
  supplierId: string;
  ingredientId: string;
  quantity: number;
  unitCost?: number | null;
}

export default function ReorderSuggestionsPage() {
  const [items, setItems] = useState<ReorderSuggestionItem[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [prefill, setPrefill] = useState<PrefillContext | null>(null);

  async function fetchSuggestions() {
    try {
      setLoading(true);
      setError('');
      const data = await reorderApi.list();
      setItems(data.items);
    } catch {
      setError('Failed to load reorder suggestions');
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
      // non-fatal — user can still browse the list
    }
  }

  useEffect(() => {
    void fetchSuggestions();
    void fetchLookups();
  }, []);

  const handleOrderClick = (
    item: ReorderSuggestionItem,
    supplierId: string,
    lastUnitCost: number | null | undefined
  ) => {
    setPrefill({
      supplierId,
      ingredientId: item.ingredient_id,
      quantity: item.suggested_qty,
      unitCost: lastUnitCost ?? null,
    });
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reorder Suggestions</h1>
          <p className="text-gray-500 mt-1 max-w-2xl">
            Ingredients below their minimum stock threshold are listed here, ranked by shortage.
            Each row shows your best supplier options based on previous orders and lead time.
          </p>
        </div>
        <button
          type="button"
          onClick={fetchSuggestions}
          disabled={loading}
          className="flex items-center justify-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2.5 rounded-lg font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors shrink-0"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
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

      {loading ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400">
          Loading suggestions...
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <CheckCircle2 size={48} strokeWidth={1.5} className="text-green-300 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-gray-700">All stock levels healthy</h2>
          <p className="text-sm text-gray-500 mt-1">
            No ingredients are below their minimum threshold. Nothing to reorder right now.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <SuggestionCard
              key={item.ingredient_id}
              item={item}
              onOrder={(supplierId, lastUnitCost) =>
                handleOrderClick(item, supplierId, lastUnitCost)
              }
            />
          ))}
        </div>
      )}

      {prefill && (
        <CreatePurchaseOrderModal
          suppliers={suppliers}
          ingredients={ingredients}
          defaults={{
            supplier_id: prefill.supplierId,
            ingredient_id: prefill.ingredientId,
            quantity: prefill.quantity,
            unit_cost: prefill.unitCost ?? undefined,
          }}
          onClose={() => setPrefill(null)}
          onCreated={() => {
            setPrefill(null);
            void fetchSuggestions();
          }}
        />
      )}
    </div>
  );
}

function SuggestionCard({
  item,
  onOrder,
}: {
  item: ReorderSuggestionItem;
  onOrder: (supplierId: string, lastUnitCost: number | null | undefined) => void;
}) {
  const ratio =
    item.min_threshold > 0
      ? Math.min(100, (item.current_qty / item.min_threshold) * 100)
      : 0;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 p-2 rounded-lg bg-amber-50 text-amber-600">
            <AlertTriangle size={18} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-900">{item.ingredient_name}</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Currently{' '}
              <span className="font-medium text-gray-700 tabular-nums">
                {qtyFormatter.format(item.current_qty)} {item.ingredient_unit}
              </span>{' '}
              · minimum{' '}
              <span className="font-medium text-gray-700 tabular-nums">
                {qtyFormatter.format(item.min_threshold)} {item.ingredient_unit}
              </span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-6 text-sm">
          <div className="text-right">
            <div className="text-xs text-gray-500 uppercase tracking-wider">Shortage</div>
            <div className="font-semibold text-amber-700 tabular-nums">
              {qtyFormatter.format(item.shortage_qty)} {item.ingredient_unit}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-500 uppercase tracking-wider">Suggested</div>
            <div className="font-semibold text-primary-700 tabular-nums">
              {qtyFormatter.format(item.suggested_qty)} {item.ingredient_unit}
            </div>
          </div>
        </div>
      </div>

      <div className="h-1.5 bg-gray-100">
        <div
          className="h-full bg-amber-400 transition-all"
          style={{ width: `${ratio}%` }}
          aria-label={`Stock at ${ratio.toFixed(0)}% of minimum threshold`}
        />
      </div>

      <div className="px-6 py-4">
        {item.suppliers.length === 0 ? (
          <div className="text-sm text-gray-500 italic">
            No active suppliers configured. Add a supplier to enable ordering for this ingredient.
          </div>
        ) : (
          <div>
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Supplier options
            </div>
            <div className="divide-y divide-gray-100 border border-gray-100 rounded-lg">
              {item.suppliers.map((sup, idx) => (
                <div
                  key={sup.supplier_id}
                  className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-4 py-3"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-semibold ${
                        idx === 0
                          ? 'bg-primary-100 text-primary-700'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {idx + 1}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">
                        {sup.supplier_name}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-gray-500 mt-0.5">
                        <span className="inline-flex items-center gap-1">
                          <Clock size={12} />
                          {sup.lead_time_days != null
                            ? `${sup.lead_time_days}d lead time`
                            : 'lead time —'}
                        </span>
                        {sup.has_history ? (
                          <>
                            <span>
                              last cost{' '}
                              <span className="text-gray-700 tabular-nums">
                                {sup.last_unit_cost != null
                                  ? etbFormatter.format(sup.last_unit_cost)
                                  : '—'}
                              </span>
                            </span>
                            <span>last order {formatDate(sup.last_order_date)}</span>
                          </>
                        ) : (
                          <span className="text-gray-400 italic">no history</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onOrder(sup.supplier_id, sup.last_unit_cost)}
                    className="inline-flex items-center justify-center gap-1.5 bg-primary-50 text-primary-700 hover:bg-primary-100 border border-primary-100 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors shrink-0"
                  >
                    <Plus size={14} />
                    Order from {sup.supplier_name}
                  </button>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-2 inline-flex items-center gap-1">
              <ShoppingCart size={12} />
              Suppliers ranked by previous order history, then lead time.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
