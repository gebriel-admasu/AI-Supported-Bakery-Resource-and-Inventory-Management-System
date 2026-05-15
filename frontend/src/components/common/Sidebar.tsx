import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { inventoryApi } from '../../api/inventory';
import { useAuth } from '../../context/AuthContext';
import type { UserRole } from '../../types';
import {
  LayoutDashboard,
  Package,
  ChefHat,
  ShoppingBag,
  Factory,
  Trash2,
  Truck,
  ShoppingCart,
  BarChart3,
  Brain,
  Users,
  Building2,
  Warehouse,
  LogOut,
  ClipboardList,
  Store,
  RefreshCw,
} from 'lucide-react';
import clsx from 'clsx';

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  roles: UserRole[];
}

const navItems: NavItem[] = [
  {
    label: 'Dashboard',
    path: '/dashboard',
    icon: <LayoutDashboard size={20} />,
    roles: ['admin', 'owner', 'finance_manager', 'production_manager', 'store_manager', 'delivery_staff'],
  },
  {
    label: 'Inventory',
    path: '/inventory',
    icon: <Warehouse size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Ingredients',
    path: '/ingredients',
    icon: <Package size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Recipes',
    path: '/recipes',
    icon: <ChefHat size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Products',
    path: '/products',
    icon: <ShoppingBag size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Production',
    path: '/production',
    icon: <Factory size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Suppliers',
    path: '/suppliers',
    icon: <Store size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Purchase Orders',
    path: '/purchase-orders',
    icon: <ClipboardList size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Reorder Suggestions',
    path: '/reorder-suggestions',
    icon: <RefreshCw size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'Wastage',
    path: '/wastage',
    icon: <Trash2 size={20} />,
    roles: ['owner', 'finance_manager', 'production_manager', 'store_manager'],
  },
  {
    label: 'Distribution',
    path: '/distribution',
    icon: <Truck size={20} />,
    roles: ['owner', 'production_manager', 'store_manager', 'delivery_staff'],
  },
  {
    label: 'Sales',
    path: '/sales',
    icon: <ShoppingCart size={20} />,
    roles: ['owner', 'finance_manager', 'store_manager'],
  },
  {
    label: 'Reports',
    path: '/reports',
    icon: <BarChart3 size={20} />,
    roles: ['owner', 'finance_manager'],
  },
  {
    label: 'Forecasting',
    path: '/forecasting',
    icon: <Brain size={20} />,
    roles: ['owner', 'production_manager'],
  },
  {
    label: 'User Management',
    path: '/admin/users',
    icon: <Users size={20} />,
    roles: ['admin'],
  },
  {
    label: 'Store Management',
    path: '/admin/stores',
    icon: <Building2 size={20} />,
    roles: ['admin', 'owner'],
  },
  {
    label: 'Audit Logs',
    path: '/admin/audit-logs',
    icon: <ClipboardList size={20} />,
    roles: ['admin', 'owner', 'finance_manager'],
  },
];

export default function Sidebar() {
  const { role, user, logout } = useAuth();
  const [inventoryAlertCount, setInventoryAlertCount] = useState(0);
  const canViewInventoryAlerts = role === 'owner' || role === 'production_manager';

  useEffect(() => {
    if (!canViewInventoryAlerts) {
      setInventoryAlertCount(0);
      return;
    }

    let mounted = true;
    const loadAlerts = async () => {
      try {
        const [stockAlerts, expiryAlerts] = await Promise.all([
          inventoryApi.listAlerts(),
          inventoryApi.listExpiryAlerts(),
        ]);
        if (mounted) {
          setInventoryAlertCount(stockAlerts.length + expiryAlerts.length);
        }
      } catch {
        if (mounted) {
          setInventoryAlertCount(0);
        }
      }
    };

    void loadAlerts();
    const pollId = window.setInterval(() => {
      void loadAlerts();
    }, 60_000);

    return () => {
      mounted = false;
      window.clearInterval(pollId);
    };
  }, [canViewInventoryAlerts]);

  const visibleItems = navItems.filter(
    (item) => role && item.roles.includes(role)
  );

  return (
    <aside className="w-64 bg-white border-r border-gray-200 min-h-screen flex flex-col">
      <div className="p-6 border-b border-gray-200">
        <h1 className="text-lg font-bold text-primary-700">Bakery Manager</h1>
        <p className="text-xs text-gray-500 mt-1">Resource & Inventory System</p>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {visibleItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary-50 text-primary-700'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              )
            }
          >
            {item.icon}
            {item.label}
            {item.path === '/inventory' && canViewInventoryAlerts && inventoryAlertCount > 0 ? (
              <span className="ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                {inventoryAlertCount > 99 ? '99+' : inventoryAlertCount}
              </span>
            ) : null}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-200">
        <div className="flex items-center gap-3 mb-3 px-3">
          <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center">
            <span className="text-sm font-semibold text-primary-700">
              {user?.full_name?.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{user?.full_name}</p>
            <p className="text-xs text-gray-500 capitalize">{role?.replace('_', ' ')}</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2 w-full rounded-lg text-sm text-gray-600 hover:bg-red-50 hover:text-red-600 transition-colors"
        >
          <LogOut size={20} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
