import apiClient from './client';
import type { User, UserRole } from '../types';

export interface CreateUserPayload {
  username: string;
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
  store_id?: string;
}

export interface UpdateUserPayload {
  email?: string;
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
  store_id?: string | null;
}

export const usersApi = {
  list: async (params?: { role?: UserRole; is_active?: boolean }): Promise<User[]> => {
    const response = await apiClient.get('/users/', { params });
    return response.data;
  },

  getById: async (id: string): Promise<User> => {
    const response = await apiClient.get(`/users/${id}`);
    return response.data;
  },

  create: async (data: CreateUserPayload): Promise<User> => {
    const response = await apiClient.post('/users/', data);
    return response.data;
  },

  update: async (id: string, data: UpdateUserPayload): Promise<User> => {
    const response = await apiClient.put(`/users/${id}`, data);
    return response.data;
  },

  deactivate: async (id: string): Promise<void> => {
    await apiClient.delete(`/users/${id}`);
  },

  reactivate: async (id: string): Promise<User> => {
    const response = await apiClient.post(`/users/${id}/reactivate`);
    return response.data;
  },
};
