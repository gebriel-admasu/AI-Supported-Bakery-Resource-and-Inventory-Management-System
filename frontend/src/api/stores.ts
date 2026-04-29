import apiClient from './client';
import type { Store } from '../types';

export interface CreateStorePayload {
  name: string;
  location?: string;
}

export interface UpdateStorePayload {
  name?: string;
  location?: string;
  is_active?: boolean;
}

export const storesApi = {
  list: async (params?: { is_active?: boolean }): Promise<Store[]> => {
    const response = await apiClient.get('/stores/', { params });
    return response.data;
  },

  create: async (data: CreateStorePayload): Promise<Store> => {
    const response = await apiClient.post('/stores/', data);
    return response.data;
  },

  update: async (storeId: string, data: UpdateStorePayload): Promise<Store> => {
    const response = await apiClient.put(`/stores/${storeId}`, data);
    return response.data;
  },
};
