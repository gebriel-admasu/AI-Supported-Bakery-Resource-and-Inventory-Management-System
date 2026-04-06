import apiClient from './client';

export interface AuditLog {
  id: string;
  user_id: string | null;
  action: string;
  resource: string | null;
  resource_id: string | null;
  details: string | null;
  ip_address: string | null;
  timestamp: string;
}

export const auditApi = {
  list: async (params?: {
    user_id?: string;
    action?: string;
    resource?: string;
    skip?: number;
    limit?: number;
  }): Promise<AuditLog[]> => {
    const response = await apiClient.get('/audit-logs/', { params });
    return response.data;
  },
};
