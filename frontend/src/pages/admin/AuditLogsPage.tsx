import { useState, useEffect } from 'react';
import { auditApi, type AuditLog } from '../../api/audit';
import { ClipboardList } from 'lucide-react';

const ACTION_COLORS: Record<string, string> = {
  login_success: 'bg-green-50 text-green-700',
  login_failed: 'bg-red-50 text-red-700',
  login_blocked: 'bg-orange-50 text-orange-700',
  user_created: 'bg-blue-50 text-blue-700',
  user_updated: 'bg-yellow-50 text-yellow-700',
  user_deactivated: 'bg-red-50 text-red-700',
  user_reactivated: 'bg-green-50 text-green-700',
};

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState('');

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        setLoading(true);
        const params: Record<string, string | number> = { limit: 100 };
        if (actionFilter) params.action = actionFilter;
        const data = await auditApi.list(params);
        setLogs(data);
      } catch {
        /* silently fail */
      } finally {
        setLoading(false);
      }
    };
    fetchLogs();
  }, [actionFilter]);

  const uniqueActions = [...new Set(logs.map((l) => l.action))].sort();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
          <p className="text-gray-500 mt-1">Track all critical system actions</p>
        </div>
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
        >
          <option value="">All Actions</option>
          {uniqueActions.map((a) => (
            <option key={a} value={a}>
              {a.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading audit logs...</div>
        ) : logs.length === 0 ? (
          <div className="p-8 text-center text-gray-400 flex flex-col items-center gap-2">
            <ClipboardList size={40} />
            No audit logs found
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Action
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Resource
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Details
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    IP Address
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-3 text-sm text-gray-500 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="px-6 py-3">
                      <span
                        className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium capitalize ${
                          ACTION_COLORS[log.action] || 'bg-gray-50 text-gray-700'
                        }`}
                      >
                        {log.action.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-600">
                      {log.resource || '—'}
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-600 max-w-xs truncate">
                      {log.details || '—'}
                    </td>
                    <td className="px-6 py-3 text-sm text-gray-500 font-mono">
                      {log.ip_address || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
