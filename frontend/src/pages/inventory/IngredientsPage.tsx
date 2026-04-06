import { useState, useEffect, type FormEvent } from 'react';
import type { Ingredient } from '../../types';
import { ingredientsApi, type CreateIngredientPayload, type UpdateIngredientPayload } from '../../api/ingredients';
import { Plus, Pencil, ToggleLeft, ToggleRight, Search, Package, X } from 'lucide-react';

const COMMON_UNITS = ['kg', 'g', 'L', 'mL', 'pcs', 'dozen', 'bag'] as const;

const etbFormatter = new Intl.NumberFormat('en-ET', {
  style: 'currency',
  currency: 'ETB',
  minimumFractionDigits: 2,
});

function formatExpiry(value?: string): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString();
}

export default function IngredientsPage() {
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingIngredient, setEditingIngredient] = useState<Ingredient | null>(null);

  async function fetchIngredients() {
    try {
      setLoading(true);
      setError('');
      const data = await ingredientsApi.list({
        search: search.trim() || undefined,
      });
      setIngredients(data);
    } catch {
      setError('Failed to load ingredients');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchIngredients();
    // search is the only dependency we need for refetching the list
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const handleToggleStatus = async (ingredient: Ingredient) => {
    try {
      if (ingredient.is_active) {
        await ingredientsApi.deactivate(ingredient.id);
      } else {
        await ingredientsApi.update(ingredient.id, { is_active: true });
      }
      await fetchIngredients();
    } catch {
      setError(`Failed to ${ingredient.is_active ? 'deactivate' : 'reactivate'} ingredient`);
    }
  };

  const openCreate = () => {
    setEditingIngredient(null);
    setShowModal(true);
  };

  const openEdit = (ingredient: Ingredient) => {
    setEditingIngredient(ingredient);
    setShowModal(true);
  };

  const handleSaved = () => {
    setShowModal(false);
    setEditingIngredient(null);
    fetchIngredients();
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ingredients</h1>
          <p className="text-gray-500 mt-1">Manage raw materials for production</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
        >
          <Plus size={18} />
          Add Ingredient
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

      <div className="mb-4">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name..."
            className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm bg-white"
            aria-label="Search ingredients by name"
          />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading ingredients...</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Name
                </th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Unit
                </th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Unit Cost
                </th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Expiry Date
                </th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {ingredients.map((row) => (
                <tr key={row.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <p className="text-sm font-medium text-gray-900">{row.name}</p>
                    {row.description && (
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{row.description}</p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">{row.unit}</td>
                  <td className="px-6 py-4 text-sm text-gray-900 tabular-nums">
                    {etbFormatter.format(row.unit_cost)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">{formatExpiry(row.expiry_date)}</td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${
                        row.is_active ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                      }`}
                    >
                      {row.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => openEdit(row)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                        title="Edit ingredient"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleStatus(row)}
                        className={`p-1.5 rounded-lg transition-colors ${
                          row.is_active
                            ? 'text-gray-400 hover:text-amber-600 hover:bg-amber-50'
                            : 'text-gray-400 hover:text-green-600 hover:bg-green-50'
                        }`}
                        title={row.is_active ? 'Deactivate' : 'Activate'}
                      >
                        {row.is_active ? <ToggleLeft size={16} /> : <ToggleRight size={16} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {ingredients.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-400">
                    <div className="flex flex-col items-center gap-2">
                      <Package className="text-gray-300" size={40} strokeWidth={1.5} />
                      <p>
                        {search.trim()
                          ? 'No ingredients match your search.'
                          : 'No ingredients yet. Add one to get started.'}
                      </p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <IngredientFormModal
          ingredient={editingIngredient}
          onClose={() => {
            setShowModal(false);
            setEditingIngredient(null);
          }}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function IngredientFormModal({
  ingredient,
  onClose,
  onSaved,
}: {
  ingredient: Ingredient | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!ingredient;
  const unitOptions =
    ingredient?.unit && !(COMMON_UNITS as readonly string[]).includes(ingredient.unit)
      ? [...COMMON_UNITS, ingredient.unit]
      : COMMON_UNITS;

  const [form, setForm] = useState({
    name: ingredient?.name ?? '',
    unit: ingredient?.unit ?? 'kg',
    unit_cost: ingredient != null ? String(ingredient.unit_cost) : '',
    expiry_date: ingredient?.expiry_date ? ingredient.expiry_date.slice(0, 10) : '',
    description: ingredient?.description ?? '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (field: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    const unitCostNum = Number(form.unit_cost);
    if (Number.isNaN(unitCostNum) || unitCostNum < 0) {
      setError('Unit cost must be a valid non-negative number');
      setSaving(false);
      return;
    }

    try {
      if (isEdit) {
        const payload: UpdateIngredientPayload = {
          name: form.name.trim(),
          unit: form.unit,
          unit_cost: unitCostNum,
          expiry_date: form.expiry_date ? form.expiry_date : null,
          description: form.description.trim() ? form.description.trim() : null,
        };
        await ingredientsApi.update(ingredient!.id, payload);
      } else {
        const payload: CreateIngredientPayload = {
          name: form.name.trim(),
          unit: form.unit,
          unit_cost: unitCostNum,
          expiry_date: form.expiry_date || undefined,
          description: form.description.trim() || undefined,
        };
        await ingredientsApi.create(payload);
      }
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to save ingredient';
      setError(typeof msg === 'string' ? msg : 'Failed to save ingredient');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Edit Ingredient' : 'Add Ingredient'}
          </h2>
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

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => handleChange('name', e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Unit</label>
            <select
              value={form.unit}
              onChange={(e) => handleChange('unit', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            >
              {unitOptions.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
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

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Expiry date <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="date"
              value={form.expiry_date}
              onChange={(e) => handleChange('expiry_date', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={form.description}
              onChange={(e) => handleChange('description', e.target.value)}
              rows={3}
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
              {saving ? 'Saving...' : isEdit ? 'Update Ingredient' : 'Create Ingredient'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
