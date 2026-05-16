import apiClient from './client';
import type {
  BacktestResponse,
  ForecastListResponse,
  ModelPerformanceResponse,
  ModelRegistryListResponse,
  OptimalBatchResponse,
  PredictResponse,
  RetrainResponse,
} from '../types';

// ---------------------------------------------------------------------------
// Request payloads
// ---------------------------------------------------------------------------

export interface PredictPayload {
  store_id?: string;
  product_id?: string;
  target_date?: string;
  days?: number;
}

export interface ForecastsQuery {
  model_version?: number;
  store_id?: string;
  product_id?: string;
  target_date_from?: string;
  target_date_to?: string;
  limit?: number;
  offset?: number;
}

export interface OptimalBatchesQuery {
  target_date?: string;
  days?: number;
  store_id?: string;
}

export interface ModelPerformanceQuery {
  version?: number;
  window_days?: number;
}

export interface RetrainPayload {
  source?: 'kaggle' | 'synthetic' | 'live';
  reason?: string;
}

export interface BacktestQuery {
  lookback_days?: number;
  target_date?: string;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const aiApi = {
  predict: async (payload: PredictPayload = {}): Promise<PredictResponse> => {
    const response = await apiClient.post('/ai/predict', payload);
    return response.data;
  },

  listForecasts: async (
    params: ForecastsQuery = {}
  ): Promise<ForecastListResponse> => {
    const response = await apiClient.get('/ai/forecasts', { params });
    return response.data;
  },

  optimalBatches: async (
    params: OptimalBatchesQuery = {}
  ): Promise<OptimalBatchResponse> => {
    const response = await apiClient.get('/ai/optimal-batches', { params });
    return response.data;
  },

  listModels: async (): Promise<ModelRegistryListResponse> => {
    const response = await apiClient.get('/ai/models');
    return response.data;
  },

  modelPerformance: async (
    params: ModelPerformanceQuery = {}
  ): Promise<ModelPerformanceResponse> => {
    const response = await apiClient.get('/ai/models/performance', { params });
    return response.data;
  },

  retrain: async (payload: RetrainPayload = {}): Promise<RetrainResponse> => {
    const response = await apiClient.post('/ai/retrain', payload);
    return response.data;
  },

  backtest: async (params: BacktestQuery = {}): Promise<BacktestResponse> => {
    const response = await apiClient.post('/ai/backtest', null, { params });
    return response.data;
  },
};
