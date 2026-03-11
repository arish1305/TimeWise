import { useAuth } from '../context/AuthContext';
import { Link } from 'react-router-dom';

const AdminDashboard = () => {
    const { user } = useAuth();

    return (
        <div>
            <h1 style={{ fontSize: '2rem', fontWeight: 800, marginBottom: '2rem' }}>Dashboard</h1>

            <div className="card" style={{
                background: 'linear-gradient(135deg, var(--primary-600), var(--primary-900))',
                color: 'white',
                marginBottom: '2rem',
                border: 'none',
                boxShadow: '0 10px 25px -5px rgba(79, 70, 229, 0.4)'
            }}>
                <h2 style={{ fontSize: '1.75rem', marginBottom: '0.5rem' }}>Welcome back, {user?.username}</h2>
                <p style={{ opacity: 0.9, fontSize: '1.1rem' }}>Manage your university schedule efficiently.</p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem' }}>
                <Link to="/admin/departments" style={{ textDecoration: 'none', color: 'inherit' }}>
                    <div className="card" style={{ borderLeft: '4px solid var(--primary-500)', cursor: 'pointer', height: '100%' }}>
                        <h3 style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Departments</h3>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.5rem 0' }}>Structure & Config</div>
                        <span style={{ fontSize: '0.9rem', color: 'var(--primary-600)', fontWeight: 500 }}>Manage Years & Sections &rarr;</span>
                    </div>
                </Link>

                <Link to="/admin/faculty" style={{ textDecoration: 'none', color: 'inherit' }}>
                    <div className="card" style={{ borderLeft: '4px solid var(--secondary-500)', cursor: 'pointer', height: '100%' }}>
                        <h3 style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Faculty</h3>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.5rem 0' }}>Profiles & Workload</div>
                        <span style={{ fontSize: '0.9rem', color: 'var(--secondary-500)', fontWeight: 500 }}>Assign Subjects &rarr;</span>
                    </div>
                </Link>

                <Link to="/admin/timetables" style={{ textDecoration: 'none', color: 'inherit' }}>
                    <div className="card" style={{ borderLeft: '4px solid #10b981', cursor: 'pointer', height: '100%' }}>
                        <h3 style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Timetables</h3>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.5rem 0' }}>Generation</div>
                        <span style={{ fontSize: '0.9rem', color: '#059669', fontWeight: 500 }}>View & Optimize &rarr;</span>
                    </div>
                </Link>
            </div>
        </div>
    );
};
export default AdminDashboard;
