import { createBrowserRouter, Navigate } from 'react-router-dom';
import AuthLayout from './components/common/AuthLayout';
import Layout from './components/common/Layout';
import ProtectedRoute from './components/common/ProtectedRoute';
import LoginPage from './pages/auth/LoginPage';
import DashboardPage from './pages/dashboard/DashboardPage';
import InventoryPage from './pages/inventory/InventoryPage';
import IngredientsPage from './pages/inventory/IngredientsPage';
import RecipesPage from './pages/production/RecipesPage';
import ProductsPage from './pages/production/ProductsPage';
import ProductionPage from './pages/production/ProductionPage';
import WastagePage from './pages/production/WastagePage';
import DistributionPage from './pages/distribution/DistributionPage';
import SalesPage from './pages/sales/SalesPage';
import ReportsPage from './pages/reports/ReportsPage';
import ForecastingPage from './pages/forecasting/ForecastingPage';
import AiInsightsPage from './pages/ai/AiInsightsPage';
import SuppliersPage from './pages/suppliers/SuppliersPage';
import PurchaseOrdersPage from './pages/suppliers/PurchaseOrdersPage';
import ReorderSuggestionsPage from './pages/suppliers/ReorderSuggestionsPage';
import UserManagementPage from './pages/admin/UserManagementPage';
import StoreManagementPage from './pages/admin/StoreManagementPage';
import AuditLogsPage from './pages/admin/AuditLogsPage';

export const router = createBrowserRouter([
  {
    element: <AuthLayout />,
    children: [
      {
        path: '/login',
        element: <LoginPage />,
      },
      {
        path: '/',
        element: (
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        ),
        children: [
          { index: true, element: <Navigate to="/dashboard" replace /> },
          { path: 'dashboard', element: <DashboardPage /> },
          {
            path: 'inventory',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <InventoryPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'ingredients',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <IngredientsPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'recipes',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <RecipesPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'products',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <ProductsPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'production',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <ProductionPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'wastage',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'finance_manager', 'production_manager', 'store_manager']}>
                <WastagePage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'distribution',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager', 'store_manager', 'delivery_staff']}>
                <DistributionPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'sales',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'finance_manager', 'store_manager']}>
                <SalesPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'sales/:salesDate',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'finance_manager', 'store_manager']}>
                <SalesPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'reports',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'finance_manager']}>
                <ReportsPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'forecasting',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <ForecastingPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'ai-insights',
            element: (
              <ProtectedRoute allowedRoles={['admin', 'owner', 'production_manager']}>
                <AiInsightsPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'suppliers',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <SuppliersPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'purchase-orders',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <PurchaseOrdersPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'reorder-suggestions',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager']}>
                <ReorderSuggestionsPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'admin/users',
            element: (
              <ProtectedRoute allowedRoles={['admin']}>
                <UserManagementPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'admin/stores',
            element: (
              <ProtectedRoute allowedRoles={['admin', 'owner']}>
                <StoreManagementPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'admin/audit-logs',
            element: (
              <ProtectedRoute allowedRoles={['admin', 'owner', 'finance_manager']}>
                <AuditLogsPage />
              </ProtectedRoute>
            ),
          },
        ],
      },
    ],
  },
]);
