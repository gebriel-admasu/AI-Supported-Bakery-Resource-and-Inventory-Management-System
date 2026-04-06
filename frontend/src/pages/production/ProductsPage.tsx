import { useState, useEffect, type FormEvent } from 'react';
import {
  productsApi,
  type ProductDetail,
  type CreateProductPayload,
  type UpdateProductPayload,
} from '../../api/products';
import { type RecipeDetail, recipesApi } from '../../api/recipes';
import {
  Plus,
  Pencil,
  ToggleLeft,
  ToggleRight,
  Search,
  ShoppingBag,
  X,
} from 'lucide-react';

const etbFormatter = new Intl.NumberFormat('en-ET', {
  style: 'currency',
  currency: 'ETB',
  minimumFractionDigits: 2,
});

export default function ProductsPage() {
  const [products, setProducts] = useState<ProductDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState<ProductDetail | null>(null);

  async function fetchProducts() {
    try {
      setLoading(true);
      setError('');
      const data = await productsApi.list({ search: search.trim() || undefined });
      setProducts(data);
    } catch {
      setError('Failed to load products');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void fetchProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const handleToggleStatus = async (product: ProductDetail) => {
    try {
      if (product.is_active) {
        await productsApi.deactivate(product.id);
      } else {
        await productsApi.update(product.id, { is_active: true });
      }
      await fetchProducts();
    } catch {
      setError(`Failed to ${product.is_active ? 'deactivate' : 'reactivate'} product`);
    }
  };

  const openCreate = () => {
    setEditingProduct(null);
    setShowModal(true);
  };

  const openEdit = (product: ProductDetail) => {
    setEditingProduct(product);
    setShowModal(true);
  };

  const handleSaved = () => {
    setShowModal(false);
    setEditingProduct(null);
    fetchProducts();
  };

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Products</h1>
          <p className="text-gray-500 mt-1">Manage your product catalog with pricing and recipe linkage</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center justify-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors shrink-0"
        >
          <Plus size={18} />
          Add Product
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
            placeholder="Search products by name..."
            className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm bg-white"
          />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading products...</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">SKU</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Price</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Unit</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Recipe</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {products.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <p className="text-sm font-medium text-gray-900">{p.name}</p>
                    {p.description && (
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{p.description}</p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700 font-mono">{p.sku}</td>
                  <td className="px-6 py-4 text-sm text-gray-900 tabular-nums">
                    {etbFormatter.format(p.sale_price)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">{p.unit}</td>
                  <td className="px-6 py-4">
                    {p.recipe_name ? (
                      <span className="inline-block px-2 py-0.5 bg-purple-50 text-purple-700 rounded text-xs">
                        {p.recipe_name}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">Unlinked</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${
                        p.is_active ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                      }`}
                    >
                      {p.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => openEdit(p)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                        title="Edit product"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleStatus(p)}
                        className={`p-1.5 rounded-lg transition-colors ${
                          p.is_active
                            ? 'text-gray-400 hover:text-amber-600 hover:bg-amber-50'
                            : 'text-gray-400 hover:text-green-600 hover:bg-green-50'
                        }`}
                        title={p.is_active ? 'Deactivate' : 'Activate'}
                      >
                        {p.is_active ? <ToggleLeft size={16} /> : <ToggleRight size={16} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {products.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-gray-400">
                    <div className="flex flex-col items-center gap-2">
                      <ShoppingBag className="text-gray-300" size={40} strokeWidth={1.5} />
                      <p>
                        {search.trim()
                          ? 'No products match your search.'
                          : 'No products yet. Add one to get started.'}
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
        <ProductFormModal
          product={editingProduct}
          onClose={() => {
            setShowModal(false);
            setEditingProduct(null);
          }}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

const COMMON_UNITS = ['piece', 'box', 'pack', 'dozen', 'kg', 'g', 'L', 'mL'] as const;

function ProductFormModal({
  product,
  onClose,
  onSaved,
}: {
  product: ProductDetail | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!product;
  const unitOptions =
    product?.unit && !(COMMON_UNITS as readonly string[]).includes(product.unit)
      ? [...COMMON_UNITS, product.unit]
      : COMMON_UNITS;

  const [form, setForm] = useState({
    name: product?.name ?? '',
    sku: product?.sku ?? '',
    sale_price: product != null ? String(product.sale_price) : '',
    unit: product?.unit ?? 'piece',
    recipe_id: product?.recipe_id ?? '',
    description: product?.description ?? '',
  });
  const [recipes, setRecipes] = useState<RecipeDetail[]>([]);
  const [loadingRecipes, setLoadingRecipes] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    recipesApi
      .list({ is_active: true })
      .then(setRecipes)
      .catch(() => setError('Failed to load recipes'))
      .finally(() => setLoadingRecipes(false));
  }, []);

  const handleChange = (field: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    const priceNum = Number(form.sale_price);
    if (Number.isNaN(priceNum) || priceNum < 0) {
      setError('Sale price must be a valid non-negative number');
      setSaving(false);
      return;
    }

    try {
      if (isEdit) {
        const payload: UpdateProductPayload = {
          name: form.name.trim(),
          sku: form.sku.trim(),
          sale_price: priceNum,
          unit: form.unit,
          recipe_id: form.recipe_id || null,
          description: form.description.trim() || null,
        };
        await productsApi.update(product!.id, payload);
      } else {
        const payload: CreateProductPayload = {
          name: form.name.trim(),
          sku: form.sku.trim(),
          sale_price: priceNum,
          unit: form.unit,
          recipe_id: form.recipe_id || undefined,
          description: form.description.trim() || undefined,
        };
        await productsApi.create(payload);
      }
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to save product';
      setError(typeof msg === 'string' ? msg : 'Failed to save product');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? 'Edit Product' : 'Add Product'}
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
            <label className="block text-sm font-medium text-gray-700 mb-1">Product Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => handleChange('name', e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">SKU</label>
            <input
              type="text"
              value={form.sku}
              onChange={(e) => handleChange('sku', e.target.value)}
              required
              placeholder="e.g. BRD-001"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm font-mono"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sale Price (ETB)</label>
              <input
                type="number"
                value={form.sale_price}
                onChange={(e) => handleChange('sale_price', e.target.value)}
                required
                min={0}
                step="0.01"
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
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Recipe <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            {loadingRecipes ? (
              <p className="text-sm text-gray-400">Loading recipes...</p>
            ) : (
              <select
                value={form.recipe_id}
                onChange={(e) => handleChange('recipe_id', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
              >
                <option value="">— No recipe linked —</option>
                {recipes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} (v{r.version})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={form.description}
              onChange={(e) => handleChange('description', e.target.value)}
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
              {saving ? 'Saving...' : isEdit ? 'Update Product' : 'Create Product'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
