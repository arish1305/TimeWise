import React, { createContext, useContext, useState, useEffect } from 'react';
import { jwtDecode } from "jwt-decode"; // Need to install jwt-decode

interface AuthContextType {
    user: any;
    login: (token: string) => void;
    logout: () => void;
    isAuthenticated: boolean;
    role: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<any>(null);
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
    const [role, setRole] = useState<string | null>(null);

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (token) {
            try {
                const decoded: any = jwtDecode(token);
                // We simple store username for now, ideally fetch profile
                setUser({ username: decoded.sub });
                setIsAuthenticated(true);
                // MVP: we didn't put role in token, maybe we should have? 
                // For MVP, if we don't have role in token, we might need to fetch it.
                // Let's assume we fetch profile or decode if we add it. 
                // Note: In backend `create_access_token` we only put `sub`.
                // Let's rely on backend or just assume ADMIN for now to test, OR fetch profile.
                // I'll add a fetch profile call if needed, or better, update backend to include role in token.
                // For now, let's just decoding.
            } catch (e) {
                logout();
            }
        }
    }, []);

    const login = (token: string) => {
        localStorage.setItem('token', token);
        const decoded: any = jwtDecode(token);
        setUser({ username: decoded.sub });
        setIsAuthenticated(true);
    };

    const logout = () => {
        localStorage.removeItem('token');
        setUser(null);
        setIsAuthenticated(false);
        setRole(null);
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, isAuthenticated, role }}>
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
