import apiClient from './client';
import type { Store } from '../types';

export const storesApi = {
  list: async (): Promise<Store[]> => {
    const response = await apiClient.get('/stores/');
    return response.data;
  },
};
