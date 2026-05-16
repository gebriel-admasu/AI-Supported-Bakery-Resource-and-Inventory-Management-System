import apiClient from './client';
import type {
  PurchaseOrder,
  PurchaseOrderStatus,
  ReorderSuggestionResponse,
  Supplier,
} from '../types';

// ---------------------------------------------------------------------------
// Suppliers
// ---------------------------------------------------------------------------

export interface CreateSupplierPayload {
  name: string;
  contact_person?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  lead_time_days?: number | null;
}

export interface UpdateSupplierPayload {
  name?: string;
  contact_person?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  lead_time_days?: number | null;
  is_active?: boolean;
}

export const suppliersApi = {
  list: async (params?: {
    search?: string;
    is_active?: boolean;
    skip?: number;
    limit?: number;
  }): Promise<Supplier[]> => {
    const response = await apiClient.get('/suppliers/', { params });
    return response.data;
  },

  getById: async (id: string): Promise<Supplier> => {
    const response = await apiClient.get(`/suppliers/${id}`);
    return response.data;
  },

  create: async (data: CreateSupplierPayload): Promise<Supplier> => {
    const response = await apiClient.post('/suppliers/', data);
    return response.data;
  },

  update: async (id: string, data: UpdateSupplierPayload): Promise<Supplier> => {
    const response = await apiClient.put(`/suppliers/${id}`, data);
    return response.data;
  },

  deactivate: async (id: string): Promise<void> => {
    await apiClient.delete(`/suppliers/${id}`);
  },
};

// ---------------------------------------------------------------------------
// Purchase orders
// ---------------------------------------------------------------------------

export interface CreatePurchaseOrderPayload {
  supplier_id: string;
  ingredient_id: string;
  quantity: number;
  unit_cost: number;
  expected_delivery?: string | null;
  notes?: string | null;
}

export interface ListPurchaseOrdersParams {
  status?: PurchaseOrderStatus;
  supplier_id?: string;
  ingredient_id?: string;
  date_from?: string;
  date_to?: string;
  skip?: number;
  limit?: number;
}

export interface ApprovePurchaseOrderPayload {
  note?: string | null;
}

export interface SendPurchaseOrderPayload {
  expected_delivery?: string | null;
  note?: string | null;
}

export interface ReceivePurchaseOrderPayload {
  actual_delivery?: string | null;
  note?: string | null;
}

export interface CancelPurchaseOrderPayload {
  reason?: string | null;
}

export const purchaseOrdersApi = {
  list: async (params?: ListPurchaseOrdersParams): Promise<PurchaseOrder[]> => {
    const response = await apiClient.get('/purchase-orders/', { params });
    return response.data;
  },

  getById: async (id: string): Promise<PurchaseOrder> => {
    const response = await apiClient.get(`/purchase-orders/${id}`);
    return response.data;
  },

  create: async (
    data: CreatePurchaseOrderPayload
  ): Promise<PurchaseOrder> => {
    const response = await apiClient.post('/purchase-orders/', data);
    return response.data;
  },

  approve: async (
    id: string,
    data: ApprovePurchaseOrderPayload = {}
  ): Promise<PurchaseOrder> => {
    const response = await apiClient.post(
      `/purchase-orders/${id}/approve`,
      data
    );
    return response.data;
  },

  send: async (
    id: string,
    data: SendPurchaseOrderPayload = {}
  ): Promise<PurchaseOrder> => {
    const response = await apiClient.post(`/purchase-orders/${id}/send`, data);
    return response.data;
  },

  receive: async (
    id: string,
    data: ReceivePurchaseOrderPayload = {}
  ): Promise<PurchaseOrder> => {
    const response = await apiClient.post(
      `/purchase-orders/${id}/receive`,
      data
    );
    return response.data;
  },

  cancel: async (
    id: string,
    data: CancelPurchaseOrderPayload = {}
  ): Promise<PurchaseOrder> => {
    const response = await apiClient.post(
      `/purchase-orders/${id}/cancel`,
      data
    );
    return response.data;
  },
};

// ---------------------------------------------------------------------------
// Reorder suggestions
// ---------------------------------------------------------------------------

export const reorderApi = {
  list: async (): Promise<ReorderSuggestionResponse> => {
    const response = await apiClient.get('/reorder-suggestions/');
    return response.data;
  },
};
