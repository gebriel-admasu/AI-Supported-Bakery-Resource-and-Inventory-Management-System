import { useState, useEffect, type FormEvent } from 'react';
import type { Ingredient } from '../../types';
import { ingredientsApi } from '../../api/ingredients';
import {
  recipesApi,
  type RecipeDetail,
  type CreateRecipePayload,
  type UpdateRecipePayload,
} from '../../api/recipes';
import {
  Plus,
  Pencil,
  ToggleLeft,
  ToggleRight,
  Search,
  ChefHat,
  X,
  Trash2,
} from 'lucide-react';

type IngredientLineForm = {
  ingredient_id: string;
  quantity_input: string;
};

const etbFormatter = new Intl.NumberFormat('en-ET', {
  style: 'currency',
  currency: 'ETB',
  minimumFractionDigits: 2,
});

export default function RecipesPage() {
  const [recipes, setRecipes] = useState<RecipeDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingRecipe, setEditingRecipe] = useState<RecipeDetail | null>(null);

  async function fetchRecipes() {
    try {
      setLoading(true);
      setError('');
      const data = await recipesApi.list({ search: search.trim() || undefined });
      setRecipes(data);
    } catch {
      setError('Failed to load recipes');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchRecipes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const handleToggleStatus = async (recipe: RecipeDetail) => {
    try {
      if (recipe.is_active) {
        await recipesApi.deactivate(recipe.id);
      } else {
        await recipesApi.update(recipe.id, { is_active: true });
      }
      await fetchRecipes();
    } catch {
      setError(`Failed to ${recipe.is_active ? 'deactivate' : 'reactivate'} recipe`);
    }
  };

  const openCreate = () => {
    setEditingRecipe(null);
    setShowModal(true);
  };

  const openEdit = (recipe: RecipeDetail) => {
    setEditingRecipe(recipe);
    setShowModal(true);
  };

  const handleSaved = () => {
    setShowModal(false);
    setEditingRecipe(null);
    fetchRecipes();
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Recipes</h1>
          <p className="text-gray-500 mt-1">Manage production recipes with ingredient lists and versioning</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
        >
          <Plus size={18} />
          New Recipe
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
            placeholder="Search recipes by name..."
            className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm bg-white"
          />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading recipes...</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Version</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Yield</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Cost/Unit</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Ingredients</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {recipes.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <p className="text-sm font-medium text-gray-900">{r.name}</p>
                    {r.instructions && (
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{r.instructions}</p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">v{r.version}</td>
                  <td className="px-6 py-4 text-sm text-gray-700 tabular-nums">{r.yield_qty}</td>
                  <td className="px-6 py-4 text-sm text-gray-900 tabular-nums">
                    {r.cost_per_unit != null ? etbFormatter.format(r.cost_per_unit) : '—'}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {r.ingredients.length > 0 ? (
                        r.ingredients.slice(0, 3).map((ri) => (
                          <span
                            key={ri.id}
                            className="inline-block px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs"
                          >
                            {ri.ingredient_name ?? 'Unknown'}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-gray-400">None</span>
                      )}
                      {r.ingredients.length > 3 && (
                        <span className="inline-block px-2 py-0.5 bg-gray-100 text-gray-500 rounded text-xs">
                          +{r.ingredients.length - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${
                        r.is_active ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                      }`}
                    >
                      {r.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => openEdit(r)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                        title="Edit recipe"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleStatus(r)}
                        className={`p-1.5 rounded-lg transition-colors ${
                          r.is_active
                            ? 'text-gray-400 hover:text-amber-600 hover:bg-amber-50'
                            : 'text-gray-400 hover:text-green-600 hover:bg-green-50'
                        }`}
                        title={r.is_active ? 'Deactivate' : 'Activate'}
                      >
                        {r.is_active ? <ToggleLeft size={16} /> : <ToggleRight size={16} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {recipes.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-gray-400">
                    <div className="flex flex-col items-center gap-2">
                      <ChefHat className="text-gray-300" size={40} strokeWidth={1.5} />
                      <p>
                        {search.trim()
                          ? 'No recipes match your search.'
                          : 'No recipes yet. Create one to get started.'}
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
        <RecipeFormModal
          recipe={editingRecipe}
          onClose={() => {
            setShowModal(false);
            setEditingRecipe(null);
          }}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function RecipeFormModal({
  recipe,
  onClose,
  onSaved,
}: {
  recipe: RecipeDetail | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!recipe;

  const [name, setName] = useState(recipe?.name ?? '');
  const [yieldQty, setYieldQty] = useState(recipe?.yield_qty != null ? String(recipe.yield_qty) : '');
  const [instructions, setInstructions] = useState(recipe?.instructions ?? '');

  const [ingredientLines, setIngredientLines] = useState<IngredientLineForm[]>(
    recipe?.ingredients.map((ri) => ({
      ingredient_id: ri.ingredient_id,
      quantity_input: String(ri.quantity_required),
    })) ?? []
  );

  const [allIngredients, setAllIngredients] = useState<Ingredient[]>([]);
  const [loadingIngredients, setLoadingIngredients] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    ingredientsApi
      .list({ is_active: true })
      .then(setAllIngredients)
      .catch(() => setError('Failed to load ingredients'))
      .finally(() => setLoadingIngredients(false));
  }, []);

  const addLine = () => {
    const usedIds = new Set(ingredientLines.map((l) => l.ingredient_id));
    const available = allIngredients.filter((i) => !usedIds.has(i.id));
    if (available.length === 0) return;
    setIngredientLines((prev) => [
      ...prev,
      { ingredient_id: available[0].id, quantity_input: '' },
    ]);
  };

  const removeLine = (idx: number) => {
    setIngredientLines((prev) => prev.filter((_, i) => i !== idx));
  };

  const updateLine = (idx: number, field: keyof IngredientLineForm, value: string) => {
    setIngredientLines((prev) =>
      prev.map((line, i) => (i === idx ? { ...line, [field]: value } : line))
    );
  };

  const ingredientById = new Map(allIngredients.map((i) => [i.id, i]));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    const yNum = Number(yieldQty);
    if (!Number.isInteger(yNum) || yNum < 1) {
      setError('Yield must be a positive integer');
      setSaving(false);
      return;
    }

    const parsedIngredients: { ingredient_id: string; quantity_required: number }[] = [];
    for (const line of ingredientLines) {
      const qty = Number(line.quantity_input);
      if (!Number.isFinite(qty) || qty <= 0) {
        const ing = ingredientById.get(line.ingredient_id);
        setError(`Quantity for "${ing?.name ?? 'ingredient'}" must be greater than 0`);
        setSaving(false);
        return;
      }
      parsedIngredients.push({
        ingredient_id: line.ingredient_id,
        quantity_required: qty,
      });
    }

    try {
      if (isEdit) {
        const payload: UpdateRecipePayload = {
          name: name.trim(),
          yield_qty: yNum,
          instructions: instructions.trim() || undefined,
          ingredients: parsedIngredients,
        };
        await recipesApi.update(recipe!.id, payload);
      } else {
        const payload: CreateRecipePayload = {
          name: name.trim(),
          yield_qty: yNum,
          instructions: instructions.trim() || undefined,
          ingredients: parsedIngredients,
        };
        await recipesApi.create(payload);
      }
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to save recipe';
      setError(typeof msg === 'string' ? msg : 'Failed to save recipe');
    } finally {
      setSaving(false);
    }
  };

  const usedIds = new Set(ingredientLines.map((l) => l.ingredient_id));
  const canAddLine = allIngredients.filter((i) => !usedIds.has(i.id)).length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Edit Recipe' : 'Create Recipe'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Recipe Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Yield (units produced)</label>
              <input
                type="number"
                value={yieldQty}
                onChange={(e) => setYieldQty(e.target.value)}
                required
                min={1}
                step={1}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Instructions <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm resize-y"
            />
          </div>

          {/* Ingredient lines */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">Ingredients</label>
              <button
                type="button"
                onClick={addLine}
                disabled={!canAddLine || loadingIngredients}
                className="flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Plus size={14} />
                Add ingredient
              </button>
            </div>

            {loadingIngredients ? (
              <p className="text-sm text-gray-400">Loading ingredient list...</p>
            ) : ingredientLines.length === 0 ? (
              <p className="text-sm text-gray-400 border border-dashed border-gray-300 rounded-lg p-4 text-center">
                No ingredients added. Click "Add ingredient" above.
              </p>
            ) : (
              <div className="space-y-2">
                {ingredientLines.map((line, idx) => {
                  const availableForRow = allIngredients.filter(
                    (i) => i.id === line.ingredient_id || !usedIds.has(i.id)
                  );
                  const selected = ingredientById.get(line.ingredient_id);
                  return (
                    <div
                      key={idx}
                      className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg border border-gray-200"
                    >
                      <select
                        value={line.ingredient_id}
                        onChange={(e) => updateLine(idx, 'ingredient_id', e.target.value)}
                        className="flex-1 min-w-0 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-white"
                      >
                        {availableForRow.map((i) => (
                          <option key={i.id} value={i.id}>
                            {i.name} ({i.unit})
                          </option>
                        ))}
                      </select>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          value={line.quantity_input}
                          onChange={(e) => updateLine(idx, 'quantity_input', e.target.value)}
                          placeholder="Qty"
                          min={0}
                          step="0.001"
                          inputMode="decimal"
                          required
                          className="w-24 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-right tabular-nums"
                        />
                        {selected && (
                          <span className="text-xs text-gray-500 w-8">{selected.unit}</span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => removeLine(idx)}
                        className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                        title="Remove"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
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
              {saving ? 'Saving...' : isEdit ? 'Update Recipe' : 'Create Recipe'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
