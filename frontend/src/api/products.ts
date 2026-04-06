import apiClient from './client';

export interface ProductDetail {
  id: string;
  name: string;
  sku: string;
  sale_price: number;
  unit: string;
  recipe_id: string | null;
  recipe_name: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateProductPayload {
  name: string;
  sku: string;
  sale_price: number;
  unit?: string;
  recipe_id?: string;
  description?: string;
}

export interface UpdateProductPayload {
  name?: string;
  sku?: string;
  sale_price?: number;
  unit?: string;
  recipe_id?: string | null;
  description?: string | null;
  is_active?: boolean;
}

export const productsApi = {
  list: async (params?: { search?: string; is_active?: boolean }): Promise<ProductDetail[]> => {
    const response = await apiClient.get('/products/', { params });
    return response.data;
  },

  getById: async (id: string): Promise<ProductDetail> => {
    const response = await apiClient.get(`/products/${id}`);
    return response.data;
  },

  create: async (data: CreateProductPayload): Promise<ProductDetail> => {
    const response = await apiClient.post('/products/', data);
    return response.data;
  },

  update: async (id: string, data: UpdateProductPayload): Promise<ProductDetail> => {
    const response = await apiClient.put(`/products/${id}`, data);
    return response.data;
  },

  deactivate: async (id: string): Promise<void> => {
    await apiClient.delete(`/products/${id}`);
  },
};
