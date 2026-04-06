import apiClient from './client';

export interface BatchDetail {
  id: string;
  recipe_id: string;
  recipe_name: string | null;
  product_id: string;
  product_name: string | null;
  batch_size: number;
  actual_yield: number | null;
  waste_qty: number | null;
  production_date: string;
  status: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateBatchPayload {
  recipe_id: string;
  product_id: string;
  batch_size: number;
  production_date: string;
}

export interface UpdateBatchPayload {
  status?: string;
  actual_yield?: number;
  waste_qty?: number;
}

export const productionApi = {
  listBatches: async (params?: { status?: string }): Promise<BatchDetail[]> => {
    const response = await apiClient.get('/production/batches', { params });
    return response.data;
  },

  getBatch: async (id: string): Promise<BatchDetail> => {
    const response = await apiClient.get(`/production/batches/${id}`);
    return response.data;
  },

  createBatch: async (data: CreateBatchPayload): Promise<BatchDetail> => {
    const response = await apiClient.post('/production/batches', data);
    return response.data;
  },

  updateBatch: async (id: string, data: UpdateBatchPayload): Promise<BatchDetail> => {
    const response = await apiClient.put(`/production/batches/${id}`, data);
    return response.data;
  },
};
