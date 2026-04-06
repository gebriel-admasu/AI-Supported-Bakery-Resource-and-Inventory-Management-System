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

export type UserRole = 'admin' | 'owner' | 'production_manager' | 'store_manager';

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
  product_id: string;
  date: string;
  opening_stock: number;
  quantity_sold: number;
  closing_stock: number;
  total_amount: number;
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
