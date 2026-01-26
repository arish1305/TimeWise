import React, { createContext, useContext, useState, useEffect } from 'react';

interface AuthContextType {
    user: any;
    login: (token: string) => void;
    logout: () => void;
    isAuthenticated: boolean;
    role: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // Hardcode authenticated state
    const [user, setUser] = useState<any>({ username: 'admin' });
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(true);
    const [role, setRole] = useState<string | null>('ADMIN');

    const login = (token: string) => {
        // No-op
        console.log("Login called (disabled)");
    };

    const logout = () => {
        // No-op
        console.log("Logout called (disabled)");
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
