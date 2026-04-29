import { useAuth } from '../../context/AuthContext';

export default function DashboardPage() {
  const { user, role } = useAuth();

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome back, {user?.full_name}
        </h1>
        <p className="text-gray-500 mt-1">
          Here's an overview of your bakery operations
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {(role === 'owner' || role === 'production_manager') && (
          <>
            <StatCard title="Total Ingredients" value="--" subtitle="in stock" color="blue" />
            <StatCard title="Active Recipes" value="--" subtitle="formulas" color="green" />
            <StatCard title="Today's Production" value="--" subtitle="batches" color="purple" />
          </>
        )}
        {(role === 'owner' || role === 'finance_manager' || role === 'store_manager') && (
          <StatCard title="Today's Sales" value="--" subtitle="revenue" color="orange" />
        )}
        {role === 'owner' && (
          <StatCard title="Active Stores" value="--" subtitle="outlets" color="teal" />
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <p className="text-gray-500 text-sm">
          Dashboard widgets will be populated as modules are implemented in subsequent phases.
        </p>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  subtitle,
  color,
}: {
  title: string;
  value: string;
  subtitle: string;
  color: string;
}) {
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-700',
    green: 'bg-green-50 text-green-700',
    purple: 'bg-purple-50 text-purple-700',
    orange: 'bg-orange-50 text-orange-700',
    teal: 'bg-teal-50 text-teal-700',
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <p className="text-sm font-medium text-gray-500">{title}</p>
      <p className="text-3xl font-bold text-gray-900 mt-2">{value}</p>
      <span
        className={`inline-block mt-2 px-2 py-0.5 rounded-full text-xs font-medium ${colorClasses[color] || colorClasses.blue}`}
      >
        {subtitle}
      </span>
    </div>
  );
}
