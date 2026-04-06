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
import UserManagementPage from './pages/admin/UserManagementPage';
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
              <ProtectedRoute allowedRoles={['owner', 'production_manager', 'store_manager']}>
                <WastagePage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'distribution',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'production_manager', 'store_manager']}>
                <DistributionPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'sales',
            element: (
              <ProtectedRoute allowedRoles={['owner', 'store_manager']}>
                <SalesPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'reports',
            element: (
              <ProtectedRoute allowedRoles={['owner']}>
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
            path: 'admin/users',
            element: (
              <ProtectedRoute allowedRoles={['admin']}>
                <UserManagementPage />
              </ProtectedRoute>
            ),
          },
          {
            path: 'admin/audit-logs',
            element: (
              <ProtectedRoute allowedRoles={['admin', 'owner']}>
                <AuditLogsPage />
              </ProtectedRoute>
            ),
          },
        ],
      },
    ],
  },
]);
