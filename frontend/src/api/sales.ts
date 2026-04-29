import apiClient from './client';

export interface SalesRecordDetail {
  id: string;
  store_id: string;
  store_name: string | null;
  product_id: string;
  product_name: string | null;
  date: string;
  opening_stock: number;
  today_received_qty: number;
  total_product_qty: number;
  quantity_sold: number;
  closing_stock: number;
  wastage_qty: number;
  expected_closing: number;
  variance_qty: number;
  total_amount: number;
  is_closed: boolean;
  closed_at: string | null;
  notes: string | null;
  recorded_by: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface SalesOpenPayload {
  store_id: string;
  product_id: string;
  date: string;
  opening_stock: number;
  notes?: string;
}

export interface SalesSellPayload {
  quantity_sold: number;
  notes?: string;
}

export interface SalesClosePayload {
  closing_stock: number;
  notes?: string;
  auto_record_wastage?: boolean;
}

export interface SalesUpdatePayload {
  opening_stock?: number;
  quantity_sold?: number;
  closing_stock?: number;
  notes?: string;
}

export const salesApi = {
  list: async (params?: {
    store_id?: string;
    product_id?: string;
    date_from?: string;
    date_to?: string;
    is_closed?: boolean;
  }): Promise<SalesRecordDetail[]> => {
    const response = await apiClient.get('/sales/records', { params });
    return response.data;
  },

  openDay: async (data: SalesOpenPayload): Promise<SalesRecordDetail> => {
    const response = await apiClient.post('/sales/open', data);
    return response.data;
  },

  recordSale: async (recordId: string, data: SalesSellPayload): Promise<SalesRecordDetail> => {
    const response = await apiClient.put(`/sales/${recordId}/sell`, data);
    return response.data;
  },

  closeDay: async (recordId: string, data: SalesClosePayload): Promise<SalesRecordDetail> => {
    const response = await apiClient.put(`/sales/${recordId}/close`, data);
    return response.data;
  },

  reopenDay: async (recordId: string): Promise<SalesRecordDetail> => {
    const response = await apiClient.put(`/sales/${recordId}/reopen`);
    return response.data;
  },

  updateRecord: async (recordId: string, data: SalesUpdatePayload): Promise<SalesRecordDetail> => {
    const response = await apiClient.put(`/sales/${recordId}`, data);
    return response.data;
  },
};
