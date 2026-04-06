import apiClient from './client';
import type { Ingredient } from '../types';

export interface CreateIngredientPayload {
  name: string;
  unit: string;
  unit_cost: number;
  expiry_date?: string;
  description?: string;
}

export interface UpdateIngredientPayload {
  name?: string;
  unit?: string;
  unit_cost?: number;
  expiry_date?: string | null;
  description?: string | null;
  is_active?: boolean;
}

export const ingredientsApi = {
  list: async (params?: { search?: string; is_active?: boolean }): Promise<Ingredient[]> => {
    const response = await apiClient.get('/ingredients/', { params });
    return response.data;
  },

  getById: async (id: string): Promise<Ingredient> => {
    const response = await apiClient.get(`/ingredients/${id}`);
    return response.data;
  },

  create: async (data: CreateIngredientPayload): Promise<Ingredient> => {
    const response = await apiClient.post('/ingredients/', data);
    return response.data;
  },

  update: async (id: string, data: UpdateIngredientPayload): Promise<Ingredient> => {
    const response = await apiClient.put(`/ingredients/${id}`, data);
    return response.data;
  },

  deactivate: async (id: string): Promise<Ingredient> => {
    const response = await apiClient.delete(`/ingredients/${id}`);
    return response.data;
  },
};
