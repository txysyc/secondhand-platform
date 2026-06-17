import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './Layout';
import { Login } from '../features/auth/Login';
import { Register } from '../features/auth/Register';
import { ProtectedRoute, AnonymousRoute } from '../features/auth/ProtectedRoute';
import { ListingList } from '../features/catalog/ListingList';
import { ListingDetail } from '../features/catalog/ListingDetail';
import { ProfileEdit } from '../features/users/ProfileEdit';
import { PublicProfile } from '../features/users/PublicProfile';
import { MyListings } from '../features/catalog/MyListings';
import { ListingForm } from '../features/catalog/ListingForm';
import { OrderList } from '../features/orders/OrderList';
import { OrderDetail } from '../features/orders/OrderDetail';
import { MessageCenter } from '../features/messages/MessageCenter';

const NotFoundPage = () => (
  <div className="placeholder-card error-card fade-in">
    <h2>🚫 404 - 页面未找到</h2>
    <p>您访问的路由地址不存在。</p>
  </div>
);

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
        path: 'me/listings',
        element: (
          <ProtectedRoute>
            <MyListings />
          </ProtectedRoute>
        ),
      },
      {
        path: 'me/listings/new',
        element: (
          <ProtectedRoute>
            <ListingForm />
          </ProtectedRoute>
        ),
      },
      {
        path: 'me/listings/:id/edit',
        element: (
          <ProtectedRoute>
            <ListingForm />
          </ProtectedRoute>
        ),
      },
      {
        path: 'me',
        element: (
          <ProtectedRoute>
            <ProfileEdit />
          </ProtectedRoute>
        ),
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
