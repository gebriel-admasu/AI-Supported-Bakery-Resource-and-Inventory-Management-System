import apiClient from './client';
import type { Recipe } from '../types';

export interface RecipeIngredientPayload {
  ingredient_id: string;
  quantity_required: number;
}

export interface CreateRecipePayload {
  name: string;
  yield_qty: number;
  instructions?: string;
  ingredients: RecipeIngredientPayload[];
}

export interface UpdateRecipePayload {
  name?: string;
  yield_qty?: number;
  instructions?: string;
  is_active?: boolean;
  ingredients?: RecipeIngredientPayload[];
}

export interface RecipeIngredientDetail {
  id: string;
  ingredient_id: string;
  ingredient_name: string | null;
  ingredient_unit: string | null;
  ingredient_unit_cost: number | null;
  quantity_required: number;
}

export interface RecipeDetail extends Omit<Recipe, 'ingredients'> {
  cost_per_unit: number | null;
  created_by: string | null;
  ingredients: RecipeIngredientDetail[];
  created_at: string;
  updated_at: string;
}

export const recipesApi = {
  list: async (params?: { search?: string; is_active?: boolean }): Promise<RecipeDetail[]> => {
    const response = await apiClient.get('/recipes/', { params });
    return response.data;
  },

  getById: async (id: string): Promise<RecipeDetail> => {
    const response = await apiClient.get(`/recipes/${id}`);
    return response.data;
  },

  create: async (data: CreateRecipePayload): Promise<RecipeDetail> => {
    const response = await apiClient.post('/recipes/', data);
    return response.data;
  },

  update: async (id: string, data: UpdateRecipePayload): Promise<RecipeDetail> => {
    const response = await apiClient.put(`/recipes/${id}`, data);
    return response.data;
  },

  deactivate: async (id: string): Promise<void> => {
    await apiClient.delete(`/recipes/${id}`);
  },
};
