import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { LockKeyhole, UserRound } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import AppLogo from '../components/AppLogo';
import { APP_NAME } from '../utils/branding';

const Login = () => {
    const navigate = useNavigate();
    const { login, isAuthenticated, role, isLoading } = useAuth();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!isLoading && isAuthenticated) {
        return <Navigate to={role === 'ADMIN' ? '/admin' : '/faculty'} replace />;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        setError(null);
        try {
            const authUser = await login(username.trim(), password);
            navigate(authUser.role === 'ADMIN' ? '/admin' : '/faculty', { replace: true });
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || 'Login failed.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div style={{
            minHeight: '100vh',
            display: 'grid',
            placeItems: 'center',
            padding: '2rem',
        }}>
            <div className="glass-panel" style={{
                width: '100%',
                maxWidth: '480px',
                padding: '2rem',
                background: 'rgba(255,255,255,0.92)',
            }}>
                <div style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <AppLogo size={64} />
                    <div>
                        <h1 style={{ fontSize: '2rem', fontWeight: 800, marginBottom: '0.5rem' }}>{APP_NAME} Login</h1>
                    </div>
                </div>
                <form onSubmit={handleSubmit}>
                    <div className="input-group">
                        <label className="input-label">Username</label>
                        <div style={{ position: 'relative' }}>
                            <UserRound size={18} style={{ position: 'absolute', left: '0.9rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                            <input
                                className="input-field"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="Enter your username or faculty ID (e.g. FAC001)"
                                style={{ width: '100%', boxSizing: 'border-box', paddingLeft: '2.7rem' }}
                            />
                        </div>
                    </div>

                    <div className="input-group">
                        <label className="input-label">Password</label>
                        <div style={{ position: 'relative' }}>
                            <LockKeyhole size={18} style={{ position: 'absolute', left: '0.9rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                            <input
                                type="password"
                                className="input-field"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Enter your password"
                                style={{ width: '100%', boxSizing: 'border-box', paddingLeft: '2.7rem' }}
                            />
                        </div>
                    </div>

                    {error && (
                        <div style={{
                            marginBottom: '1rem',
                            padding: '0.85rem 1rem',
                            borderRadius: '0.75rem',
                            background: '#fef2f2',
                            color: '#b91c1c',
                            border: '1px solid #fecaca',
                            fontSize: '0.9rem',
                        }}>
                            {error}
                        </div>
                    )}

                    <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%' }}>
                        {submitting ? 'Signing in...' : 'Sign In'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Login;
