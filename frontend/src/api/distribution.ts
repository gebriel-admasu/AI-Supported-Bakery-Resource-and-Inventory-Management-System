import apiClient from './client';

export interface DistributionItemDetail {
  id: string;
  product_id: string;
  product_name: string | null;
  quantity_sent: number;
  quantity_received: number | null;
  discrepancy_qty: number;
  discrepancy_reason: string | null;
  discrepancy_note: string | null;
}

export interface DistributionDetail {
  id: string;
  store_id: string;
  store_name: string | null;
  dispatch_date: string;
  status: string;
  dispatched_by: string | null;
  delivery_person_id: string | null;
  delivery_person_name: string | null;
  driver_count_confirmed: boolean;
  driver_count_confirmed_by: string | null;
  driver_count_confirmed_at: string | null;
  received_by: string | null;
  has_discrepancy: boolean;
  discrepancy_status: string;
  reviewed_by: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  is_locked: boolean;
  items: DistributionItemDetail[];
  created_at: string;
  updated_at: string;
}

export interface DistItemPayload {
  product_id: string;
  quantity_sent: number;
}

export interface CreateDistributionPayload {
  store_id: string;
  dispatch_date: string;
  delivery_person_id?: string;
  items: DistItemPayload[];
}

export interface ReceiveItemPayload {
  item_id: string;
  quantity_received: number;
  discrepancy_reason?: string;
  discrepancy_note?: string;
}

export interface DistributionDiscrepancyDecisionPayload {
  review_note?: string;
}

export const distributionApi = {
  list: async (params?: { store_id?: string; status?: string }): Promise<DistributionDetail[]> => {
    const response = await apiClient.get('/distributions/', { params });
    return response.data;
  },

  getById: async (id: string): Promise<DistributionDetail> => {
    const response = await apiClient.get(`/distributions/${id}`);
    return response.data;
  },

  create: async (data: CreateDistributionPayload): Promise<DistributionDetail> => {
    const response = await apiClient.post('/distributions/', data);
    return response.data;
  },

  updateStatus: async (id: string, newStatus: string): Promise<DistributionDetail> => {
    const response = await apiClient.put(`/distributions/${id}/status?new_status=${newStatus}`);
    return response.data;
  },

  receiveItems: async (id: string, items: ReceiveItemPayload[]): Promise<DistributionDetail> => {
    const response = await apiClient.put(`/distributions/${id}/receive`, items);
    return response.data;
  },

  confirmDriverCount: async (id: string): Promise<DistributionDetail> => {
    const response = await apiClient.put(`/distributions/${id}/driver-confirm-count`);
    return response.data;
  },

  approveDiscrepancy: async (
    id: string,
    data?: DistributionDiscrepancyDecisionPayload
  ): Promise<DistributionDetail> => {
    const response = await apiClient.put(`/distributions/${id}/discrepancy/approve`, data ?? {});
    return response.data;
  },

  rejectDiscrepancy: async (
    id: string,
    data?: DistributionDiscrepancyDecisionPayload
  ): Promise<DistributionDetail> => {
    const response = await apiClient.put(`/distributions/${id}/discrepancy/reject`, data ?? {});
    return response.data;
  },
};
