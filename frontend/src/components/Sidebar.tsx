import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Users, Building2, Calendar, Clock3, LogOut, NotebookTabs } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import AppLogo from './AppLogo';
import { APP_NAME } from '../utils/branding';

const Sidebar = () => {
    const { logout, role } = useAuth();

    const navItems = role === 'FACULTY'
        ? [
            { icon: Clock3, label: 'My Timetable', path: '/faculty' },
        ]
        : [
            { icon: LayoutDashboard, label: 'Dashboard', path: '/admin' },
            { icon: Building2, label: 'Departments', path: '/admin/departments' },
            { icon: Users, label: 'Faculty', path: '/admin/faculty' },
            { icon: NotebookTabs, label: 'Faculty Timetable', path: '/admin/faculty-timetable' },
            { icon: Calendar, label: 'Timetables', path: '/admin/timetables' },
        ];

    return (
        <aside className="glass-panel" style={{
            width: '240px',
            height: 'calc(100vh - 2rem)',
            margin: '1rem',
            display: 'flex',
            flexDirection: 'column',
            padding: '1.5rem',
            position: 'sticky',
            top: '1rem'
        }}>
            <div style={{ marginBottom: '2.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <AppLogo size={44} />
                <h2 style={{ fontSize: '1.25rem', fontWeight: '700', letterSpacing: '-0.5px' }}>{APP_NAME}</h2>
            </div>

            <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {navItems.map((item) => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        end={item.path === '/admin'}
                        className={() => `btn`}
                        style={({ isActive }) => ({
                            display: 'flex',
                            gap: '0.75rem',
                            justifyContent: 'flex-start',
                            background: isActive ? 'var(--primary-600)' : 'transparent',
                            color: isActive ? 'white' : 'var(--text-muted)',
                            opacity: isActive ? 1 : 0.8,
                            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
                        })}
                    >
                        <item.icon size={20} />
                        {item.label}
                    </NavLink>
                ))}
            </nav>

            <div style={{ paddingTop: '1rem', borderTop: '1px solid var(--border-light)' }}>
                <button onClick={logout} className="btn" style={{
                    width: '100%',
                    justifyContent: 'flex-start',
                    color: 'var(--text-muted)',
                    gap: '0.75rem',
                    display: 'flex'
                }}>
                    <LogOut size={20} />
                    Logout
                </button>
            </div>
        </aside>
    );
};

export default Sidebar;
