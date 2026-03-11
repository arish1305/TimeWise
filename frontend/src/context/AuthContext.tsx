import React, { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';

interface AuthContextType {
    user: any;
    login: (token: string) => void;
    logout: () => void;
    isAuthenticated: boolean;
    role: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    // Basic state for future auth integration
    const [user] = useState<any>(null);
    const [isAuthenticated] = useState(false);
    const [role] = useState<string | null>(null);

    const login = async () => {
        // Implement login
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
