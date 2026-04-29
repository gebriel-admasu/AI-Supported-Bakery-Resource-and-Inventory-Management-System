import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import type { Store } from '../../types';
import { storesApi, type CreateStorePayload, type UpdateStorePayload } from '../../api/stores';
import { ArrowRight, Building2, ListChecks, Pencil, ShieldCheck, ShieldOff, X } from 'lucide-react';

export default function StoreManagementPage() {
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingStore, setEditingStore] = useState<Store | null>(null);

  const fetchStores = async () => {
    try {
      setLoading(true);
      setError('');
      const data = await storesApi.list();
      setStores(data);
    } catch {
      setError('Failed to load stores');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchStores();
  }, []);

  const openCreate = () => {
    setEditingStore(null);
    setShowModal(true);
  };

  const openEdit = (store: Store) => {
    setEditingStore(store);
    setShowModal(true);
  };

  const handleToggleStatus = async (store: Store) => {
    try {
      await storesApi.update(store.id, { is_active: !store.is_active });
      await fetchStores();
    } catch {
      setError(`Failed to ${store.is_active ? 'deactivate' : 'activate'} store`);
    }
  };

  const handleSaved = () => {
    setShowModal(false);
    setEditingStore(null);
    void fetchStores();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Store Management</h1>
          <p className="text-gray-500 mt-1">Create and manage branch stores for multi-location operations</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors"
        >
          <Building2 size={18} />
          Add Store
        </button>
      </div>

      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-5 mb-5">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-indigo-100 flex items-center justify-center shrink-0">
            <ListChecks size={18} className="text-indigo-700" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-indigo-900">New Branch Onboarding Checklist</h2>
            <p className="text-sm text-indigo-700 mt-1">
              Use these steps whenever you open a new branch store to keep operations and reporting clean.
            </p>
            <div className="mt-3 grid grid-cols-1 lg:grid-cols-3 gap-3 text-sm">
              <div className="bg-white/80 border border-indigo-100 rounded-lg p-3">
                <p className="font-semibold text-gray-900">1. Create Store</p>
                <p className="text-gray-600 mt-1">
                  Add the new branch name and location, then keep it active for daily operations.
                </p>
              </div>
              <div className="bg-white/80 border border-indigo-100 rounded-lg p-3">
                <p className="font-semibold text-gray-900">2. Assign Manager</p>
                <p className="text-gray-600 mt-1">
                  Create or update a user with <code>store_manager</code> role and set the branch <code>store_id</code>.
                </p>
                <Link
                  to="/admin/users"
                  className="inline-flex items-center gap-1 mt-2 text-indigo-700 hover:text-indigo-900 font-medium"
                >
                  Go to User Management <ArrowRight size={14} />
                </Link>
              </div>
              <div className="bg-white/80 border border-indigo-100 rounded-lg p-3">
                <p className="font-semibold text-gray-900">3. Verify Visibility</p>
                <p className="text-gray-600 mt-1">
                  Confirm the branch appears in Sales/Distribution/Wastage dropdowns and owner reports.
                </p>
                <div className="flex flex-wrap gap-2 mt-2">
                  <Link to="/sales" className="text-indigo-700 hover:text-indigo-900 font-medium">Sales</Link>
                  <span className="text-indigo-300">|</span>
                  <Link to="/distribution" className="text-indigo-700 hover:text-indigo-900 font-medium">Distribution</Link>
                  <span className="text-indigo-300">|</span>
                  <Link to="/wastage" className="text-indigo-700 hover:text-indigo-900 font-medium">Wastage</Link>
                </div>
              </div>
            </div>
          </div>
        </div>
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
          <div className="p-8 text-center text-gray-400">Loading stores...</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Store</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Location</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {stores.map((store) => (
                <tr key={store.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{store.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{store.location || '—'}</td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${
                        store.is_active
                          ? 'bg-green-50 text-green-700'
                          : 'bg-red-50 text-red-700'
                      }`}
                    >
                      {store.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => openEdit(store)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                        title="Edit store"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleStatus(store)}
                        className={`p-1.5 rounded-lg transition-colors ${
                          store.is_active
                            ? 'text-gray-400 hover:text-red-600 hover:bg-red-50'
                            : 'text-gray-400 hover:text-green-600 hover:bg-green-50'
                        }`}
                        title={store.is_active ? 'Deactivate store' : 'Activate store'}
                      >
                        {store.is_active ? <ShieldOff size={16} /> : <ShieldCheck size={16} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {stores.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                    No stores found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <StoreFormModal
          store={editingStore}
          onClose={() => {
            setShowModal(false);
            setEditingStore(null);
          }}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function StoreFormModal({
  store,
  onClose,
  onSaved,
}: {
  store: Store | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!store;
  const [name, setName] = useState(store?.name ?? '');
  const [location, setLocation] = useState(store?.location ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    try {
      if (isEdit) {
        const payload: UpdateStorePayload = {
          name: name.trim(),
          location: location.trim() || undefined,
        };
        await storesApi.update(store.id, payload);
      } else {
        const payload: CreateStorePayload = {
          name: name.trim(),
          location: location.trim() || undefined,
        };
        await storesApi.create(payload);
      }
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to save store';
      setError(typeof msg === 'string' ? msg : 'Failed to save store');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">{isEdit ? 'Edit Store' : 'Create New Store'}</h2>
          <button type="button" onClick={onClose} className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Store Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Location <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
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
              {saving ? 'Saving...' : isEdit ? 'Update Store' : 'Create Store'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
