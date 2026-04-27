import apiClient from './client';

export interface WastageDetail {
  id: string;
  store_id: string;
  store_name: string | null;
  product_id: string;
  product_name: string | null;
  date: string;
  quantity: number;
  reason: string;
  notes: string | null;
  recorded_by: string | null;
  recorded_by_name: string | null;
  created_at: string;
}

export interface CreateWastagePayload {
  store_id: string;
  product_id: string;
  date: string;
  quantity: number;
  reason: string;
  notes?: string;
}

export const wastageApi = {
  list: async (params?: { store_id?: string; product_id?: string }): Promise<WastageDetail[]> => {
    const response = await apiClient.get('/wastage/', { params });
    return response.data;
  },

  create: async (data: CreateWastagePayload): Promise<WastageDetail> => {
    const response = await apiClient.post('/wastage/', data);
    return response.data;
  },
};
