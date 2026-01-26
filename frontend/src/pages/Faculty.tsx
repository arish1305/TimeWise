import React, { useState, useEffect } from 'react';
import api from '../api/axios';
import { Plus, Edit2, Trash2, User, UserCheck, BookOpen, Check, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Subject {
    id: number;
    name: string;
    code: string;
    department_id: number;
}

interface Faculty {
    id: number;
    name: string;
    faculty_id_code: string;
    faculty_type: string;
    min_hours_per_week: number;
    max_hours_per_week: number;
    qualified_subjects?: { subject_id: number; preference_level: number; }[];
}

const FacultyManager = () => {
    const [facultyList, setFacultyList] = useState<Faculty[]>([]);
    const [loading, setLoading] = useState(false);
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);

    // Subject Assignment State
    const [showSubjectModal, setShowSubjectModal] = useState(false);
    const [selectedFaculty, setSelectedFaculty] = useState<Faculty | null>(null);
    const [availableSubjects, setAvailableSubjects] = useState<Subject[]>([]);
    const [selectedSubjectIds, setSelectedSubjectIds] = useState<number[]>([]);

    const [formData, setFormData] = useState({
        name: '',
        faculty_id_code: '',
        faculty_type: 'ASSISTANT_PROFESSOR',
        min_hours_per_week: 5,
        max_hours_per_week: 18
    });

    useEffect(() => {
        fetchFaculty();
        fetchSubjects();
    }, []);

    const fetchSubjects = async () => {
        try {
            const res = await api.get('/admin/subjects');
            setAvailableSubjects(res.data);
        } catch (err) { console.error("Failed to fetch subjects", err); }
    };

    const fetchFaculty = async () => {
        setLoading(true);
        try {
            const res = await api.get('/admin/faculty');
            setFacultyList(res.data);
        } catch (err) { console.error(err); } finally { setLoading(false); }
    };

    const handleSubmit = async () => {
        try {
            if (editingId) {
                await api.put(`/admin/faculty/${editingId}`, formData);
            } else {
                await api.post('/admin/faculty', formData);
            }
            setShowForm(false);
            setEditingId(null);
            resetForm();
            fetchFaculty();
        } catch (err) { console.error(err); alert("Error saving faculty. Check if ID Code is unique."); }
    };

    const resetForm = () => {
        setFormData({
            name: '',
            faculty_id_code: '',
            faculty_type: 'ASSISTANT_PROFESSOR',
            min_hours_per_week: 5,
            max_hours_per_week: 18
        });
    };

    const startEdit = (fac: Faculty) => {
        setFormData({
            name: fac.name,
            faculty_id_code: fac.faculty_id_code || '',
            faculty_type: fac.faculty_type,
            min_hours_per_week: fac.min_hours_per_week,
            max_hours_per_week: fac.max_hours_per_week
        });
        setEditingId(fac.id);
        setShowForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const deleteFaculty = async (id: number) => {
        if (!window.confirm("Delete this faculty member?")) return;
        try {
            await api.delete(`/admin/faculty/${id}`);
            fetchFaculty();
        } catch (err) { console.error(err); }
    };

    const openSubjectModal = (fac: Faculty) => {
        setSelectedFaculty(fac);
        // Pre-select existing subjects
        const existingIds = fac.qualified_subjects?.map(qs => qs.subject_id) || [];
        setSelectedSubjectIds(existingIds);
        setShowSubjectModal(true);
    };

    const toggleSubjectSelection = (subId: number) => {
        setSelectedSubjectIds(prev =>
            prev.includes(subId) ? prev.filter(id => id !== subId) : [...prev, subId]
        );
    };

    const saveSubjectAssignments = async () => {
        if (!selectedFaculty) return;
        try {
            // Transform to API format [ { subject_id, preference_level } ]
            const payload = selectedSubjectIds.map(id => ({
                subject_id: id,
                preference_level: 1 // Default preference
            }));

            await api.post(`/admin/faculty/${selectedFaculty.id}/subjects`, payload);
            setShowSubjectModal(false);
            fetchFaculty(); // Refresh to get updated assignments
        } catch (err) { console.error(err); alert("Failed to save assignments"); }
    };

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 800 }}>Faculty Management</h1>
                <button className="btn btn-primary" onClick={() => {
                    setEditingId(null);
                    resetForm();
                    setShowForm(true);
                }}>
                    <Plus size={20} /> Add Faculty
                </button>
            </div>

            <AnimatePresence>
                {showForm && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="card" style={{ marginBottom: '2rem', borderLeft: '4px solid var(--primary-500)' }}
                    >
                        <h3>{editingId ? 'Edit Faculty' : 'New Faculty Member'}</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                            <div className="input-group">
                                <label className="input-label">Full Name</label>
                                <input className="input-field" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} placeholder="e.g. Dr. Jane Doe" />
                            </div>
                            <div className="input-group">
                                <label className="input-label">Faculty ID Code</label>
                                <input className="input-field" value={formData.faculty_id_code} onChange={e => setFormData({ ...formData, faculty_id_code: e.target.value })} placeholder="e.g. FAC001" />
                            </div>

                            <div className="input-group">
                                <label className="input-label">Designation</label>
                                <select className="input-field" value={formData.faculty_type} onChange={e => setFormData({ ...formData, faculty_type: e.target.value })}>
                                    <option value="PROFESSOR">Professor</option>
                                    <option value="ASSISTANT_PROFESSOR">Assistant Professor</option>
                                    <option value="LAB_INSTRUCTOR">Lab Instructor</option>
                                    <option value="GUEST">Guest</option>
                                </select>
                            </div>

                            <div style={{ display: 'flex', gap: '1rem' }}>
                                <div className="input-group" style={{ flex: 1 }}>
                                    <label className="input-label">Min Hours/Week</label>
                                    <input type="number" className="input-field" value={formData.min_hours_per_week} onChange={e => setFormData({ ...formData, min_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                                <div className="input-group" style={{ flex: 1 }}>
                                    <label className="input-label">Max Hours/Week</label>
                                    <input type="number" className="input-field" value={formData.max_hours_per_week} onChange={e => setFormData({ ...formData, max_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                            </div>
                        </div>
                        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem' }}>
                            <button className="btn btn-primary" onClick={handleSubmit}>Save Profile</button>
                            <button className="btn" onClick={() => setShowForm(false)}>Cancel</button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Subject Assignment Modal */}
            <AnimatePresence>
                {showSubjectModal && selectedFaculty && (
                    <div style={{
                        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                        background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
                    }} onClick={() => setShowSubjectModal(false)}>
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
                            className="card" style={{ width: '600px', maxHeight: '80vh', display: 'flex', flexDirection: 'column', padding: 0 }}
                            onClick={e => e.stopPropagation()}
                        >
                            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h3 style={{ margin: 0 }}>Assign Subjects to {selectedFaculty.name}</h3>
                                <button className="btn" onClick={() => setShowSubjectModal(false)}><X size={20} /></button>
                            </div>

                            <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
                                <p style={{ marginBottom: '1rem', color: 'var(--text-muted)' }}>Select subjects this faculty member is qualified to teach.</p>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '1rem' }}>
                                    {availableSubjects.map(sub => {
                                        const isSelected = selectedSubjectIds.includes(sub.id);
                                        return (
                                            <div
                                                key={sub.id}
                                                onClick={() => toggleSubjectSelection(sub.id)}
                                                style={{
                                                    padding: '0.75rem', borderRadius: '8px', border: `2px solid ${isSelected ? 'var(--primary-500)' : 'var(--border-light)'}`,
                                                    background: isSelected ? 'var(--primary-50)' : 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between'
                                                }}
                                            >
                                                <div>
                                                    <div style={{ fontWeight: 600 }}>{sub.name}</div>
                                                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{sub.code}</div>
                                                </div>
                                                {isSelected && <Check size={18} color="var(--primary-600)" />}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            <div style={{ padding: '1.5rem', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
                                <button className="btn" onClick={() => setShowSubjectModal(false)}>Cancel</button>
                                <button className="btn btn-primary" onClick={saveSubjectAssignments}>Save Assignments ({selectedSubjectIds.length})</button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1.5rem' }}>
                {facultyList.map(fac => (
                    <div key={fac.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                                <div style={{
                                    width: 48, height: 48, borderRadius: '50%', background: 'var(--primary-100)',
                                    color: 'var(--primary-600)', display: 'flex', alignItems: 'center', justifyContent: 'center'
                                }}>
                                    <User size={24} />
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>{fac.name}</div>
                                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <span style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>{fac.faculty_id_code || 'No ID'}</span>
                                        <span>•</span>
                                        <span>{fac.faculty_type.replace('_', ' ')}</span>
                                    </div>
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <button className="btn" title="Assign Subjects" style={{ padding: '0.4rem', color: 'var(--secondary-600)', background: 'var(--secondary-50)' }} onClick={() => openSubjectModal(fac)}>
                                    <BookOpen size={16} />
                                </button>
                                <button className="btn" style={{ padding: '0.4rem', color: 'var(--text-muted)' }} onClick={() => startEdit(fac)}>
                                    <Edit2 size={16} />
                                </button>
                                <button className="btn" style={{ padding: '0.4rem', color: 'var(--error-color)' }} onClick={() => deleteFaculty(fac.id)}>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        </div>

                        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: 'var(--primary-600)' }}>{fac.min_hours_per_week}h</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Min Load</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: 'var(--text-main)' }}>{fac.max_hours_per_week}h</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Max Load</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: 'var(--secondary-600)' }}>{fac.qualified_subjects?.length || 0}</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Subjects</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: '#10b981' }}>Active</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Status</div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};
export default FacultyManager;
