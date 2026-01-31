import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

const Layout = () => {
    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-app)' }}>
            <Sidebar />
            <main style={{ flex: 1, padding: '1rem', overflowY: 'auto', maxHeight: '100vh' }}>
                <div className="glass-panel" style={{
                    padding: '2rem',
                    minHeight: 'calc(100vh - 2rem)',
                    background: 'rgba(255, 255, 255, 0.4)' /* Lighter glass for main area */
                }}>
                    <Outlet />
                </div>
            </main>
        </div>
    );
};
export default Layout;
