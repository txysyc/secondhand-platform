import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './Layout';
import { Login } from '../features/auth/Login';
import { Register } from '../features/auth/Register';
import { ProtectedRoute, AnonymousRoute } from '../features/auth/ProtectedRoute';
import { ListingList } from '../features/catalog/ListingList';
import { ListingDetail } from '../features/catalog/ListingDetail';
import { ProfileEdit } from '../features/users/ProfileEdit';
import { PublicProfile } from '../features/users/PublicProfile';
import { AddressManager } from '../features/users/AddressManager';
import { MyListings } from '../features/catalog/MyListings';
import { BrowseHistory, MyFavorites } from '../features/catalog/ListingBehaviorList';
import { ListingForm } from '../features/catalog/ListingForm';
import { OrderList } from '../features/orders/OrderList';
import { OrderDetail } from '../features/orders/OrderDetail';
import { MessageCenter } from '../features/messages/MessageCenter';
import { NotificationCenter } from '../features/notifications/NotificationCenter';
import { AccountLayout } from '../features/users/AccountLayout';
import { NotFoundPage } from './NotFoundPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      {
        index: true,
        element: <ListingList />,
      },
      {
        path: 'listings/:id',
        element: <ListingDetail />,
      },
      {
        path: 'login',
        element: (
          <AnonymousRoute>
            <Login />
          </AnonymousRoute>
        ),
      },
      {
        path: 'register',
        element: (
          <AnonymousRoute>
            <Register />
          </AnonymousRoute>
        ),
      },
      {
        path: 'messages',
        element: (
          <ProtectedRoute>
            <MessageCenter />
          </ProtectedRoute>
        ),
      },
      {
        path: 'notifications',
        element: (
          <ProtectedRoute>
            <NotificationCenter />
          </ProtectedRoute>
        ),
      },
      {
        path: 'orders/buyer',
        element: (
          <ProtectedRoute>
            <OrderList />
          </ProtectedRoute>
        ),
      },
      {
        path: 'orders/seller',
        element: (
          <ProtectedRoute>
            <OrderList />
          </ProtectedRoute>
        ),
      },
      {
        path: 'orders/:id',
        element: (
          <ProtectedRoute>
            <OrderDetail />
          </ProtectedRoute>
        ),
      },
      {
        path: 'me',
        element: (
          <ProtectedRoute>
            <AccountLayout />
          </ProtectedRoute>
        ),
        children: [
          { index: true, element: <ProfileEdit /> },
          { path: 'listings', element: <MyListings /> },
          { path: 'listings/new', element: <ListingForm /> },
          { path: 'listings/:id/edit', element: <ListingForm /> },
          { path: 'favorites', element: <MyFavorites /> },
          { path: 'history', element: <BrowseHistory /> },
          { path: 'addresses', element: <AddressManager /> },
        ],
      },
      {
        path: 'users/:id',
        element: <PublicProfile />,
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
]);
