export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  store_id?: string;
  created_at: string;
}

export type UserRole =
  | 'admin'
  | 'owner'
  | 'finance_manager'
  | 'production_manager'
  | 'store_manager'
  | 'delivery_staff';

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  role: string;
  username: string;
}

export interface Store {
  id: string;
  name: string;
  location: string;
  is_active: boolean;
}

export interface Ingredient {
  id: string;
  name: string;
  unit: string;
  unit_cost: number;
  expiry_date?: string;
  description?: string;
  is_active: boolean;
}

export interface Product {
  id: string;
  name: string;
  sku: string;
  sale_price: number;
  unit: string;
  recipe_id?: string;
  description?: string;
  is_active: boolean;
}

export interface Recipe {
  id: string;
  name: string;
  version: number;
  yield_qty: number;
  cost_per_unit?: number;
  instructions?: string;
  is_active: boolean;
  ingredients: RecipeIngredient[];
}

export interface RecipeIngredient {
  id: string;
  ingredient_id: string;
  quantity_required: number;
}

export interface SalesRecord {
  id: string;
  store_id: string;
  store_name?: string | null;
  product_id: string;
  product_name?: string | null;
  date: string;
  opening_stock: number;
  quantity_sold: number;
  closing_stock: number;
  wastage_qty?: number;
  expected_closing?: number;
  variance_qty?: number;
  total_amount: number;
  is_closed?: boolean;
  closed_at?: string | null;
  notes?: string | null;
  recorded_by?: string | null;
  updated_at?: string | null;
}

export interface DemandForecast {
  id: string;
  product_id: string;
  store_id?: string;
  forecast_date: string;
  predicted_qty: number;
  actual_qty?: number;
  accuracy_score?: number;
}

export interface ForecastItem {
  store_ref: string;
  product_ref: string;
  store_name?: string | null;
  product_name?: string | null;
  target_date: string;
  predicted_qty: number;
  horizon: string;
}

export interface PredictResponse {
  model_version: number;
  generated_at: string;
  horizon_days: number;
  items: ForecastItem[];
}

export interface ForecastListItem {
  id: string;
  model_version: number;
  store_ref: string;
  product_ref: string;
  store_name?: string | null;
  product_name?: string | null;
  target_date: string;
  horizon: string;
  predicted_qty: number;
  actual_qty?: number | null;
  abs_error?: number | null;
  generated_at: string;
}

export interface ForecastListResponse {
  items: ForecastListItem[];
  total: number;
}

export interface OptimalBatchItem {
  product_ref: string;
  product_name?: string | null;
  target_date: string;
  forecasted_demand: number;
  suggested_batch_qty: number;
  confidence: string;
}

export interface OptimalBatchResponse {
  model_version: number;
  generated_at: string;
  horizon_days: number;
  items: OptimalBatchItem[];
}

export type ModelStatus =
  | 'candidate'
  | 'champion'
  | 'archived'
  | 'rejected';

export interface ModelRegistryItem {
  id: string;
  version: number;
  status: ModelStatus | string;
  trained_at: string;
  training_rows_used: number;
  training_source?: string | null;
  holdout_mae?: number | null;
  model_path: string;
  promoted_at?: string | null;
  archived_at?: string | null;
  notes?: string | null;
}

export interface ModelRegistryListResponse {
  champion_version: number | null;
  items: ModelRegistryItem[];
}

export interface ModelPerformancePoint {
  bucket_date: string;
  mae: number;
  predictions: number;
}

export interface ModelPerformanceResponse {
  model_version: number;
  window_days: number;
  overall_mae: number | null;
  daily: ModelPerformancePoint[];
}

export interface RetrainResponse {
  candidate_version: number;
  status: string;
  holdout_mae: number;
  training_rows: number;
  training_source: string;
  promoted: boolean;
  message: string;
}

export interface BacktestResponse {
  rows_scored: number;
  forecasts_skipped_no_actual: number;
  mean_abs_error: number | null;
  window_start: string | null;
  window_end: string | null;
}

export interface Supplier {
  id: string;
  name: string;
  contact_person?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  lead_time_days?: number | null;
  is_active: boolean;
  created_at: string;
}

export type PurchaseOrderStatus =
  | 'pending'
  | 'approved'
  | 'sent'
  | 'received'
  | 'cancelled';

export interface PurchaseOrder {
  id: string;
  supplier_id: string;
  supplier_name?: string | null;
  ingredient_id: string;
  ingredient_name?: string | null;
  ingredient_unit?: string | null;
  quantity: number;
  unit_cost: number;
  total_cost: number;
  order_date: string;
  expected_delivery?: string | null;
  actual_delivery?: string | null;
  status: PurchaseOrderStatus;
  created_by?: string | null;
  created_by_username?: string | null;
  created_at: string;
}

export interface ReorderSupplierOption {
  supplier_id: string;
  supplier_name: string;
  lead_time_days?: number | null;
  last_unit_cost?: number | null;
  last_order_date?: string | null;
  has_history: boolean;
}

export interface ReorderSuggestionItem {
  ingredient_id: string;
  ingredient_name: string;
  ingredient_unit: string;
  current_qty: number;
  min_threshold: number;
  shortage_qty: number;
  suggested_qty: number;
  suppliers: ReorderSupplierOption[];
}

export interface ReorderSuggestionResponse {
  items: ReorderSuggestionItem[];
}
