import { useAuth } from '../context/AuthContext';
import { Link } from 'react-router-dom';
import { Building2, Users, Calendar, ArrowRight, TrendingUp, Sparkles } from 'lucide-react';

const AdminDashboard = () => {
    const { user } = useAuth();

    return (
        <div className="animate-fade-in">
            {/* Header Section */}
            <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2.5rem' }}>
                <div>
                    <h1 style={{ fontSize: '2.25rem', fontWeight: 800, margin: 0, letterSpacing: '-1px' }}>
                        Dashboard
                    </h1>
                    <p style={{ color: 'var(--text-muted)', fontSize: '1rem', marginTop: '0.25rem' }}>
                        Here's what's happening with your schedule today.
                    </p>
                </div>
            </header>

            {/* Welcome Banner */}
            <div className="card shadow-md animate-fade-in delay-100" style={{
                background: 'linear-gradient(135deg, var(--primary-600) 0%, #6366f1 100%)',
                color: 'white',
                marginBottom: '2.5rem',
                border: 'none',
                position: 'relative',
                overflow: 'hidden',
                padding: '2.5rem'
            }}>
                <div style={{ position: 'relative', zIndex: 1, maxWidth: '600px' }}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.2)', padding: '0.25rem 0.75rem', borderRadius: '100px', fontSize: '0.875rem', fontWeight: 500, marginBottom: '1rem', backdropFilter: 'blur(4px)' }}>
                        <Sparkles size={16} />
                        Welcome back, {user?.username || 'Admin'}
                    </div>
                    <h2 style={{ fontSize: '2.5rem', fontWeight: 800, margin: '0 0 1rem 0', lineHeight: 1.1, letterSpacing: '-1px' }}>
                        TimeWise Engine is Active
                    </h2>
                    <p style={{ fontSize: '1.125rem', opacity: 0.9, margin: 0, lineHeight: 1.6 }}>
                        AI-driven scheduling and resource management. Generate conflict-free timetables in seconds, not weeks.
                    </p>
                </div>
                {/* Decorative BG element */}
                <div style={{
                    position: 'absolute', right: '-10%', top: '-20%', width: '400px', height: '400px',
                    background: 'radial-gradient(circle, rgba(255,255,255,0.15) 0%, transparent 70%)',
                    borderRadius: '50%', pointerEvents: 'none'
                }}></div>
            </div>

            {/* Quick Stats Grid */}
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 1rem 0', color: 'var(--text-secondary)' }}>Quick Navigation</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>

                {/* Depts Card */}
                <Link to="/admin/departments" style={{ textDecoration: 'none', color: 'inherit' }} className="animate-fade-in delay-100">
                    <div className="card" style={{ height: '100%', position: 'relative', overflow: 'hidden', borderTop: '4px solid var(--primary-500)', display: 'flex', flexDirection: 'column' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                            <div style={{ background: 'var(--primary-50)', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: 'var(--primary-600)' }}>
                                <Building2 size={24} />
                            </div>
                            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary-600)', background: 'var(--primary-50)', padding: '0.25rem 0.75rem', borderRadius: '100px' }}>Setup</span>
                        </div>
                        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.5rem 0' }}>Departments</h3>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', margin: '0 0 1.5rem 0', flex: 1 }}>Configure academic years, sections, and departmental structure.</p>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary-600)', fontWeight: 600, fontSize: '0.95rem', alignSelf: 'flex-start' }}>
                            Manage Setup <ArrowRight size={18} />
                        </div>
                    </div>
                </Link>

                {/* Faculty Card */}
                <Link to="/admin/faculty" style={{ textDecoration: 'none', color: 'inherit' }} className="animate-fade-in delay-200">
                    <div className="card" style={{ height: '100%', position: 'relative', overflow: 'hidden', borderTop: '4px solid #8b5cf6', display: 'flex', flexDirection: 'column' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                            <div style={{ background: '#ede9fe', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: '#7c3aed' }}>
                                <Users size={24} />
                            </div>
                            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#7c3aed', background: '#ede9fe', padding: '0.25rem 0.75rem', borderRadius: '100px' }}>Resources</span>
                        </div>
                        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.5rem 0' }}>Faculty</h3>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', margin: '0 0 1.5rem 0', flex: 1 }}>Manage faculty profiles, workloads, constraints, and subject assignments.</p>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#7c3aed', fontWeight: 600, fontSize: '0.95rem', alignSelf: 'flex-start' }}>
                            View Faculty <ArrowRight size={18} />
                        </div>
                    </div>
                </Link>

                {/* Timetables Card */}
                <Link to="/admin/timetables" style={{ textDecoration: 'none', color: 'inherit' }} className="animate-fade-in delay-300">
                    <div className="card" style={{ height: '100%', position: 'relative', overflow: 'hidden', borderTop: '4px solid #10b981', display: 'flex', flexDirection: 'column' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                            <div style={{ background: '#d1fae5', padding: '0.75rem', borderRadius: 'var(--radius-md)', color: '#059669' }}>
                                <Calendar size={24} />
                            </div>
                            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#059669', background: '#d1fae5', padding: '0.25rem 0.75rem', borderRadius: '100px' }}>Actions</span>
                        </div>
                        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.5rem 0' }}>Timetables</h3>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', margin: '0 0 1.5rem 0', flex: 1 }}>Generate, optimize, and view AI-powered class schedules.</p>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#059669', fontWeight: 600, fontSize: '0.95rem', alignSelf: 'flex-start' }}>
                            Generate Schedule <ArrowRight size={18} />
                        </div>
                    </div>
                </Link>
            </div>

            {/* System Status Mockup */}
            <div className="card animate-fade-in delay-300" style={{ background: 'var(--secondary-50)', border: '1px dashed var(--secondary-300)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div style={{ background: 'white', padding: '1rem', borderRadius: '50%', boxShadow: 'var(--shadow-sm)' }}>
                        <TrendingUp size={24} color="var(--primary-500)" />
                    </div>
                    <div>
                        <h4 style={{ margin: '0 0 0.25rem 0', fontSize: '1.1rem' }}>System Efficiency is Optimal</h4>
                        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem' }}>All backend AI models are loaded and ready for timetable generation.</p>
                    </div>
                </div>
            </div>

        </div>
    );
};
export default AdminDashboard;
