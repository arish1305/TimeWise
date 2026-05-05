import React, { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { jwtDecode } from 'jwt-decode';
import api from '../api/axios';

type UserRole = 'ADMIN' | 'FACULTY';

interface AuthUser {
    username: string;
    role: UserRole;
    full_name?: string | null;
    faculty_id?: number | null;
}

interface AuthContextType {
    user: AuthUser | null;
    login: (username: string, password: string) => Promise<AuthUser>;
    logout: () => void;
    isAuthenticated: boolean;
    role: UserRole | null;
    isLoading: boolean;
}

interface TokenPayload {
    sub: string;
    role: UserRole;
    faculty_id?: number;
    exp: number;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const buildUserFromToken = (token: string): AuthUser | null => {
    try {
        const decoded = jwtDecode<TokenPayload>(token);
        if (!decoded?.sub || !decoded?.role) {
            return null;
        }
        return {
            username: decoded.sub,
            role: decoded.role,
            faculty_id: decoded.faculty_id,
            full_name: null,
        };
    } catch {
        return null;
    }
};

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (!token) {
            setIsLoading(false);
            return;
        }

        const restoredUser = buildUserFromToken(token);
        if (!restoredUser) {
            localStorage.removeItem('token');
            localStorage.removeItem('auth_user');
            setIsLoading(false);
            return;
        }

        const persistedUser = localStorage.getItem('auth_user');
        if (persistedUser) {
            try {
                const parsed = JSON.parse(persistedUser) as AuthUser;
                setUser({ ...restoredUser, full_name: parsed.full_name ?? restoredUser.full_name });
            } catch {
                setUser(restoredUser);
            }
        } else {
            setUser(restoredUser);
        }
        setIsLoading(false);
    }, []);

    const login = async (username: string, password: string) => {
        const body = new URLSearchParams();
        body.append('username', username);
        body.append('password', password);

        const res = await api.post('/auth/login', body, {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });

        const authUser: AuthUser = {
            username: res.data.username,
            role: res.data.role,
            full_name: res.data.full_name,
            faculty_id: res.data.faculty_id,
        };

        localStorage.setItem('token', res.data.access_token);
        localStorage.setItem('auth_user', JSON.stringify(authUser));
        setUser(authUser);
        return authUser;
    };

    const logout = () => {
        localStorage.removeItem('token');
        localStorage.removeItem('auth_user');
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{
            user,
            login,
            logout,
            isAuthenticated: !!user,
            role: user?.role || null,
            isLoading,
        }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
