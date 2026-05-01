import apiClient from './client';

export interface InventoryStock {
  id: string;
  inventory_id: string;
  ingredient_id: string | null;
  product_id: string | null;
  quantity: number;
  min_threshold: number | null;
  ingredient_name: string | null;
  product_name: string | null;
  updated_at: string;
}

export interface StockAlert {
  id: string;
  inventory_stock_id: string;
  ingredient_id: string | null;
  current_qty: number;
  min_qty: number;
  status: string;
  timestamp: string;
  ingredient_name: string | null;
}

export interface ExpiryAlert {
  inventory_stock_id: string;
  ingredient_id: string;
  ingredient_name: string;
  quantity: number;
  unit: string;
  expiry_date: string;
  days_to_expiry: number;
  status: 'expired' | 'near_expiry';
}

export interface AddStockPayload {
  ingredient_id: string;
  quantity: number;
  min_threshold?: number;
}

export interface UpdateStockPayload {
  quantity: number;
  min_threshold?: number;
}

export const inventoryApi = {
  listStocks: async (): Promise<InventoryStock[]> => {
    const response = await apiClient.get('/inventory/stocks');
    return response.data;
  },

  addStock: async (data: AddStockPayload): Promise<InventoryStock> => {
    const response = await apiClient.post('/inventory/stocks', data);
    return response.data;
  },

  updateStock: async (stockId: string, data: UpdateStockPayload): Promise<InventoryStock> => {
    const response = await apiClient.put(`/inventory/stocks/${stockId}`, data);
    return response.data;
  },

  listAlerts: async (): Promise<StockAlert[]> => {
    const response = await apiClient.get('/inventory/alerts');
    return response.data;
  },

  listExpiryAlerts: async (nearExpiryDays = 7): Promise<ExpiryAlert[]> => {
    const response = await apiClient.get('/inventory/alerts/expiry', {
      params: { near_expiry_days: nearExpiryDays },
    });
    return response.data;
  },
};
