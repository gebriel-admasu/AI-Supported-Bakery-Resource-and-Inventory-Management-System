import apiClient from './client';

export interface FinanceSummary {
  date_from: string;
  date_to: string;
  total_revenue: number;
  total_cogs: number;
  gross_profit: number;
  gross_margin_pct: number;
  total_wastage_cost: number;
  estimated_net_profit: number;
  total_units_sold: number;
  total_wastage_units: number;
  missing_cost_rows: number;
}

export interface ProductMarginItem {
  product_id: string;
  product_name: string;
  sku: string;
  units_sold: number;
  revenue: number;
  cogs: number;
  gross_profit: number;
  gross_margin_pct: number;
  avg_selling_price: number;
  unit_cogs: number;
  missing_cost: boolean;
}

export interface ProductMarginResponse {
  date_from: string;
  date_to: string;
  items: ProductMarginItem[];
}

export interface PnlTrendPoint {
  date: string;
  revenue: number;
  cogs: number;
  gross_profit: number;
  wastage_cost: number;
  estimated_net_profit: number;
}

export interface PnlTrendResponse {
  date_from: string;
  date_to: string;
  points: PnlTrendPoint[];
  total_revenue: number;
  total_cogs: number;
  gross_profit: number;
  total_wastage_cost: number;
  estimated_net_profit: number;
}

export interface FinanceFilters {
  date_from?: string;
  date_to?: string;
  store_id?: string;
  product_id?: string;
}

export const financeApi = {
  getSummary: async (params?: FinanceFilters): Promise<FinanceSummary> => {
    const response = await apiClient.get('/finance/summary', { params });
    return response.data;
  },

  getProductMargins: async (
    params?: Omit<FinanceFilters, 'product_id'> & { limit?: number }
  ): Promise<ProductMarginResponse> => {
    const response = await apiClient.get('/finance/product-margins', { params });
    return response.data;
  },

  getPnlTrend: async (params?: FinanceFilters): Promise<PnlTrendResponse> => {
    const response = await apiClient.get('/finance/pnl-trend', { params });
    return response.data;
  },
};
