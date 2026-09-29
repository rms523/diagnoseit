import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import * as SecureStore from 'expo-secure-store';
import { apiService, User } from '../services/api';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  register: (userData: RegisterData) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  updateUser: (userData: Partial<User>) => Promise<void>;
}

interface RegisterData {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadStoredAuth();
  }, []);

  const loadStoredAuth = async () => {
    try {
      const token = await SecureStore.getItemAsync('authToken');
      if (token) {
        apiService.setToken(token);
        // Cached profile data alone does not prove that a rotating, expiring token is still valid.
        const currentUser = await apiService.getProfile();
        setUser(currentUser);
        await SecureStore.setItemAsync('user_data', JSON.stringify(currentUser));
      } else {
        await clearStoredAuth();
      }
    } catch (error) {
      console.error('Error loading stored auth:', error);
      setUser(null);
      apiService.clearToken();
      await clearStoredAuth();
    } finally {
      setIsLoading(false);
    }
  };

  const storeAuth = async (token: string, userData: User) => {
    try {
      await SecureStore.setItemAsync('authToken', token);
      await SecureStore.setItemAsync('user_data', JSON.stringify(userData));
    } catch (error) {
      console.error('Error storing auth:', error);
    }
  };

  const clearStoredAuth = async () => {
    try {
      await SecureStore.deleteItemAsync('authToken');
      await SecureStore.deleteItemAsync('user_data');
    } catch (error) {
      console.error('Error clearing stored auth:', error);
    }
  };

  const login = async (username: string, password: string) => {
    try {
      const response = await apiService.login(username, password);
      setUser(response.user);
      await storeAuth(response.token, response.user);
      return { success: true };
    } catch (error: any) {
      return { 
        success: false, 
        error: error.message || 'Login failed' 
      };
    }
  };

  const register = async (userData: RegisterData) => {
    try {
      const response = await apiService.register(userData);
      setUser(response.user);
      await storeAuth(response.token, response.user);
      return { success: true };
    } catch (error: any) {
      // Show the server's reason ("Sign-up is closed on this server...") rather than the raw API error.
      const body = String(error?.message || '').replace(/^API Error: \d+[^-]*- /, '');
      let message = body || 'Registration failed';
      try {
        const data = JSON.parse(body);
        if (typeof data?.error === 'string') message = data.error;
      } catch {
        /* body is not JSON */
      }
      return { success: false, error: message };
    }
  };

  const logout = async () => {
    try {
      await apiService.logout();
    } catch (error) {
      console.error('Error during logout:', error);
    } finally {
      setUser(null);
      apiService.clearToken();
      await clearStoredAuth();
    }
  };

  const updateUser = async (userData: Partial<User>) => {
    try {
      const updatedUser = await apiService.updateProfile(userData);
      setUser(updatedUser);
      await SecureStore.setItemAsync('user_data', JSON.stringify(updatedUser));
    } catch (error) {
      console.error('Error updating user:', error);
      throw error;
    }
  };

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    register,
    logout,
    updateUser,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
