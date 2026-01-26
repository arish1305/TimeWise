import React, { useState } from 'react';
import api from '../api/axios';
import { useAuth } from '../context/AuthContext';

const AdminDashboard: React.FC = () => {
    const { logout, user } = useAuth();
    const [semester, setSemester] = useState(1);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');

    const [schedule, setSchedule] = useState<any>(null);

    const handleGenerate = async () => {
        setLoading(true);
        setMessage('AI Engine is optimizing schedule...');
        try {
            // Trigger generation
            const res = await api.post('/timetable/generate', { semester });
            setMessage(`Success! Schedule generated.`);
            setSchedule(res.data);
        } catch (err) {
            setMessage('Error generating schedule.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="container" style={{ padding: '2rem 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1>Admin Dashboard</h1>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <span>Welcome, {user?.username}</span>
                    <button onClick={logout} className="btn" style={{ border: '1px solid #ccc' }}>Logout</button>
                </div>
            </div>

            <div className="card">
                <h2>Timetable Operations</h2>
                <div className="input-group" style={{ maxWidth: '200px' }}>
                    <label className="input-label">Target Semester</label>
                    <input
                        type="number"
                        className="input-field"
                        value={semester}
                        onChange={(e) => setSemester(parseInt(e.target.value))}
                    />
                </div>

                <button
                    onClick={handleGenerate}
                    className="btn btn-primary"
                    disabled={loading}
                >
                    {loading ? 'Processing...' : 'Generate Timetable with AI'}
                </button>

                {message && (
                    <div style={{ marginTop: '1rem', padding: '1rem', background: '#f0f9ff', borderRadius: '0.5rem' }}>
                        {message}
                    </div>
                )}

                {schedule && (
                    <div style={{ marginTop: '1rem', overflowX: 'auto' }}>
                        <h3>Generated Schedule</h3>
                        <pre style={{ background: '#f8fafc', padding: '1rem', borderRadius: '0.5rem' }}>
                            {JSON.stringify(schedule, null, 2)}
                        </pre>
                    </div>
                )}
            </div>

            <div style={{ marginTop: '2rem' }}>
                <h3>Management Quick Links</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem' }}>
                    <div className="card">Manage Departments</div>
                    <div className="card">Manage Faculty</div>
                    <div className="card">Manage Courses</div>
                    <div className="card">Manage Rooms</div>
                </div>
            </div>
        </div>
    );
};

export default AdminDashboard;
