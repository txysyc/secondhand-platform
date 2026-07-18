import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import type { User } from '../types/auth';
import { AuthContext } from './auth';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshUser = async () => {
    try {
      const userData = await apiClient.get<User>('/users/me/');
      setUser(userData);
    } catch {
      setUser(null);
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
  };

  const login = async (identifier: string, password: string) => {
    const data = await apiClient.post<{ access: string; refresh: string }>('/auth/token/', {
      identifier,
      password,
    });
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    await refreshUser();
  };

  const register = async (formData: Record<string, string>) => {
    await apiClient.post('/auth/register/', formData);
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
  };

  useEffect(() => {
    apiClient.setAuthFailureCallback(() => {
      setUser(null);
    });

    const initAuth = async () => {
      const access = localStorage.getItem('access_token');
      if (access) {
        await refreshUser();
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};
