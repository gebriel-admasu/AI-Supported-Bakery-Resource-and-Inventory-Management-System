import apiClient from './client';

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export interface SparklinePoint {
  date: string;
  value: number;
}

export interface DashboardTopProduct {
  product_id: string;
  product_name: string;
  units_sold: number;
}

export interface DashboardActivityItem {
  kind: 'sale' | 'production' | 'purchase_order' | 'wastage';
  summary: string;
  occurred_at: string;
  actor?: string | null;
}

export interface DashboardResponse {
  role: string;
  revenue_today: number | null;
  revenue_week: number | null;
  revenue_month: number | null;
  gross_profit_week: number | null;
  units_sold_today: number | null;
  production_batches_today: number | null;
  active_stock_alerts: number | null;
  expiring_ingredients: number | null;
  pending_purchase_orders: number | null;
  revenue_sparkline: SparklinePoint[];
  batches_sparkline: SparklinePoint[];
  top_product_today: DashboardTopProduct | null;
  recent_activity: DashboardActivityItem[];
  scoped_store_id: string | null;
  scoped_store_name: string | null;
}

// ---------------------------------------------------------------------------
// Sales trends + top sellers
// ---------------------------------------------------------------------------

export interface SalesTrendPoint {
  date: string;
  units_sold: number;
  revenue: number;
  transaction_count: number;
}

export interface SalesTrendsResponse {
  granularity: 'day' | 'week';
  points: SalesTrendPoint[];
  total_units: number;
  total_revenue: number;
}

export interface TopSellerItem {
  product_id: string;
  product_name: string;
  sku?: string | null;
  units_sold: number;
  revenue: number;
  avg_unit_price: number;
}

export interface TopSellersResponse {
  order_by: 'units' | 'revenue';
  items: TopSellerItem[];
}

// ---------------------------------------------------------------------------
// Wastage trends
// ---------------------------------------------------------------------------

export interface WastageTrendBucket {
  key: string;
  label: string;
  total_qty: number;
  total_cost: number;
  record_count: number;
}

export interface WastageTrendsResponse {
  group_by: 'date' | 'reason' | 'source';
  buckets: WastageTrendBucket[];
  total_qty: number;
  total_cost: number;
}

// ---------------------------------------------------------------------------
// Ingredient consumption
// ---------------------------------------------------------------------------

export interface IngredientConsumptionItem {
  ingredient_id: string;
  ingredient_name: string;
  unit: string;
  total_qty_consumed: number;
  total_cost: number;
  batch_count: number;
}

export interface IngredientConsumptionResponse {
  items: IngredientConsumptionItem[];
  total_cost: number;
}

// ---------------------------------------------------------------------------
// Production efficiency
// ---------------------------------------------------------------------------

export interface ProductionByRecipeItem {
  recipe_id: string;
  recipe_name: string;
  planned_batches: number;
  completed_batches: number;
  cancelled_batches: number;
  total_planned_qty: number;
  total_actual_qty: number;
  avg_yield_variance_pct: number;
}

export interface ProductionEfficiencyResponse {
  planned_count: number;
  in_progress_count: number;
  completed_count: number;
  cancelled_count: number;
  total_batches: number;
  completion_rate: number;
  avg_yield_variance_pct: number;
  by_recipe: ProductionByRecipeItem[];
}

// ---------------------------------------------------------------------------
// Filter types
// ---------------------------------------------------------------------------

export interface DateRangeFilters {
  date_from?: string;
  date_to?: string;
}

export interface SalesTrendFilters extends DateRangeFilters {
  store_id?: string;
  product_id?: string;
  granularity?: 'day' | 'week';
}

export interface TopSellersFilters extends DateRangeFilters {
  store_id?: string;
  limit?: number;
  order_by?: 'units' | 'revenue';
}

export interface WastageTrendFilters extends DateRangeFilters {
  store_id?: string;
  group_by?: 'date' | 'reason' | 'source';
}

export interface IngredientConsumptionFilters extends DateRangeFilters {
  ingredient_id?: string;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const reportsApi = {
  getDashboard: async (): Promise<DashboardResponse> => {
    const response = await apiClient.get('/reports/dashboard');
    return response.data;
  },

  getSalesTrends: async (
    params?: SalesTrendFilters
  ): Promise<SalesTrendsResponse> => {
    const response = await apiClient.get('/reports/sales-trends', { params });
    return response.data;
  },

  getTopSellers: async (
    params?: TopSellersFilters
  ): Promise<TopSellersResponse> => {
    const response = await apiClient.get('/reports/top-sellers', { params });
    return response.data;
  },

  getWastageTrends: async (
    params?: WastageTrendFilters
  ): Promise<WastageTrendsResponse> => {
    const response = await apiClient.get('/reports/wastage-trends', { params });
    return response.data;
  },

  getIngredientConsumption: async (
    params?: IngredientConsumptionFilters
  ): Promise<IngredientConsumptionResponse> => {
    const response = await apiClient.get('/reports/ingredient-consumption', {
      params,
    });
    return response.data;
  },

  getProductionEfficiency: async (
    params?: DateRangeFilters
  ): Promise<ProductionEfficiencyResponse> => {
    const response = await apiClient.get('/reports/production-efficiency', {
      params,
    });
    return response.data;
  },
};
