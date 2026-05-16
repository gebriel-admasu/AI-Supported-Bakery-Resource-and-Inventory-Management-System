import { useState } from 'react';
import {
  BarChart3,
  ChefHat,
  DollarSign,
  Package,
  ShoppingBag,
  Trash2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import FinancialReport from './FinancialReport';
import SalesReportTab from './SalesReportTab';
import WastageReportTab from './WastageReportTab';
import InventoryReportTab from './InventoryReportTab';
import ProductionReportTab from './ProductionReportTab';

type TabId = 'sales' | 'wastage' | 'inventory' | 'production' | 'financial';

interface TabDef {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Roles permitted to see this tab. */
  roles: string[];
}

const ALL_TABS: TabDef[] = [
  {
    id: 'sales',
    label: 'Sales',
    icon: ShoppingBag,
    roles: ['owner', 'finance_manager', 'store_manager'],
  },
  {
    id: 'wastage',
    label: 'Wastage',
    icon: Trash2,
    roles: ['owner', 'finance_manager', 'production_manager'],
  },
  {
    id: 'inventory',
    label: 'Inventory',
    icon: Package,
    roles: ['owner', 'finance_manager', 'production_manager'],
  },
  {
    id: 'production',
    label: 'Production',
    icon: ChefHat,
    roles: ['owner', 'finance_manager', 'production_manager'],
  },
  {
    id: 'financial',
    label: 'Financial',
    icon: DollarSign,
    roles: ['owner', 'finance_manager'],
  },
];

export default function ReportsPage() {
  const { role } = useAuth();
  const availableTabs = ALL_TABS.filter((t) => !role || t.roles.includes(role));
  const [activeTab, setActiveTab] = useState<TabId>(
    availableTabs[0]?.id ?? 'sales'
  );

  if (!availableTabs.length) {
    return (
      <div className="text-sm text-gray-500 italic">
        You don't have access to any reports.
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BarChart3 className="w-7 h-7 text-primary-600" />
            Reports &amp; Analytics
          </h1>
          <p className="text-gray-500 mt-1 text-sm">
            Operational insights across sales, wastage, inventory, production,
            and finance.
          </p>
        </div>
      </div>

      <div className="border-b border-gray-200 mb-5">
        <nav className="flex gap-1 overflow-x-auto" aria-label="Report tabs">
          {availableTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  isActive
                    ? 'border-primary-600 text-primary-700'
                    : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {activeTab === 'sales' && <SalesReportTab />}
      {activeTab === 'wastage' && <WastageReportTab />}
      {activeTab === 'inventory' && <InventoryReportTab />}
      {activeTab === 'production' && <ProductionReportTab />}
      {activeTab === 'financial' && <FinancialReport />}
    </div>
  );
}
